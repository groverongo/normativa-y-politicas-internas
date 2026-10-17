"""ClassifierAgent: decides the lifecycle case for an incoming document, and
assesses whether a redefined term affects an existing document (loop 2).
Ported verbatim from modules/ingesta/agents/classifier.py.
"""
from __future__ import annotations

from app.schemas.lifecycle import (
    CASE_DESCRIPTIONS,
    CatalogEntry,
    ClassificationResult,
    DocumentMetadata,
    FeedbackMessage,
    ImpactAssessment,
    ReinvocationRequest,
)

from .base import BaseAgent, render_catalog_tag, render_document_tag, render_feedback_tag

SYSTEM_PROMPT = (
    "You are the Classifier agent in a regulatory-document ingestion pipeline. "
    "You decide which of 9 lifecycle cases an incoming document represents, "
    "and you list any existing document ids the document's text appears to "
    "cite (as written in the text; use the exact doc_id from <catalog> when "
    "the citation matches a cataloged document). "
    "Respond with ONLY a JSON object matching the given JSON Schema."
)


def _case_descriptions_block() -> str:
    lines = ["Lifecycle cases (pick exactly one):"]
    for case, desc in CASE_DESCRIPTIONS.items():
        lines.append(f"- {case.value}: {desc}")
    return "\n".join(lines)


class ClassifierAgent(BaseAgent):
    name = "classifier"

    def classify(
        self,
        doc_text: str,
        source_name: str,
        catalog: list[CatalogEntry],
        feedback: FeedbackMessage | None = None,
        attempt: int = 0,
    ) -> ClassificationResult:
        parts = [
            _case_descriptions_block(),
            f"Source file name: {source_name}",
            render_document_tag(doc_text),
            render_catalog_tag(catalog),
        ]
        if feedback is not None:
            parts.append(
                "RECONSIDER: a previous classification of this document was "
                "rejected by the validation agent. Reconsider the case in "
                "light of this feedback before answering again.\n"
                f"- prior case: {feedback.payload.get('prior_case')}\n"
                f"- missing references: {feedback.payload.get('missing_refs')}\n"
                f"- structural issues: {feedback.payload.get('structural_issues')}\n"
                f"- validator hypothesis: {feedback.content}\n"
                + render_feedback_tag(feedback)
            )
        user_prompt = "\n\n".join(parts)

        result = self._llm_json(
            task="classify",
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_model=ClassificationResult,
            context={
                "document_text": doc_text,
                "catalog_ids": [entry.doc_id for entry in catalog],
                "feedback": feedback.model_dump(mode="json") if feedback is not None else None,
            },
            attempt=attempt,
        )
        # The LLM does not set `attempt`; the agent does.
        result.attempt = attempt
        return result

    def assess_impact(
        self,
        request: ReinvocationRequest,
        target_text: str,
        target_meta: DocumentMetadata,
    ) -> ImpactAssessment:
        user_prompt = (
            f"Term redefined: \"{request.term}\"\n"
            f"New definition (from {request.source_doc_id}): {request.new_definition}\n"
            f"Target document id: {request.target_doc_id}\n"
            f"Target document title: {target_meta.identity_metadata.title}\n"
            + render_document_tag(target_text)
            + "\n\nDoes this target document's use of the term make it affected "
              "by the redefinition? Respond with ONLY a JSON object matching "
              "the given JSON Schema."
        )
        result = self._llm_json(
            task="assess_impact",
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_model=ImpactAssessment,
            context={
                "term": request.term,
                "new_definition": request.new_definition,
                "target_doc_id": request.target_doc_id,
                "target_text": target_text,
            },
            doc_id=request.target_doc_id,
            loop="graph_update_reinvoke",
        )
        # These are facts of the request, not LLM guesses; keep them authoritative.
        result.target_doc_id = request.target_doc_id
        result.term = request.term
        return result
