"""Storage adapter for the ingestion pipeline's document-lifecycle graph.

Implements the same method contract as modules/ingesta/storage.py's
StorageInterface, but backed by a SQLAlchemy Session against the ORM models
in app/models/document.py, instead of ingesta's raw-psycopg S3DbStorage --
this keeps one DB-access style in the service (the existing app/crud/*.py
files are the precedent). chunk_text() and apply_operation()'s dispatch
logic are ported verbatim (pure functions, no I/O).
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import (
    Document,
    DocumentChunk,
    DocumentDefinitionSource,
    DocumentLineage,
    DocumentPatchRecord,
)
from app.models.enums import DocStatus
from app.schemas.lifecycle import (
    CatalogEntry,
    DocumentMetadata,
    GraphOperation,
    IdentityMetadata,
    LifecycleMetadata,
    LineageMetadata,
    PatchRecord,
    StoredDocument,
    normalize_doc_id,
)

_NUM_YEAR = re.compile(r"(\d+)-(\d{4})")

_LINEAGE_FIELDS: tuple[str, ...] = (
    "supersedes", "superseded_by", "amends", "patched_by", "consolidates",
    "split_from", "split_into", "contradicts", "revokes", "revoked_by",
    "overrides", "overridden_by", "impacts",
)
_LIFECYCLE_SCALAR_FIELDS = {"valid_from", "valid_until", "version"}
_LIFECYCLE_JSON_LIST_FIELDS = {"review_flags", "missing_dependencies", "notes"}


class StorageError(RuntimeError):
    """Raised for any DocumentGraphStorage operation failure."""


def chunk_text(text: str, max_chars: int = 1500) -> list[str]:
    """Paragraph-greedy splitter: pack paragraphs into chunks up to max_chars."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return [text] if text.strip() else []
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) > max_chars and current:
            chunks.append(current)
            current = para
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


class DocumentGraphStorage:
    """SQLAlchemy-backed implementation of ingesta's StorageInterface contract."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- reads ----
    def check_document_exists(self, doc_id: str) -> bool:
        return self.db.get(Document, doc_id) is not None

    def resolve_doc_id(self, raw_ref: str) -> str | None:
        normalized = normalize_doc_id(raw_ref)
        if self.check_document_exists(normalized):
            return normalized
        match = _NUM_YEAR.search(raw_ref)
        if not match:
            return None
        core = f"{match.group(1)}-{match.group(2)}"
        stmt = select(Document.doc_id).where(Document.doc_id.like(f"%{core}"))
        candidates = list(self.db.scalars(stmt))
        return candidates[0] if len(candidates) == 1 else None

    def get_document(self, doc_id: str) -> DocumentMetadata | None:
        return self._load_metadata(doc_id)

    def get_document_text(self, doc_id: str) -> str | None:
        row = self.db.get(Document, doc_id)
        return row.raw_text if row is not None else None

    def list_documents(self, status: DocStatus | None = None) -> list[DocumentMetadata]:
        stmt = select(Document.doc_id)
        if status is not None:
            stmt = stmt.where(Document.status == status.value)
        doc_ids = list(self.db.scalars(stmt))
        docs = (self._load_metadata(doc_id) for doc_id in doc_ids)
        return [doc for doc in docs if doc is not None]

    def catalog(self) -> list[CatalogEntry]:
        entries = []
        for meta in self.list_documents():
            ident = meta.identity_metadata
            life = meta.lifecycle_metadata
            entries.append(
                CatalogEntry(
                    doc_id=ident.doc_id,
                    title=ident.title,
                    doc_type=ident.doc_type,
                    status=life.status,
                    valid_from=life.valid_from,
                    valid_until=life.valid_until,
                    defined_terms=list(ident.defined_terms),
                    topic_tags=list(ident.topic_tags),
                )
            )
        return sorted(entries, key=lambda e: e.doc_id)

    def find_active_documents_referencing_term(
        self, term: str, exclude: Iterable[str] = ()
    ) -> list[str]:
        exclude_set = set(exclude)
        term_lower = term.lower()
        stmt = select(Document).where(Document.status == DocStatus.ACTIVE.value)
        matches: list[str] = []
        for row in self.db.scalars(stmt):
            if row.doc_id in exclude_set:
                continue
            referenced = [t.lower() for t in (row.referenced_terms or [])]
            if term_lower in referenced or term_lower in (row.raw_text or "").lower():
                matches.append(row.doc_id)
        return sorted(matches)

    def _load_metadata(self, doc_id: str) -> DocumentMetadata | None:
        row = self.db.get(Document, doc_id)
        if row is None:
            return None

        lineage_data: dict[str, Any] = {field: [] for field in _LINEAGE_FIELDS}
        lineage_rows = self.db.scalars(
            select(DocumentLineage).where(DocumentLineage.doc_id == doc_id)
        )
        for lrow in lineage_rows:
            lineage_data[str(lrow.relation)].append(lrow.target_doc_id)

        definition_rows = self.db.scalars(
            select(DocumentDefinitionSource).where(DocumentDefinitionSource.doc_id == doc_id)
        )
        lineage_data["definition_sources"] = {drow.term: drow.source_doc_id for drow in definition_rows}

        patch_rows = self.db.scalars(
            select(DocumentPatchRecord)
            .where(DocumentPatchRecord.doc_id == doc_id)
            .order_by(DocumentPatchRecord.id)
        )
        patch_log = [
            PatchRecord(
                clause=prow.clause,
                old_text=prow.old_text,
                new_text=prow.new_text,
                patched_by=prow.patched_by,
                effective_date=_date_str(prow.effective_date),
            )
            for prow in patch_rows
        ]

        return DocumentMetadata(
            identity_metadata=IdentityMetadata(
                doc_id=row.doc_id,
                doc_type=row.doc_type,
                title=row.title,
                issuer=row.issuer,
                topic_tags=list(row.topic_tags or []),
                defined_terms=list(row.defined_terms or []),
                referenced_terms=list(row.referenced_terms or []),
                source_uri=None,
            ),
            lifecycle_metadata=LifecycleMetadata(
                status=DocStatus(row.status),
                valid_from=_date_str(row.valid_from),
                valid_until=_date_str(row.valid_until),
                version=row.version,
                review_flags=list(row.review_flags or []),
                missing_dependencies=list(row.missing_dependencies or []),
                patch_log=patch_log,
                notes=list(row.notes or []),
            ),
            lineage_metadata=LineageMetadata(**lineage_data),
        )

    # ---- writes ----
    def put_document(self, metadata: DocumentMetadata, raw_text: str) -> None:
        doc_id = metadata.doc_id
        ident = metadata.identity_metadata
        life = metadata.lifecycle_metadata

        row = Document(
            doc_id=doc_id,
            doc_type=ident.doc_type,
            title=ident.title,
            issuer=ident.issuer,
            raw_text=raw_text,
            status=life.status.value,
            valid_from=_parse_date(life.valid_from),
            valid_until=_parse_date(life.valid_until),
            version=life.version,
            topic_tags=list(ident.topic_tags),
            defined_terms=list(ident.defined_terms),
            referenced_terms=list(ident.referenced_terms),
            review_flags=list(life.review_flags),
            missing_dependencies=list(life.missing_dependencies),
            notes=list(life.notes),
        )
        self.db.add(row)
        self.db.flush()

        pieces = chunk_text(raw_text) or [raw_text]
        for idx, piece in enumerate(pieces):
            self.db.add(DocumentChunk(chunk_id=f"{doc_id}#{idx}", doc_id=doc_id, chunk_index=idx, text=piece))

        self._write_lineage(doc_id, metadata.lineage_metadata)
        for patch in life.patch_log:
            self._insert_patch(doc_id, patch)
        for term, source_doc_id in metadata.lineage_metadata.definition_sources.items():
            self._upsert_definition_source(doc_id, term, source_doc_id)
        self.db.flush()

    def _write_lineage(self, doc_id: str, lineage: LineageMetadata) -> None:
        existing = {
            (r.relation, r.target_doc_id)
            for r in self.db.scalars(select(DocumentLineage).where(DocumentLineage.doc_id == doc_id))
        }
        for field in _LINEAGE_FIELDS:
            for target in getattr(lineage, field):
                if (field, target) in existing:
                    continue
                self.db.add(DocumentLineage(doc_id=doc_id, relation=field, target_doc_id=target))
                existing.add((field, target))

    def _insert_patch(self, doc_id: str, patch: PatchRecord) -> None:
        self.db.add(
            DocumentPatchRecord(
                doc_id=doc_id,
                clause=patch.clause,
                old_text=patch.old_text,
                new_text=patch.new_text,
                patched_by=patch.patched_by,
                effective_date=_parse_date(patch.effective_date),
            )
        )

    def _upsert_definition_source(self, doc_id: str, term: str, source_doc_id: str) -> None:
        row = self.db.get(DocumentDefinitionSource, {"doc_id": doc_id, "term": term})
        if row is None:
            self.db.add(DocumentDefinitionSource(doc_id=doc_id, term=term, source_doc_id=source_doc_id))
        else:
            row.source_doc_id = source_doc_id

    def update_document_status(
        self, doc_id: str, status: DocStatus, valid_until: str | None = None
    ) -> None:
        row = self.db.get(Document, doc_id)
        if row is None:
            raise KeyError(f"unknown document: {doc_id!r}")
        row.status = status.value
        if valid_until is not None:
            row.valid_until = _parse_date(valid_until)
        self.db.flush()

    def append_lineage(self, doc_id: str, field: str, value: str) -> None:
        exists = self.db.scalar(
            select(DocumentLineage.id).where(
                DocumentLineage.doc_id == doc_id,
                DocumentLineage.relation == field,
                DocumentLineage.target_doc_id == value,
            )
        )
        if exists is None:
            self.db.add(DocumentLineage(doc_id=doc_id, relation=field, target_doc_id=value))
            self.db.flush()

    def set_lifecycle_field(self, doc_id: str, field: str, value: Any) -> None:
        row = self.db.get(Document, doc_id)
        if row is None:
            raise KeyError(f"unknown document: {doc_id!r}")
        if field == "status":
            row.status = DocStatus(value).value
        elif field in ("valid_from", "valid_until"):
            setattr(row, field, _parse_date(value))
        elif field in _LIFECYCLE_SCALAR_FIELDS or field in _LIFECYCLE_JSON_LIST_FIELDS:
            setattr(row, field, value)
        else:
            raise StorageError(f"DocumentGraphStorage.set_lifecycle_field: unsupported field {field!r}")
        self.db.flush()

    def add_review_flag(self, doc_id: str, flag: str) -> None:
        row = self.db.get(Document, doc_id)
        if row is None:
            raise KeyError(f"unknown document: {doc_id!r}")
        flags = list(row.review_flags or [])
        if flag not in flags:
            flags.append(flag)
            row.review_flags = flags
            self.db.flush()

    def append_patch_metadata(self, doc_id: str, patch: PatchRecord) -> None:
        if self.db.get(Document, doc_id) is None:
            raise KeyError(f"unknown document: {doc_id!r}")
        self._insert_patch(doc_id, patch)
        if patch.patched_by:
            self.append_lineage(doc_id, "patched_by", patch.patched_by)
        self.db.flush()

    def set_definition_source(self, doc_id: str, term: str, source_doc_id: str) -> None:
        if self.db.get(Document, doc_id) is None:
            raise KeyError(f"unknown document: {doc_id!r}")
        self._upsert_definition_source(doc_id, term, source_doc_id)
        self.db.flush()

    def apply_operation(self, op: GraphOperation) -> None:
        if op.op == "create_document":
            stored = StoredDocument.model_validate(op.value)
            self.put_document(stored.metadata, stored.raw_text)
            return
        if not self.check_document_exists(op.doc_id):
            raise KeyError(f"unknown document for operation {op.op!r}: {op.doc_id!r}")
        if op.op == "set_status":
            value = op.value or {}
            self.update_document_status(op.doc_id, DocStatus(value["status"]), value.get("valid_until"))
        elif op.op == "set_lifecycle_field":
            self.set_lifecycle_field(op.doc_id, op.field, op.value)
        elif op.op == "append_lineage":
            self.append_lineage(op.doc_id, op.field, op.value)
        elif op.op == "append_patch":
            self.append_patch_metadata(op.doc_id, PatchRecord.model_validate(op.value))
        elif op.op == "add_review_flag":
            self.add_review_flag(op.doc_id, op.value)
        elif op.op == "set_definition_source":
            self.set_definition_source(op.doc_id, op.field, op.value)
        else:
            raise KeyError(f"unknown operation {op.op!r}")


def _date_str(value: Any) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return value.isoformat()


def _parse_date(value: Any):
    """ISO date string -> datetime.date, for Date-typed columns. The pydantic
    schema (app.schemas.lifecycle) stores dates as `str | None`; SQLite's
    driver (unlike psycopg) requires an actual `date` object."""
    from datetime import date as _date

    if value is None or isinstance(value, _date):
        return value
    return _date.fromisoformat(value)
