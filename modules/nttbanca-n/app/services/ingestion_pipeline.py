"""IngestionPipeline: mediator that wires the 4 ingestion agents and owns
both feedback loops. Ported from modules/ingesta/pipeline.py's
IngestionPipeline.ingest_document(); ingest_path()/load_document_text() are
dropped (CLI/file concerns, not needed for an HTTP-only service -- see
app/api/routes/ingest.py for the HTTP entry points instead).

Agents never hold references to each other: this module is the mediator and
routes FeedbackMessages, enforcing every loop bound in one place.
"""
from __future__ import annotations

from app.agentes_ingesta import ClassifierAgent, ExtractionAgent, GraphUpdateAgent, ValidationAgent
from app.core.config import Settings
from app.schemas.lifecycle import (
    ExtractionResult,
    FeedbackMessage,
    IngestionResult,
    LifecycleCase,
    normalize_doc_id,
)
from app.services.document_graph_storage import DocumentGraphStorage
from app.services.ingestion_logger import InteractionLogger
from app.services.llm_provider import LLMProvider


class IngestionPipeline:
    """Drives Classifier -> Extraction -> Validation -> Graph-Update for a
    single document, including the two bounded feedback loops."""

    def __init__(
        self,
        storage: DocumentGraphStorage,
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
        from pathlib import Path

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

        # Reset the logger's per-document doc_id context so a stale doc_id
        # from a previously ingested document in this run doesn't leak onto
        # this document's early log rows.
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
