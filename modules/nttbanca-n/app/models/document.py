"""ORM models for the ingestion pipeline's document-lifecycle graph.

Ported from modules/ingesta/schema.py. Additive to `items`/`files`: these
tables are not referenced by app/models/item.py or app/models/file.py.
Registered in app.main via app/models/__init__.py so Base.metadata picks them
up (used by tests/conftest.py's Base.metadata.create_all(sqlite_engine) and,
on Postgres, by the repo-root /migrations/0003..0007, shared with
modules/ingesta).

JSON columns use JSON().with_variant(JSONB(), "postgresql") -- same pattern
as app/models/ejecucion.py's PasoAgente.salida -- so these models work on
both the real Postgres backend and the SQLite-in-memory test engine.
"""
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DocStatus, LineageRelation

_JSONList = JSON().with_variant(JSONB(), "postgresql")

# native_enum degrades to VARCHAR+CHECK on SQLite automatically; on Postgres
# it binds to the `doc_status`/`lineage_relation` types created by
# migrations/0003 and 0005 (create_type=False: those migrations own the
# type, not SQLAlchemy's create_all). values_callable stores the member
# *value* (matches the ENUM labels, e.g. "supersedes") rather than the
# Python member name (e.g. "SUPERSEDES").
_DocStatusType = Enum(
    DocStatus, name="doc_status", native_enum=True, create_type=False,
    values_callable=lambda enum_cls: [e.value for e in enum_cls],
)
_LineageRelationType = Enum(
    LineageRelation, name="lineage_relation", native_enum=True, create_type=False,
    values_callable=lambda enum_cls: [e.value for e in enum_cls],
)


class Document(Base):
    """A regulatory/policy document node in the lifecycle graph. Mirrors
    schema.DocumentMetadata's identity_metadata + lifecycle_metadata."""

    __tablename__ = "documents"

    doc_id: Mapped[str] = mapped_column(String, primary_key=True)
    doc_type: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    title: Mapped[str] = mapped_column(String, nullable=False, default="")
    issuer: Mapped[str] = mapped_column(String, nullable=False, default="")
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[DocStatus] = mapped_column(
        _DocStatusType, nullable=False, default=DocStatus.ACTIVE, server_default=DocStatus.ACTIVE.value
    )
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    version: Mapped[str | None] = mapped_column(String, nullable=True)
    topic_tags: Mapped[list[str]] = mapped_column(_JSONList, nullable=False, default=list)
    defined_terms: Mapped[list[str]] = mapped_column(_JSONList, nullable=False, default=list)
    referenced_terms: Mapped[list[str]] = mapped_column(_JSONList, nullable=False, default=list)
    review_flags: Mapped[list[str]] = mapped_column(_JSONList, nullable=False, default=list)
    missing_dependencies: Mapped[list[str]] = mapped_column(_JSONList, nullable=False, default=list)
    notes: Mapped[list[str]] = mapped_column(_JSONList, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class DocumentChunk(Base):
    """A text unit of a document. Mirrors schema.Chunk."""

    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("doc_id", "chunk_index", name="uq_chunks_doc_id_chunk_index"),)

    chunk_id: Mapped[str] = mapped_column(String, primary_key=True)
    doc_id: Mapped[str] = mapped_column(ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DocumentLineage(Base):
    """One directed edge in the lineage graph. Replaces the 13 list fields on
    schema.LineageMetadata with a normalized edge table.

    target_doc_id is intentionally not a FK: a "missing dependency" case
    records a reference to a document that may not exist in this corpus yet.
    """

    __tablename__ = "document_lineage"
    __table_args__ = (
        UniqueConstraint("doc_id", "relation", "target_doc_id", name="uq_document_lineage_doc_relation_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[str] = mapped_column(ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False)
    relation: Mapped[LineageRelation] = mapped_column(_LineageRelationType, nullable=False)
    target_doc_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DocumentDefinitionSource(Base):
    """Which document currently defines a given term. Mirrors
    schema.LineageMetadata.definition_sources (dict[term, source_doc_id])."""

    __tablename__ = "document_definition_sources"

    doc_id: Mapped[str] = mapped_column(
        ForeignKey("documents.doc_id", ondelete="CASCADE"), primary_key=True
    )
    term: Mapped[str] = mapped_column(String, primary_key=True)
    source_doc_id: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class DocumentPatchRecord(Base):
    """A patch applied by a "fe de erratas" document. Mirrors schema.PatchRecord."""

    __tablename__ = "document_patches"

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[str] = mapped_column(ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False)
    clause: Mapped[str] = mapped_column(Text, nullable=False)
    old_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    new_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    patched_by: Mapped[str | None] = mapped_column(String, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
