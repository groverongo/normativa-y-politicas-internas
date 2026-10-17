"""Orchestrator: IngestionPipeline wires the 4 agents and owns both feedback loops.

Per the implementation plan (.omc/plans/autopilot-impl.md, section 0 "Agent
wiring"): agents never hold references to each other. This module is the
mediator/message bus. It routes FeedbackMessages and enforces every loop
bound in one place (section 4).
"""
from __future__ import annotations

from pathlib import Path

from agents import ClassifierAgent, ExtractionAgent, GraphUpdateAgent, ValidationAgent
from config import Settings
from llm_provider import LLMProvider
from logging_trace import InteractionLogger
from schema import (
    ExtractionResult,
    FeedbackMessage,
    IngestionResult,
    LifecycleCase,
    normalize_doc_id,
)
from storage import StorageInterface

_TEXT_SUFFIXES = (".txt", ".md")
_PDF_SUFFIX = ".pdf"


def load_document_text(path: Path) -> str:
    """Read a document's raw text.

    .txt/.md are read as utf-8. .pdf is read lazily via pdfplumber if it is
    installed. The caller (IngestionPipeline.ingest_path) is responsible for
    checking pdfplumber's availability ahead of time and skipping+logging
    when it is not importable; this function does not swallow that error.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == _PDF_SUFFIX:
        import pdfplumber  # lazy import; see ingest_path for the skip-and-log path

        parts: list[str] = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
        return "\n\n".join(parts)
    # .txt/.md and anything else: best-effort utf-8 text read.
    return path.read_text(encoding="utf-8")


class IngestionPipeline:
    """Mediator that drives Classifier -> Extraction -> Validation -> Graph-Update
    for a single document, including the two bounded feedback loops in section 4.
    """

    def __init__(
        self,
        storage: StorageInterface,
        llm: LLMProvider,
        logger: InteractionLogger,
        settings: Settings,
    ) -> None:
        self.storage = storage
        self.llm = llm
        self.logger = logger
        self.settings = settings
        self.classifier = ClassifierAgent(llm, storage, logger, settings)
        self.extraction = ExtractionAgent(llm, storage, logger, settings)
        self.validation = ValidationAgent(llm, storage, logger, settings)
        self.graph_update = GraphUpdateAgent(llm, storage, logger, settings)

    # ------------------------------------------------------------------
    def _assign_doc_id(self, extraction: ExtractionResult, source_name: str) -> str:
        """Normalize the extracted doc id; disambiguate collisions with -DUP{n}."""
        raw_id = extraction.metadata.identity_metadata.doc_id or Path(source_name).stem
        doc_id = normalize_doc_id(raw_id) or normalize_doc_id(Path(source_name).stem)
        if not self.storage.check_document_exists(doc_id):
            extraction.metadata.identity_metadata.doc_id = doc_id
            return doc_id
        n = 2
        candidate = f"{doc_id}-DUP{n}"
        while self.storage.check_document_exists(candidate):
            n += 1
            candidate = f"{doc_id}-DUP{n}"
        self.logger.log(
            "loop_decision",
            agent="pipeline",
            message=f"doc_id {doc_id!r} already exists in storage; assigned {candidate!r} instead",
            input={"source_name": source_name, "original_doc_id": doc_id, "assigned_doc_id": candidate},
        )
        extraction.metadata.identity_metadata.doc_id = candidate
        return candidate

    # ------------------------------------------------------------------
    def ingest_document(self, text: str, source_name: str) -> IngestionResult:
        """Run one document through both feedback loops. Never raises."""
        result = IngestionResult(source_file=source_name)

        # Reset the logger's per-document doc_id context. set_context() only
        # ever *sets* doc_id (it ignores None), so a stale doc_id left over
        # from a previously ingested document in this run would otherwise
        # leak onto this document's early log rows (document_start and the
        # first classify/extract agent_call rows, before _assign_doc_id runs).
        self.logger._doc_id = None
        self.logger.set_context(source_file=source_name)
        self.logger.log("document_start", agent="pipeline", message=f"ingesting {source_name}")

        try:
            catalog = self.storage.catalog()
            feedback: FeedbackMessage | None = None
            history: list[LifecycleCase] = []
            prev_sig = None
            cls = None
            ext = None
            rep = None
            new_id: str | None = None
            final_attempt = 0

            # ---- Loop 1: Validation -> Classifier (bounded reclassification) ----
            for attempt in range(self.settings.max_reclassify_attempts + 1):
                final_attempt = attempt
                cls = self.classifier.classify(text, source_name, catalog, feedback, attempt)
                ext = self.extraction.extract(text, source_name, cls, catalog)
                new_id = self._assign_doc_id(ext, source_name)
                self.logger.set_context(doc_id=new_id)
                rep = self.validation.validate(cls, ext, attempt)
                history.append(cls.case)

                if rep.ok:
                    self.logger.log(
                        "loop_decision",
                        agent="pipeline",
                        message="validation passed",
                        attempt=attempt,
                        doc_id=new_id,
                    )
                    break

                sig = (cls.case, tuple(sorted(rep.missing_refs)), tuple(sorted(rep.structural_issues)))
                if attempt == self.settings.max_reclassify_attempts or sig == prev_sig:
                    reason = (
                        "budget exhausted"
                        if attempt == self.settings.max_reclassify_attempts
                        else "no progress (fixpoint)"
                    )
                    self.logger.log(
                        "loop_decision",
                        agent="pipeline",
                        loop="validation_to_classifier",
                        message=f"{reason} -> proceed_with_missing_dependency",
                        attempt=attempt,
                        doc_id=new_id,
                    )
                    rep.recommendation = "proceed_with_missing_dependency"
                    break

                feedback = self.validation.build_feedback(rep, cls, iteration=attempt + 1)
                self.logger.feedback(feedback, doc_id=new_id)
                prev_sig = sig

            result.classification_history = history
            result.reclassify_iterations = final_attempt
            result.doc_id = new_id
            result.final_case = cls.case if cls is not None else None
            result.missing_dependencies = list(rep.missing_refs) if rep is not None else []

            # ---- Graph-Update: apply the deterministic case operations ----
            plan = self.graph_update.plan(cls, ext, rep, new_id, text)
            applied = self.graph_update.apply(plan)

            # ---- Loop 2: Graph-Update -> Classifier/Extraction re-invocation ----
            impacted: list[str] = []
            if cls.case == LifecycleCase.INDIRECT_DEPENDENCY_UPDATE and self.settings.max_cascade_depth >= 1:
                terms = plan.impact_terms or ext.redefined_terms
                requests = self.graph_update.find_impact_targets(new_id, terms, exclude={new_id})
                if not requests:
                    self.logger.log(
                        "loop_decision",
                        agent="graph_update",
                        loop="graph_update_reinvoke",
                        message="no active documents reference the redefined term(s)",
                        doc_id=new_id,
                    )
                for i, req in enumerate(requests, 1):
                    self.logger.feedback(
                        FeedbackMessage(
                            from_agent="graph_update",
                            to_agent="classifier",
                            loop="graph_update_reinvoke",
                            iteration=i,
                            kind="impact_reassessment",
                            content=f"'{req.term}' redefined by {new_id}; reassess {req.target_doc_id}",
                            payload=req.model_dump(),
                        ),
                        doc_id=new_id,
                    )
                    target_text = self.storage.get_document_text(req.target_doc_id) or ""
                    target_meta = self.storage.get_document(req.target_doc_id)
                    assess = self.classifier.assess_impact(req, target_text, target_meta)
                    usage = (
                        self.extraction.extract_term_usage(req, target_text)
                        if assess.affected
                        else None
                    )
                    self.logger.feedback(
                        FeedbackMessage(
                            from_agent="extraction" if usage else "classifier",
                            to_agent="graph_update",
                            loop="graph_update_reinvoke",
                            iteration=i,
                            kind="impact_result",
                            content=assess.rationale,
                            payload={
                                "assessment": assess.model_dump(),
                                "usage": usage.model_dump() if usage else None,
                            },
                        ),
                        doc_id=new_id,
                    )
                    applied += self.graph_update.apply_impact(req, assess, usage)
                    if assess.affected:
                        impacted.append(req.target_doc_id)

            result.operations_applied = applied
            result.impacted_docs = impacted

        except Exception as exc:  # pipeline must never raise
            result.errors.append(f"{type(exc).__name__}: {exc}")
            self.logger.log(
                "error",
                agent="pipeline",
                message=f"{type(exc).__name__}: {exc}",
                doc_id=result.doc_id,
            )
        finally:
            self.logger.log(
                "document_end",
                agent="pipeline",
                message=f"final_case={result.final_case}; errors={len(result.errors)}",
                doc_id=result.doc_id,
            )

        return result

    # ------------------------------------------------------------------
    def ingest_path(self, path: Path) -> list[IngestionResult]:
        """Ingest a single file, or every *.txt/*.md/*.pdf in a directory.

        Uses one shared `self.storage` across every document in the run, so
        later documents can reference earlier ones (and earlier case-9 docs
        can be found by later impact-target lookups).
        """
        path = Path(path)
        if path.is_file():
            files = [path]
        else:
            files = sorted(
                list(path.glob("*.txt")) + list(path.glob("*.md")) + list(path.glob("*.pdf"))
            )

        self.logger.log(
            "run_start",
            agent="pipeline",
            message=f"ingesting {len(files)} file(s) from {path}",
            input={"path": str(path), "files": [str(f) for f in files]},
        )

        results: list[IngestionResult] = []
        for f in files:
            if f.suffix.lower() == _PDF_SUFFIX:
                try:
                    import pdfplumber  # noqa: F401
                except ImportError:
                    msg = f"pdfplumber is not installed; skipping {f}"
                    self.logger.log("error", agent="pipeline", message=msg, input={"path": str(f)})
                    results.append(IngestionResult(source_file=str(f), errors=[msg]))
                    continue
            try:
                text = load_document_text(f)
            except Exception as exc:
                msg = f"failed to read {f}: {type(exc).__name__}: {exc}"
                self.logger.log("error", agent="pipeline", message=msg, input={"path": str(f)})
                results.append(IngestionResult(source_file=str(f), errors=[msg]))
                continue
            results.append(self.ingest_document(text, str(f)))

        self.logger.log(
            "run_end",
            agent="pipeline",
            message=f"processed {len(results)} document(s)",
            output={
                "count": len(results),
                "documents_with_errors": sum(1 for r in results if r.errors),
            },
        )
        return results
