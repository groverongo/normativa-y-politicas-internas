"""Storage seam: StorageInterface (stub) + InMemoryStorage implementation.

Per the spec, real S3/file storage and a real database are being built by a
separate workstream. Every mutating/reading method below is marked with
`# TODO: link to real S3/DB client` — this class is a stand-in so the
ingestion pipeline can be built and demoed without that integration.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterable

from schema import (
    CatalogEntry,
    Chunk,
    DocStatus,
    DocumentMetadata,
    GraphOperation,
    PatchRecord,
    StoredDocument,
    normalize_doc_id,
)

_NUM_YEAR = re.compile(r"(\d+)-(\d{4})")


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


class StorageInterface(ABC):
    """Stub seam standing in for the real S3 (file) + DB (metadata) layer."""

    # ---- reads ----
    @abstractmethod
    def check_document_exists(self, doc_id: str) -> bool: ...

    @abstractmethod
    def resolve_doc_id(self, raw_ref: str) -> str | None: ...

    @abstractmethod
    def get_document(self, doc_id: str) -> DocumentMetadata | None: ...

    @abstractmethod
    def get_document_text(self, doc_id: str) -> str | None: ...

    @abstractmethod
    def list_documents(self, status: DocStatus | None = None) -> list[DocumentMetadata]: ...

    @abstractmethod
    def find_active_documents_referencing_term(
        self, term: str, exclude: Iterable[str] = ()
    ) -> list[str]: ...

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

    # ---- writes ----
    @abstractmethod
    def put_document(self, metadata: DocumentMetadata, raw_text: str) -> list[Chunk]: ...

    @abstractmethod
    def update_document_status(
        self, doc_id: str, status: DocStatus, valid_until: str | None = None
    ) -> None: ...

    @abstractmethod
    def append_lineage(self, doc_id: str, field: str, value: str) -> None: ...

    @abstractmethod
    def set_lifecycle_field(self, doc_id: str, field: str, value: Any) -> None: ...

    @abstractmethod
    def add_review_flag(self, doc_id: str, flag: str) -> None: ...

    @abstractmethod
    def append_patch_metadata(self, doc_id: str, patch: PatchRecord) -> None: ...

    @abstractmethod
    def set_definition_source(self, doc_id: str, term: str, source_doc_id: str) -> None: ...

    def apply_operation(self, op: GraphOperation) -> None:
        if op.op == "create_document":
            stored = StoredDocument.model_validate(op.value)
            self.put_document(stored.metadata, stored.raw_text)
            return
        if op.op != "create_document" and not self.check_document_exists(op.doc_id):
            raise KeyError(f"unknown document for operation {op.op!r}: {op.doc_id!r}")
        if op.op == "set_status":
            value = op.value or {}
            self.update_document_status(
                op.doc_id, DocStatus(value["status"]), value.get("valid_until")
            )
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

    @abstractmethod
    def snapshot(self) -> dict: ...


class InMemoryStorage(StorageInterface):
    """Dict-backed stand-in for the real S3/DB-backed storage layer."""

    def __init__(self) -> None:
        self._docs: dict[str, StoredDocument] = {}
        self._chunks: dict[str, list[Chunk]] = {}

    @classmethod
    def from_seed_file(cls, path: Path) -> "InMemoryStorage":
        store = cls()
        if path and Path(path).exists():
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            for entry in raw:
                stored = StoredDocument.model_validate(entry)
                store.put_document(stored.metadata, stored.raw_text)
        return store

    def dump(self, path: Path) -> None:
        Path(path).write_text(
            json.dumps(
                [doc.model_dump(mode="json") for doc in self._docs.values()],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    # ---- reads ----
    def check_document_exists(self, doc_id: str) -> bool:
        # TODO: link to real S3/DB client
        return doc_id in self._docs

    def resolve_doc_id(self, raw_ref: str) -> str | None:
        # TODO: link to real S3/DB client
        normalized = normalize_doc_id(raw_ref)
        if normalized in self._docs:
            return normalized
        match = _NUM_YEAR.search(raw_ref)
        if not match:
            return None
        core = f"{match.group(1)}-{match.group(2)}"
        candidates = [doc_id for doc_id in self._docs if doc_id.endswith(core)]
        return candidates[0] if len(candidates) == 1 else None

    def get_document(self, doc_id: str) -> DocumentMetadata | None:
        # TODO: link to real S3/DB client
        stored = self._docs.get(doc_id)
        return stored.metadata if stored else None

    def get_document_text(self, doc_id: str) -> str | None:
        # TODO: link to real S3/DB client
        stored = self._docs.get(doc_id)
        return stored.raw_text if stored else None

    def list_documents(self, status: DocStatus | None = None) -> list[DocumentMetadata]:
        # TODO: link to real S3/DB client
        docs = [stored.metadata for stored in self._docs.values()]
        if status is not None:
            docs = [d for d in docs if d.lifecycle_metadata.status == status]
        return docs

    def find_active_documents_referencing_term(
        self, term: str, exclude: Iterable[str] = ()
    ) -> list[str]:
        # TODO: link to real S3/DB client
        exclude_set = set(exclude)
        term_lower = term.lower()
        matches = []
        for doc_id, stored in self._docs.items():
            if doc_id in exclude_set:
                continue
            if stored.metadata.lifecycle_metadata.status != DocStatus.ACTIVE:
                continue
            referenced = [t.lower() for t in stored.metadata.identity_metadata.referenced_terms]
            if term_lower in referenced or term_lower in stored.raw_text.lower():
                matches.append(doc_id)
        return sorted(matches)

    # ---- writes ----
    def put_document(self, metadata: DocumentMetadata, raw_text: str) -> list[Chunk]:
        # TODO: link to real S3/DB client
        doc_id = metadata.doc_id
        self._docs[doc_id] = StoredDocument(metadata=metadata, raw_text=raw_text)
        pieces = chunk_text(raw_text) or [raw_text]
        chunks = []
        for idx, piece in enumerate(pieces):
            chunk_meta = metadata.model_copy(deep=True)
            chunk_meta.identity_metadata.chunk_index = idx
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}#{idx}",
                    doc_id=doc_id,
                    chunk_index=idx,
                    text=piece,
                    metadata=chunk_meta,
                )
            )
        self._chunks[doc_id] = chunks
        return chunks

    def _resync_chunks(self, doc_id: str) -> None:
        stored = self._docs.get(doc_id)
        if not stored or doc_id not in self._chunks:
            return
        for chunk in self._chunks[doc_id]:
            chunk.metadata = stored.metadata.model_copy(deep=True)
            chunk.metadata.identity_metadata.chunk_index = chunk.chunk_index

    def update_document_status(
        self, doc_id: str, status: DocStatus, valid_until: str | None = None
    ) -> None:
        # TODO: link to real S3/DB client
        stored = self._docs[doc_id]
        stored.metadata.lifecycle_metadata.status = status
        if valid_until is not None:
            stored.metadata.lifecycle_metadata.valid_until = valid_until
        self._resync_chunks(doc_id)

    def append_lineage(self, doc_id: str, field: str, value: str) -> None:
        # TODO: link to real S3/DB client
        stored = self._docs[doc_id]
        current: list[str] = getattr(stored.metadata.lineage_metadata, field)
        if value not in current:
            current.append(value)
        self._resync_chunks(doc_id)

    def set_lifecycle_field(self, doc_id: str, field: str, value: Any) -> None:
        # TODO: link to real S3/DB client
        stored = self._docs[doc_id]
        setattr(stored.metadata.lifecycle_metadata, field, value)
        self._resync_chunks(doc_id)

    def add_review_flag(self, doc_id: str, flag: str) -> None:
        # TODO: link to real S3/DB client
        stored = self._docs[doc_id]
        if flag not in stored.metadata.lifecycle_metadata.review_flags:
            stored.metadata.lifecycle_metadata.review_flags.append(flag)
        self._resync_chunks(doc_id)

    def append_patch_metadata(self, doc_id: str, patch: PatchRecord) -> None:
        # TODO: link to real S3/DB client
        stored = self._docs[doc_id]
        stored.metadata.lifecycle_metadata.patch_log.append(patch)
        if patch.patched_by and patch.patched_by not in stored.metadata.lineage_metadata.patched_by:
            stored.metadata.lineage_metadata.patched_by.append(patch.patched_by)
        self._resync_chunks(doc_id)

    def set_definition_source(self, doc_id: str, term: str, source_doc_id: str) -> None:
        # TODO: link to real S3/DB client
        stored = self._docs[doc_id]
        stored.metadata.lineage_metadata.definition_sources[term] = source_doc_id
        self._resync_chunks(doc_id)

    def snapshot(self) -> dict:
        # TODO: link to real S3/DB client
        return {doc_id: stored.model_dump(mode="json") for doc_id, stored in self._docs.items()}
