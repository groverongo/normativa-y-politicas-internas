"""CLI entrypoint for the multi-agent regulatory document ingestion pipeline.

Usage:
    python main.py ingest <file-or-dir> [--provider mock|anthropic|openai|gemini]
                                         [--model NAME] [--seed sample_docs/seed_corpus.json]
                                         [--runs-dir runs] [--max-reclassify 2] [--max-impact-docs 5]
    python main.py trace <runs/<run_id>/interaction_log.jsonl>

See .omc/plans/autopilot-impl.md section 2.12 for the exact CLI contract.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from config import Settings
from llm_provider import LLMError, get_provider
from logging_trace import InteractionLogger
from pipeline import IngestionPipeline
from storage import InMemoryStorage, StorageError, get_storage


def _build_ingest_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("ingest", help="Ingest one file or a directory of documents.")
    p.add_argument("path", help="Path to a document file or a directory of documents (.txt/.md/.pdf).")
    p.add_argument(
        "--provider",
        dest="provider",
        default=None,
        help="LLM provider: mock|anthropic|openai|gemini (default: env LLM_PROVIDER, or mock).",
    )
    p.add_argument(
        "--model",
        dest="model",
        default=None,
        help="Model name for the chosen provider (default: env LLM_MODEL).",
    )
    p.add_argument(
        "--seed",
        dest="seed",
        default=None,
        help="Path to a seed corpus JSON file (e.g. sample_docs/seed_corpus.json). "
        "If omitted, storage starts empty.",
    )
    p.add_argument(
        "--runs-dir",
        dest="runs_dir",
        default=None,
        help="Directory to write run artifacts under (default: env RUNS_DIR, or 'runs').",
    )
    p.add_argument(
        "--max-reclassify",
        dest="max_reclassify",
        type=int,
        default=None,
        help="Loop 1 bound: max validation -> classifier reclassification attempts.",
    )
    p.add_argument(
        "--max-impact-docs",
        dest="max_impact_docs",
        type=int,
        default=None,
        help="Loop 2 bound: max fan-out of case-9 impact reassessment per document.",
    )


def _build_trace_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "trace", help="Print a human-readable timeline of an interaction_log.jsonl file."
    )
    p.add_argument("log_path", help="Path to runs/<run_id>/interaction_log.jsonl")


def cmd_ingest(args: argparse.Namespace) -> int:
    cli_overrides = {
        "llm_provider": args.provider,
        "llm_model": args.model,
        "runs_dir": Path(args.runs_dir) if args.runs_dir else None,
        "max_reclassify_attempts": args.max_reclassify,
        "max_impact_docs": args.max_impact_docs,
    }
    settings = Settings.from_env(**cli_overrides)

    if settings.llm_provider == "mock":
        print(
            "WARNING: running with the mock LLM provider (heuristic, not a real model). "
            "Set LLM_PROVIDER=anthropic|openai|gemini (and LLM_MODEL) for a real run.",
            file=sys.stderr,
        )
    if settings.storage_backend == "memory":
        print(
            "WARNING: running with in-memory storage (non-persistent, lost on exit). "
            "Set STORAGE_BACKEND=postgres (and DATABASE_URL, S3_BUCKET) for persistent storage.",
            file=sys.stderr,
        )

    try:
        provider = get_provider(settings)
    except LLMError as exc:
        print(f"error: could not initialize LLM provider: {exc}", file=sys.stderr)
        return 1

    path = Path(args.path)
    if not path.exists():
        print(f"error: path not found: {path}", file=sys.stderr)
        return 1

    if args.seed and settings.storage_backend != "memory":
        print(
            f"error: --seed is only supported with the memory storage backend "
            f"(STORAGE_BACKEND={settings.storage_backend!r})",
            file=sys.stderr,
        )
        return 1

    if args.seed:
        seed_path = Path(args.seed)
        if not seed_path.exists():
            print(f"error: seed file not found: {seed_path}", file=sys.stderr)
            return 1
        storage = InMemoryStorage.from_seed_file(seed_path)
    else:
        try:
            storage = get_storage(settings)
        except StorageError as exc:
            print(f"error: could not initialize storage backend: {exc}", file=sys.stderr)
            return 1

    logger = InteractionLogger(settings.runs_dir)
    pipeline = IngestionPipeline(storage, provider, logger, settings)

    try:
        results = pipeline.ingest_path(path)
    finally:
        logger.close()

    logger.write_json("summary.json", results)
    logger.write_json("storage_snapshot.json", storage.snapshot())

    _print_results_table(results)
    print(f"\nrun directory: {logger.run_dir}")
    return 0


def _print_results_table(results) -> None:
    rows = []
    for r in results:
        errors = "; ".join(r.errors) if r.errors else "-"
        case = r.final_case.value if r.final_case else "-"
        rows.append((r.source_file, r.doc_id or "-", case, errors))

    headers = ("source_file", "doc_id", "final_case", "errors")
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    def fmt_row(row) -> str:
        return "  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row))

    print(fmt_row(headers))
    print(fmt_row(["-" * w for w in widths]))
    for row in rows:
        print(fmt_row(row))


def cmd_trace(args: argparse.Namespace) -> int:
    log_path = Path(args.log_path)
    if not log_path.exists():
        print(f"error: log file not found: {log_path}", file=sys.stderr)
        return 1

    with log_path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            entry = json.loads(line)
            seq = entry.get("seq")
            ts = entry.get("ts")
            agent = entry.get("agent") or "-"
            event = entry.get("event") or "-"
            message = entry.get("message") or ""
            out = f"[{seq}] {ts} {agent:<12} {event:<16} {message}"
            if event == "feedback":
                from_agent = entry.get("from_agent") or "?"
                to_agent = entry.get("to_agent") or "?"
                loop = entry.get("loop") or "?"
                out += f"   ({from_agent} -> {to_agent}, loop={loop})"
            print(out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="main.py", description="Multi-agent regulatory document ingestion CLI."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _build_ingest_parser(subparsers)
    _build_trace_parser(subparsers)

    args = parser.parse_args(argv)
    if args.command == "ingest":
        return cmd_ingest(args)
    if args.command == "trace":
        return cmd_trace(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
