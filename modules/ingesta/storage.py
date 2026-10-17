"""Storage seam: StorageInterface + two implementations.

`InMemoryStorage` is a dict-backed stand-in (default, `STORAGE_BACKEND=memory`,
needs no external services) so the pipeline and smoke tests run with no setup.
`S3DbStorage` (`STORAGE_BACKEND=postgres`) is the real backend: raw document
text lives in S3, the metadata graph lives in Postgres per the shared schema
in `../nttbanca-n/migrations/*.sql` (documents, chunks, document_lineage,
document_definition_sources, document_patches -- shared with
modules/nttbanca-n, the repo's one migration sequence; run `make migrate`
from the repo root before using this backend, see
../nttbanca-n/migrations/README.md). `get_storage(settings)` picks the right
one from `Settings.storage_backend`.
"""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterable

from config import Settings
from schema import (
    CatalogEntry,
    Chunk,
    DocStatus,
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


# ---------------------------------------------------------------------------
# Real backend: S3 (raw text) + Postgres (metadata graph)
# ---------------------------------------------------------------------------


class StorageError(RuntimeError):
    """Raised for any S3DbStorage initialization or operation failure."""


_LINEAGE_FIELDS: tuple[str, ...] = (
    "supersedes", "superseded_by", "amends", "patched_by", "consolidates",
    "split_from", "split_into", "contradicts", "revokes", "revoked_by",
    "overrides", "overridden_by", "impacts",
)

_LIFECYCLE_SCALAR_FIELDS = {"valid_from", "valid_until", "version"}
_LIFECYCLE_JSON_LIST_FIELDS = {"review_flags", "missing_dependencies", "notes"}


def _date_str(value: Any) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return value.isoformat()


class S3DbStorage(StorageInterface):
    """Raw text in S3, metadata graph in Postgres (see
    ../nttbanca-n/migrations/*.sql, shared with modules/nttbanca-n -- run
    `make migrate` from the repo root before using this backend).

    `psycopg` and `boto3` are lazily imported, mirroring llm_provider.py's
    real-provider classes, so the default memory backend never needs them.
    """

    def __init__(self, settings: Settings) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise StorageError(
                "S3DbStorage requires the 'psycopg[binary]' package. "
                "Install it with `pip install psycopg[binary]`."
            ) from exc
        try:
            import boto3
        except ImportError as exc:
            raise StorageError(
                "S3DbStorage requires the 'boto3' package. "
                "Install it with `pip install boto3`."
            ) from exc
        if not (settings.db_host and settings.db_name and settings.db_user):
            raise StorageError("S3DbStorage requires DB_HOST, DB_NAME, and DB_USER.")
        db_password = os.environ.get("DB_PASSWORD")
        if not db_password:
            raise StorageError("S3DbStorage requires the DB_PASSWORD environment variable.")
        if not settings.s3_bucket_name:
            raise StorageError("S3DbStorage requires S3_BUCKET_NAME.")

        conn_kwargs: dict[str, Any] = dict(
            host=settings.db_host,
            port=settings.db_port,
            dbname=settings.db_name,
            user=settings.db_user,
            password=db_password,
            connect_timeout=settings.db_connect_timeout,
        )
        if settings.db_sslmode:
            conn_kwargs["sslmode"] = settings.db_sslmode
        self._conn = psycopg.connect(**conn_kwargs, autocommit=True, row_factory=dict_row)

        self._s3 = boto3.client(
            "s3", region_name=settings.aws_region, endpoint_url=settings.s3_endpoint_url or None
        )
        self._bucket = settings.s3_bucket_name
        self._prefix = settings.s3_key_prefix

    # ---- S3 helpers ----
    def _s3_key(self, doc_id: str) -> str:
        prefix = self._prefix
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        return f"{prefix}{doc_id}.txt"

    def _put_raw_text(self, doc_id: str, text: str) -> str:
        key = self._s3_key(doc_id)
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=text.encode("utf-8"))
        return key

    def _get_raw_text(self, key: str) -> str | None:
        try:
            obj = self._s3.get_object(Bucket=self._bucket, Key=key)
        except self._s3.exceptions.NoSuchKey:
            return None
        return obj["Body"].read().decode("utf-8")

    # ---- reads ----
    def check_document_exists(self, doc_id: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("SELECT 1 FROM documents WHERE doc_id = %s", (doc_id,))
            return cur.fetchone() is not None

    def resolve_doc_id(self, raw_ref: str) -> str | None:
        normalized = normalize_doc_id(raw_ref)
        if self.check_document_exists(normalized):
            return normalized
        match = _NUM_YEAR.search(raw_ref)
        if not match:
            return None
        core = f"{match.group(1)}-{match.group(2)}"
        with self._conn.cursor() as cur:
            cur.execute("SELECT doc_id FROM documents WHERE doc_id LIKE %s", (f"%{core}",))
            candidates = [row["doc_id"] for row in cur.fetchall()]
        return candidates[0] if len(candidates) == 1 else None

    def get_document(self, doc_id: str) -> DocumentMetadata | None:
        return self._load_metadata(doc_id)

    def get_document_text(self, doc_id: str) -> str | None:
        with self._conn.cursor() as cur:
            cur.execute("SELECT source_uri FROM documents WHERE doc_id = %s", (doc_id,))
            row = cur.fetchone()
        if row is None or not row["source_uri"]:
            return None
        return self._get_raw_text(row["source_uri"])

    def list_documents(self, status: DocStatus | None = None) -> list[DocumentMetadata]:
        query = "SELECT doc_id FROM documents"
        params: tuple = ()
        if status is not None:
            query += " WHERE status = %s"
            params = (status.value,)
        with self._conn.cursor() as cur:
            cur.execute(query, params)
            doc_ids = [row["doc_id"] for row in cur.fetchall()]
        docs = (self._load_metadata(doc_id) for doc_id in doc_ids)
        return [doc for doc in docs if doc is not None]

    def find_active_documents_referencing_term(
        self, term: str, exclude: Iterable[str] = ()
    ) -> list[str]:
        exclude_list = list(exclude)
        term_lower = term.lower()
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT doc_id, referenced_terms FROM documents "
                "WHERE status = %s AND doc_id <> ALL(%s)",
                (DocStatus.ACTIVE.value, exclude_list),
            )
            rows = cur.fetchall()

        matches: set[str] = set()
        remaining: list[str] = []
        for row in rows:
            referenced = [t.lower() for t in (row["referenced_terms"] or [])]
            if term_lower in referenced:
                matches.add(row["doc_id"])
            else:
                remaining.append(row["doc_id"])

        if remaining:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT doc_id FROM chunks WHERE doc_id = ANY(%s) AND text ILIKE %s",
                    (remaining, f"%{term}%"),
                )
                matches.update(row["doc_id"] for row in cur.fetchall())
        return sorted(matches)

    def _load_metadata(self, doc_id: str) -> DocumentMetadata | None:
        with self._conn.cursor() as cur:
            cur.execute("SELECT * FROM documents WHERE doc_id = %s", (doc_id,))
            row = cur.fetchone()
            if row is None:
                return None
            cur.execute(
                "SELECT relation, target_doc_id FROM document_lineage WHERE doc_id = %s",
                (doc_id,),
            )
            lineage_rows = cur.fetchall()
            cur.execute(
                "SELECT term, source_doc_id FROM document_definition_sources WHERE doc_id = %s",
                (doc_id,),
            )
            definition_rows = cur.fetchall()
            cur.execute(
                "SELECT clause, old_text, new_text, patched_by, effective_date "
                "FROM document_patches WHERE doc_id = %s ORDER BY id",
                (doc_id,),
            )
            patch_rows = cur.fetchall()

        lineage_data: dict[str, Any] = {field: [] for field in _LINEAGE_FIELDS}
        for lrow in lineage_rows:
            lineage_data[lrow["relation"]].append(lrow["target_doc_id"])
        lineage_data["definition_sources"] = {
            drow["term"]: drow["source_doc_id"] for drow in definition_rows
        }

        patch_log = [
            PatchRecord(
                clause=prow["clause"],
                old_text=prow["old_text"],
                new_text=prow["new_text"],
                patched_by=prow["patched_by"],
                effective_date=_date_str(prow["effective_date"]),
            )
            for prow in patch_rows
        ]

        return DocumentMetadata(
            identity_metadata=IdentityMetadata(
                doc_id=row["doc_id"],
                doc_type=row["doc_type"],
                title=row["title"],
                issuer=row["issuer"],
                topic_tags=list(row["topic_tags"] or []),
                defined_terms=list(row["defined_terms"] or []),
                referenced_terms=list(row["referenced_terms"] or []),
                source_uri=row["source_uri"],
            ),
            lifecycle_metadata=LifecycleMetadata(
                status=DocStatus(row["status"]),
                valid_from=_date_str(row["valid_from"]),
                valid_until=_date_str(row["valid_until"]),
                version=row["version"],
                review_flags=list(row["review_flags"] or []),
                missing_dependencies=list(row["missing_dependencies"] or []),
                patch_log=patch_log,
                notes=list(row["notes"] or []),
            ),
            lineage_metadata=LineageMetadata(**lineage_data),
        )

    # ---- writes ----
    def put_document(self, metadata: DocumentMetadata, raw_text: str) -> list[Chunk]:
        from psycopg.types.json import Jsonb

        doc_id = metadata.doc_id
        ident = metadata.identity_metadata
        life = metadata.lifecycle_metadata
        source_uri = self._put_raw_text(doc_id, raw_text)

        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents (
                    doc_id, doc_type, title, issuer, source_uri, status,
                    valid_from, valid_until, version, topic_tags, defined_terms,
                    referenced_terms, review_flags, missing_dependencies, notes
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    doc_id, ident.doc_type, ident.title, ident.issuer, source_uri,
                    life.status.value, life.valid_from, life.valid_until, life.version,
                    Jsonb(ident.topic_tags), Jsonb(ident.defined_terms),
                    Jsonb(ident.referenced_terms), Jsonb(life.review_flags),
                    Jsonb(life.missing_dependencies), Jsonb(life.notes),
                ),
            )

        pieces = chunk_text(raw_text) or [raw_text]
        chunk_meta = metadata.model_copy(deep=True)
        chunk_meta.identity_metadata.source_uri = source_uri
        chunks: list[Chunk] = []
        with self._conn.cursor() as cur:
            for idx, piece in enumerate(pieces):
                cur.execute(
                    "INSERT INTO chunks (chunk_id, doc_id, chunk_index, text) VALUES (%s,%s,%s,%s)",
                    (f"{doc_id}#{idx}", doc_id, idx, piece),
                )
                piece_meta = chunk_meta.model_copy(deep=True)
                piece_meta.identity_metadata.chunk_index = idx
                chunks.append(
                    Chunk(
                        chunk_id=f"{doc_id}#{idx}", doc_id=doc_id, chunk_index=idx,
                        text=piece, metadata=piece_meta,
                    )
                )

        self._write_lineage(doc_id, metadata.lineage_metadata)
        for patch in life.patch_log:
            self._insert_patch(doc_id, patch)
        for term, source_doc_id in metadata.lineage_metadata.definition_sources.items():
            self._upsert_definition_source(doc_id, term, source_doc_id)
        return chunks

    def _write_lineage(self, doc_id: str, lineage: LineageMetadata) -> None:
        rows = [
            (doc_id, field, target)
            for field in _LINEAGE_FIELDS
            for target in getattr(lineage, field)
        ]
        if not rows:
            return
        with self._conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO document_lineage (doc_id, relation, target_doc_id) "
                "VALUES (%s,%s,%s) ON CONFLICT (doc_id, relation, target_doc_id) DO NOTHING",
                rows,
            )

    def _insert_patch(self, doc_id: str, patch: PatchRecord) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO document_patches "
                "(doc_id, clause, old_text, new_text, patched_by, effective_date) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    doc_id, patch.clause, patch.old_text, patch.new_text,
                    patch.patched_by, patch.effective_date,
                ),
            )

    def _upsert_definition_source(self, doc_id: str, term: str, source_doc_id: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO document_definition_sources (doc_id, term, source_doc_id) "
                "VALUES (%s,%s,%s) ON CONFLICT (doc_id, term) "
                "DO UPDATE SET source_doc_id = EXCLUDED.source_doc_id, updated_at = now()",
                (doc_id, term, source_doc_id),
            )

    def update_document_status(
        self, doc_id: str, status: DocStatus, valid_until: str | None = None
    ) -> None:
        with self._conn.cursor() as cur:
            if valid_until is not None:
                cur.execute(
                    "UPDATE documents SET status = %s, valid_until = %s WHERE doc_id = %s",
                    (status.value, valid_until, doc_id),
                )
            else:
                cur.execute(
                    "UPDATE documents SET status = %s WHERE doc_id = %s", (status.value, doc_id)
                )

    def append_lineage(self, doc_id: str, field: str, value: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO document_lineage (doc_id, relation, target_doc_id) "
                "VALUES (%s,%s,%s) ON CONFLICT (doc_id, relation, target_doc_id) DO NOTHING",
                (doc_id, field, value),
            )

    def set_lifecycle_field(self, doc_id: str, field: str, value: Any) -> None:
        from psycopg.types.json import Jsonb

        if field == "status":
            self.update_document_status(doc_id, DocStatus(value))
            return
        if field in _LIFECYCLE_SCALAR_FIELDS:
            with self._conn.cursor() as cur:
                cur.execute(f"UPDATE documents SET {field} = %s WHERE doc_id = %s", (value, doc_id))
            return
        if field in _LIFECYCLE_JSON_LIST_FIELDS:
            with self._conn.cursor() as cur:
                cur.execute(
                    f"UPDATE documents SET {field} = %s WHERE doc_id = %s", (Jsonb(value), doc_id)
                )
            return
        raise StorageError(f"S3DbStorage.set_lifecycle_field: unsupported field {field!r}")

    def add_review_flag(self, doc_id: str, flag: str) -> None:
        from psycopg.types.json import Jsonb

        with self._conn.cursor() as cur:
            cur.execute("SELECT review_flags FROM documents WHERE doc_id = %s", (doc_id,))
            row = cur.fetchone()
            flags = list(row["review_flags"] or [])
            if flag not in flags:
                flags.append(flag)
                cur.execute(
                    "UPDATE documents SET review_flags = %s WHERE doc_id = %s",
                    (Jsonb(flags), doc_id),
                )

    def append_patch_metadata(self, doc_id: str, patch: PatchRecord) -> None:
        self._insert_patch(doc_id, patch)
        if patch.patched_by:
            self.append_lineage(doc_id, "patched_by", patch.patched_by)

    def set_definition_source(self, doc_id: str, term: str, source_doc_id: str) -> None:
        self._upsert_definition_source(doc_id, term, source_doc_id)

    def snapshot(self) -> dict:
        result: dict[str, Any] = {}
        for meta in self.list_documents():
            raw_text = self.get_document_text(meta.doc_id) or ""
            stored = StoredDocument(metadata=meta, raw_text=raw_text)
            result[meta.doc_id] = stored.model_dump(mode="json")
        return result


STORAGE_BACKENDS: tuple[str, ...] = ("memory", "postgres")


def get_storage(settings: Settings) -> StorageInterface:
    if settings.storage_backend == "memory":
        return InMemoryStorage()
    if settings.storage_backend == "postgres":
        return S3DbStorage(settings)
    raise StorageError(
        f"Unknown storage backend {settings.storage_backend!r}; expected one of {STORAGE_BACKENDS}"
    )
