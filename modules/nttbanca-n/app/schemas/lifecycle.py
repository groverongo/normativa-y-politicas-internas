"""Pydantic contracts for the ingestion pipeline (Classifier/Extraction/
Validation/Graph-Update agents), ported verbatim from modules/ingesta/schema.py.

This is the single collision point for the new ingestion feature: every
agent, the pipeline, and app/services/document_graph_storage.py code against
the models and enums defined here. Field names are kept identical to
modules/ingesta/schema.py -- do not rename.
"""
from __future__ import annotations

import re
import unicodedata
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.enums import DocStatus

__all__ = [
    "LifecycleCase",
    "CASE_NUMBER",
    "CASE_DESCRIPTIONS",
    "CASES_REQUIRING_TARGETS",
    "DocStatus",
    "IdentityMetadata",
    "PatchRecord",
    "LifecycleMetadata",
    "LineageMetadata",
    "DocumentMetadata",
    "Chunk",
    "StoredDocument",
    "CatalogEntry",
    "ClassificationResult",
    "TermDefinition",
    "ExtractionResult",
    "ValidationJudgement",
    "ValidationReport",
    "FeedbackMessage",
    "GraphOperation",
    "GraphUpdateRationale",
    "GraphUpdatePlan",
    "ReinvocationRequest",
    "ImpactAssessment",
    "TermUsage",
    "IngestionResult",
    "normalize_doc_id",
]


# ---------------------------------------------------------------------------
# Lifecycle cases
# ---------------------------------------------------------------------------

class LifecycleCase(str, Enum):
    NEW_STATEMENT = "NEW_STATEMENT"
    FULL_REPLACEMENT = "FULL_REPLACEMENT"
    REPLACEMENT_WITH_CONTRADICTION = "REPLACEMENT_WITH_CONTRADICTION"
    REVOCATION_OR_EXPIRATION = "REVOCATION_OR_EXPIRATION"
    CONSOLIDATION = "CONSOLIDATION"
    SPLITTING = "SPLITTING"
    PATCH_ERRATUM = "PATCH_ERRATUM"
    TEMPORARY_EXCEPTION = "TEMPORARY_EXCEPTION"
    INDIRECT_DEPENDENCY_UPDATE = "INDIRECT_DEPENDENCY_UPDATE"


CASE_NUMBER: dict[LifecycleCase, int] = {
    LifecycleCase.NEW_STATEMENT: 1,
    LifecycleCase.FULL_REPLACEMENT: 2,
    LifecycleCase.REPLACEMENT_WITH_CONTRADICTION: 3,
    LifecycleCase.REVOCATION_OR_EXPIRATION: 4,
    LifecycleCase.CONSOLIDATION: 5,
    LifecycleCase.SPLITTING: 6,
    LifecycleCase.PATCH_ERRATUM: 7,
    LifecycleCase.TEMPORARY_EXCEPTION: 8,
    LifecycleCase.INDIRECT_DEPENDENCY_UPDATE: 9,
}

CASE_DESCRIPTIONS: dict[LifecycleCase, str] = {
    LifecycleCase.NEW_STATEMENT: (
        "New statement (nuevo documento): a brand-new document with no relation to "
        "any existing document in the corpus. No prior document is cited as being "
        "replaced, amended, revoked, consolidated, or split. "
        "ES keywords: 'nuevo reglamento', 'se establece', 'se crea', 'aprueba'."
    ),
    LifecycleCase.FULL_REPLACEMENT: (
        "Full replacement / new version (sustitucion): this document completely "
        "replaces one or more prior documents, which should no longer be used. "
        "ES keywords: 'sustituye', 'reemplaza', 'nueva version de', 'deja sin efecto "
        "y sustituye'."
    ),
    LifecycleCase.REPLACEMENT_WITH_CONTRADICTION: (
        "Replacement with contradiction: this document replaces or overrides a "
        "prior document AND explicitly contradicts it (partially or totally) rather "
        "than cleanly updating it. "
        "ES keywords: 'contradice', 'en sentido contrario a', 'deja sin efecto el "
        "criterio establecido en', 'se aparta de lo dispuesto en'."
    ),
    LifecycleCase.REVOCATION_OR_EXPIRATION: (
        "Full revocation or expiration (derogacion total / caducidad): a document "
        "is completely retired, annulled, or reaches its expiration date, with no "
        "replacement document issued. "
        "ES keywords: 'deroga', 'queda sin efecto', 'caduca', 'pierde vigencia'."
    ),
    LifecycleCase.CONSOLIDATION: (
        "Consolidation (fusion / Texto Unico Ordenado - TUO): multiple scattered "
        "documents are merged into one comprehensive manual or master document "
        "(many-to-one). "
        "ES keywords: 'texto unico ordenado', 'TUO', 'consolida', 'fusiona', "
        "'refunde en un solo texto'."
    ),
    LifecycleCase.SPLITTING: (
        "Splitting / fragmentation (escision): a broad document is deprecated and "
        "split into several highly specific documents (one-to-many). "
        "ES keywords: 'se escinde', 'se divide en', 'se desagrega en', 'fracciona'."
    ),
    LifecycleCase.PATCH_ERRATUM: (
        "Minor patch / erratum (fe de erratas / modificatoria menor): a document is "
        "published purely to fix a typo, update a specific threshold, or clarify a "
        "single clause, without replacing the whole parent document. "
        "ES keywords: 'fe de erratas', 'modifica el articulo', 'se corrige', "
        "'precisa que'."
    ),
    LifecycleCase.TEMPORARY_EXCEPTION: (
        "Temporary exception (regimen de excepcion temporal): a document establishes "
        "a time-bounded rule that overrides an existing policy for a specific "
        "timeframe, after which the original rule applies again. "
        "ES keywords: 'regimen de excepcion', 'de manera temporal', 'hasta el', "
        "'mientras dure el estado de emergencia'."
    ),
    LifecycleCase.INDIRECT_DEPENDENCY_UPDATE: (
        "Indirect dependency update (impacto cruzado): a document redefines a core "
        "term or concept used by other, unrelated documents, changing how those "
        "other documents should be interpreted without replacing them. "
        "ES keywords: 'para efectos de', 'se entiende por', 'redefine el concepto "
        "de', 'nueva definicion de'."
    ),
}

CASES_REQUIRING_TARGETS: frozenset[LifecycleCase] = frozenset(
    {
        LifecycleCase.FULL_REPLACEMENT,
        LifecycleCase.REPLACEMENT_WITH_CONTRADICTION,
        LifecycleCase.REVOCATION_OR_EXPIRATION,
        LifecycleCase.CONSOLIDATION,
        LifecycleCase.SPLITTING,
        LifecycleCase.PATCH_ERRATUM,
        LifecycleCase.TEMPORARY_EXCEPTION,
    }
)


# ---------------------------------------------------------------------------
# Metadata schema
# ---------------------------------------------------------------------------

class IdentityMetadata(BaseModel):
    doc_id: str
    chunk_index: int = 0
    doc_type: str = "unknown"
    title: str = ""
    issuer: str = ""
    topic_tags: list[str] = Field(default_factory=list)
    defined_terms: list[str] = Field(default_factory=list)
    referenced_terms: list[str] = Field(default_factory=list)
    source_uri: str | None = None


class PatchRecord(BaseModel):
    clause: str
    old_text: str = ""
    new_text: str = ""
    patched_by: str | None = None
    effective_date: str | None = None


class LifecycleMetadata(BaseModel):
    status: DocStatus = DocStatus.ACTIVE
    valid_from: str | None = None
    valid_until: str | None = None
    version: str | None = None
    review_flags: list[str] = Field(default_factory=list)
    missing_dependencies: list[str] = Field(default_factory=list)
    patch_log: list[PatchRecord] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class LineageMetadata(BaseModel):
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: list[str] = Field(default_factory=list)
    amends: list[str] = Field(default_factory=list)
    patched_by: list[str] = Field(default_factory=list)
    consolidates: list[str] = Field(default_factory=list)
    split_from: list[str] = Field(default_factory=list)
    split_into: list[str] = Field(default_factory=list)
    contradicts: list[str] = Field(default_factory=list)
    revokes: list[str] = Field(default_factory=list)
    revoked_by: list[str] = Field(default_factory=list)
    overrides: list[str] = Field(default_factory=list)
    overridden_by: list[str] = Field(default_factory=list)
    impacts: list[str] = Field(default_factory=list)
    definition_sources: dict[str, str] = Field(default_factory=dict)


class DocumentMetadata(BaseModel):
    identity_metadata: IdentityMetadata
    lifecycle_metadata: LifecycleMetadata = Field(default_factory=LifecycleMetadata)
    lineage_metadata: LineageMetadata = Field(default_factory=LineageMetadata)

    @property
    def doc_id(self) -> str:
        return self.identity_metadata.doc_id


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    chunk_index: int
    text: str
    metadata: DocumentMetadata


class StoredDocument(BaseModel):
    metadata: DocumentMetadata
    raw_text: str


class CatalogEntry(BaseModel):
    doc_id: str
    title: str
    doc_type: str
    status: DocStatus
    valid_from: str | None = None
    valid_until: str | None = None
    defined_terms: list[str] = Field(default_factory=list)
    topic_tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent I/O
# ---------------------------------------------------------------------------

class ClassificationResult(BaseModel):
    case: LifecycleCase
    confidence: float = 0.5
    rationale: str = ""
    candidate_references: list[str] = Field(default_factory=list)
    attempt: int = 0


class TermDefinition(BaseModel):
    term: str
    definition: str = ""


class ExtractionResult(BaseModel):
    metadata: DocumentMetadata
    target_doc_ids: list[str] = Field(default_factory=list)
    effective_date: str | None = None
    contradiction_scope: Literal["none", "partial", "total"] = "none"
    contradiction_notes: list[str] = Field(default_factory=list)
    revocation_kind: Literal["revocation", "expiration"] | None = None
    patches: list[PatchRecord] = Field(default_factory=list)
    redefined_terms: list[TermDefinition] = Field(default_factory=list)


class ValidationJudgement(BaseModel):
    recommendation: Literal["proceed", "reclassify", "proceed_with_missing_dependency"]
    reasoning: str = ""
    feedback_hint: str = ""


class ValidationReport(BaseModel):
    ok: bool
    resolved_refs: dict[str, str] = Field(default_factory=dict)
    missing_refs: list[str] = Field(default_factory=list)
    structural_issues: list[str] = Field(default_factory=list)
    recommendation: Literal["proceed", "reclassify", "proceed_with_missing_dependency"]
    reasoning: str = ""
    feedback_hint: str = ""
    attempt: int = 0


class FeedbackMessage(BaseModel):
    from_agent: str
    to_agent: str
    loop: Literal["validation_to_classifier", "graph_update_reinvoke"]
    iteration: int
    kind: str
    content: str
    payload: dict[str, Any] = Field(default_factory=dict)


OpName = Literal[
    "create_document",
    "set_status",
    "set_lifecycle_field",
    "append_lineage",
    "append_patch",
    "add_review_flag",
    "set_definition_source",
]


class GraphOperation(BaseModel):
    op: OpName
    doc_id: str
    field: str | None = None
    value: Any = None
    reason: str = ""


class GraphUpdateRationale(BaseModel):
    rationale: str = ""
    impact_terms: list[TermDefinition] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class GraphUpdatePlan(BaseModel):
    case: LifecycleCase
    new_doc_id: str
    operations: list[GraphOperation] = Field(default_factory=list)
    rationale: str = ""
    impact_terms: list[TermDefinition] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReinvocationRequest(BaseModel):
    source_doc_id: str
    target_doc_id: str
    term: str
    new_definition: str = ""


class ImpactAssessment(BaseModel):
    target_doc_id: str
    term: str
    affected: bool
    rationale: str = ""


class TermUsage(BaseModel):
    target_doc_id: str
    term: str
    clauses: list[str] = Field(default_factory=list)


class IngestionResult(BaseModel):
    source_file: str
    doc_id: str | None = None
    final_case: LifecycleCase | None = None
    classification_history: list[LifecycleCase] = Field(default_factory=list)
    reclassify_iterations: int = 0
    missing_dependencies: list[str] = Field(default_factory=list)
    operations_applied: int = 0
    impacted_docs: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STRIP_TOKENS = re.compile(r"\b(N°|Nº|NO\.|NUM\.|NUMERO)\b", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


def normalize_doc_id(raw: str) -> str:
    """Uppercase, strip accents, drop ordinal/number markers, collapse separators.

    Example: "Circular N° G-219-2023" -> "CIRCULAR-G-219-2023"
    """
    if raw is None:
        return ""
    text = unicodedata.normalize("NFKD", raw)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper()
    text = _STRIP_TOKENS.sub(" ", text)
    text = _NON_ALNUM.sub("-", text)
    return text.strip("-")
