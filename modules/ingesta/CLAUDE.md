# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A hackathon-scale multi-agent pipeline ("B2 Normativa") that ingests one regulatory document (SBS/BCP resolutions, circulars, errata, ...) at a time, classifies it into one of 9 `LifecycleCase`s, extracts its effects, validates references against existing storage, and mutates a metadata graph (status, lineage, patches, review flags). `README.md` is detailed and accurate (architecture diagram, the authoritative case -> operations table in section 5, loop bounds, log format); read it before changing behavior rather than re-deriving it from code.

## Commands

This is the `modules/ingesta/` module of the `normativa-y-politicas-internas` monorepo (see the repo-root `CLAUDE.md` and `Makefile` for the other module, `modules/nttbanca-n/`). Flat Python modules at this module's root, no package install or build step beyond `Makefile`-managed `.venv`.

```bash
make install        # creates .venv here and installs requirements.txt (pydantic + python-dotenv; provider SDKs / pdfplumber optional)
make env             # cp .env.example .env if missing -- defaults to LLM_PROVIDER=mock, no API key needed
make test             # the only test suite: plain asserts, no pytest; forces LLM_PROVIDER=mock
make ingest           # python main.py ingest sample_docs/examples --seed sample_docs/seed_corpus.json
make trace FILE=runs/<run_id>/interaction_log.jsonl
make api              # uvicorn api:app --reload
```

Equivalently, from the repo root: `make -C modules/ingesta <target>`. The underlying commands (`pip install -r requirements.txt`, `python smoke_test.py`, `python main.py ...`) still work directly against this module's own `.venv` if you prefer not to use `make`.

`smoke_test.py` has no test selector: each `test_*` function is called from `main()` (line ~504). To run one, import it in a Python one-liner, e.g. `python -c "import smoke_test as s; s.test_case_2_full_replacement()"`. There is no linter or formatter configured.

## Architecture (the parts that span files)

- **`pipeline.py` `IngestionPipeline` is the only mediator.** Agents (`agents/classifier|extraction|validation|graph_update.py`, all subclassing `agents/base.py` `BaseAgent`) never reference each other; they return pydantic values and the pipeline routes them. Both feedback loops and all their bounds live in `ingest_document()`:
  - Loop 1 (`validation_to_classifier`): classify -> extract -> validate, retried up to `MAX_RECLASSIFY_ATTEMPTS`, with fixpoint detection; always ends with a usable result (missing refs become `MISSING_DEPENDENCY` flags, never a failure).
  - Loop 2 (`graph_update_reinvoke`): case 9 only, depth fixed at 1, fan-out capped by `MAX_IMPACT_DOCS`.
  - `ingest_document` must never raise; exceptions are caught into `IngestionResult.errors`.
- **`schema.py` holds every data shape** (pydantic models, `LifecycleCase`, `GraphOperation`, `normalize_doc_id`). Treat it as a frozen contract shared by all modules.
- **Graph mutation is deterministic, not LLM-driven.** `agents/graph_update.py:build_case_operations()` is a pure function mapping (case, extraction, validation report) -> `GraphOperation`s; it must stay in sync with the README section 5 table and is what `smoke_test.py` checks for all 9 cases. The first op is always `create_document(N)` with the new doc's lineage/flags/notes already baked in. `build_impact_operations()` does the same for loop-2 per-target ops.
- **Two seams** let the rest of the code stay unchanged: `StorageInterface` (ABC in `storage.py`; `InMemoryStorage` is the default, no-setup implementation, and `S3DbStorage` is the real one -- raw text in S3, metadata graph in Postgres per the repo's one shared migration sequence in `../nttbanca-n/migrations/*.sql` (run `make migrate` from the repo root first), `psycopg`/`boto3` lazily imported -- selected via `STORAGE_BACKEND` through `get_storage(settings)`) and `LLMProvider.complete_json(...)` in `llm_provider.py` (`MockProvider` default; `anthropic`/`openai`/`gemini` register in `PROVIDERS` with lazily imported SDKs and JSON-schema-in-the-system-prompt instead of tool use). Agents call the LLM only through `BaseAgent._llm_json`, which validates output against the pydantic model, retries once with the error appended, and writes the `agent_call`/`agent_result` log rows.
- **`logging_trace.py` `InteractionLogger`** writes `runs/<run_id>/interaction_log.jsonl` (the primary evidence artifact; every row has every key, `null` when unused), plus `summary.json` and `storage_snapshot.json` written by `main.py`. `runs/` is gitignored and a fresh directory is created per invocation.
- **`config.py` `Settings`** is a frozen dataclass built by `Settings.from_env()` (loads `.env`); CLI flags override env, `None` overrides are ignored. API keys are read inside provider classes, not in `Settings`.

## Gotchas

- `ingest_document` resets `self.logger._doc_id = None` directly because `set_context()` ignores `None`; keep that reset or a previous document's id leaks onto the next document's early log rows.
- Duplicate doc ids are disambiguated with `-DUP{n}` in `_assign_doc_id`, not rejected.
- Directory ingestion is lexicographic and shares one storage across the run, so sample files are numbered (`01_`, `02_`, ...) to control order; later documents can cite earlier ones.
- `MockProvider` is keyword/regex heuristics keyed off a first line `ID: <doc_id>` and an ISO date in the text; it exists to exercise all 9 cases and both loops offline. Changing mock heuristics can break `smoke_test.py`'s end-to-end check (`test_ingest_examples`).
- `.pdf` inputs are skipped with a logged error unless `pdfplumber` is installed.
- The sample regulatory documents are in Spanish; the README and code identifiers are English.
- `.omc/` (gitignored) holds planning artifacts (`.omc/plans/autopilot-impl.md`) that code docstrings reference by section number; it may not exist in a fresh checkout.
