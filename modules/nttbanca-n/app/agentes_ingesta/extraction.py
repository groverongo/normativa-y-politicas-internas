"""ExtractionAgent: pulls structured metadata and case-specific fields out of
an incoming document's text, and summarizes a target document's usage of a
redefined term for loop 2 (case 9 re-invocation). Ported verbatim from
modules/ingesta/agents/extraction.py.
"""
from __future__ import annotations

from pathlib import Path

from app.models.enums import DocStatus
from app.schemas.lifecycle import (
    CatalogEntry,
    ClassificationResult,
    ExtractionResult,
    LifecycleCase,
    ReinvocationRequest,
    TermUsage,
    normalize_doc_id,
)

from .base import BaseAgent, render_catalog_tag, render_document_tag

SYSTEM_PROMPT = (
    "You are the Extraction agent in a regulatory-document ingestion pipeline. "
    "Given the text of an incoming document, its already-decided lifecycle "
    "case, and a catalog of existing documents, extract structured metadata: "
    "identity (doc id, title, issuer, doc type, defined/referenced terms), "
    "the target documents this one acts upon (target_doc_ids), the effective "
    "date, and the case-specific fields requested below. "
    "When citing an existing document, use the exact doc_id from <catalog>. "
    "Respond with ONLY a JSON object matching the given JSON Schema."
)

_CASE_INSTRUCTIONS: dict[LifecycleCase, str] = {
    LifecycleCase.REPLACEMENT_WITH_CONTRADICTION: (
        "Case REPLACEMENT_WITH_CONTRADICTION: set contradiction_scope to "
        "'total' or 'partial', and list the specific contradicted points in "
        "contradiction_notes."
    ),
    LifecycleCase.REVOCATION_OR_EXPIRATION: (
        "Case REVOCATION_OR_EXPIRATION: set revocation_kind to 'revocation' "
        "or 'expiration'."
    ),
    LifecycleCase.PATCH_ERRATUM: (
        "Case PATCH_ERRATUM: fill `patches` with one PatchRecord per "
        "correction (clause, old_text, new_text)."
    ),
    LifecycleCase.TEMPORARY_EXCEPTION: (
        "Case TEMPORARY_EXCEPTION: metadata.lifecycle_metadata.valid_until is "
        "REQUIRED -- extract the end date of the exception window."
    ),
    LifecycleCase.INDIRECT_DEPENDENCY_UPDATE: (
        "Case INDIRECT_DEPENDENCY_UPDATE: fill `redefined_terms` with each "
        "term and its new definition."
    ),
}


class ExtractionAgent(BaseAgent):
    name = "extraction"

    def extract(
        self,
        doc_text: str,
        source_name: str,
        classification: ClassificationResult,
        catalog: list[CatalogEntry],
    ) -> ExtractionResult:
        parts = [
            f"Lifecycle case (already decided): {classification.case.value}",
            "When citing an existing document, use the exact doc_id from <catalog>.",
        ]
        extra = _CASE_INSTRUCTIONS.get(classification.case)
        if extra:
            parts.append(extra)
        parts.append(render_document_tag(doc_text))
        parts.append(render_catalog_tag(catalog))
        user_prompt = "\n\n".join(parts)

        result = self._llm_json(
            task="extract",
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_model=ExtractionResult,
            context={
                "document_text": doc_text,
                "case": classification.case.value,
                "source_name": source_name,
                "catalog_ids": [entry.doc_id for entry in catalog],
            },
            attempt=classification.attempt,
        )

        ident = result.metadata.identity_metadata
        if not ident.doc_id:
            ident.doc_id = normalize_doc_id(Path(source_name).stem)
        # The incoming document is always ACTIVE at the moment of ingestion.
        result.metadata.lifecycle_metadata.status = DocStatus.ACTIVE
        return result

    def extract_term_usage(self, request: ReinvocationRequest, target_text: str) -> TermUsage:
        user_prompt = (
            f"Term: \"{request.term}\"\n"
            f"Target document id: {request.target_doc_id}\n"
            + render_document_tag(target_text)
            + "\n\nList the clauses/sentences in this document that use the "
              "term. Respond with ONLY a JSON object matching the given "
              "JSON Schema."
        )
        result = self._llm_json(
            task="extract_term_usage",
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_model=TermUsage,
            context={
                "term": request.term,
                "target_doc_id": request.target_doc_id,
                "target_text": target_text,
            },
            doc_id=request.target_doc_id,
            loop="graph_update_reinvoke",
        )
        result.target_doc_id = request.target_doc_id
        result.term = request.term
        return result
