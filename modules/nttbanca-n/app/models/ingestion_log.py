"""ORM model for the ingestion pipeline's interaction log.

Ported from modules/ingesta/logging_trace.py's InteractionLogger event
taxonomy, but as a Postgres table (see migrations/0008_create_ingestion_log.sql)
instead of local runs/<run_id>/interaction_log.jsonl files -- consistent with
how app/models/ejecucion.py already persists pipeline traceability in
Postgres rather than on local disk.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_JSONField = JSON().with_variant(JSONB(), "postgresql")


class IngestionLogEntry(Base):
    """One event row from an ingestion pipeline run."""

    __tablename__ = "ingestion_log"
    __table_args__ = (UniqueConstraint("run_id", "seq", name="uq_ingestion_log_run_id_seq"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    source_file: Mapped[str | None] = mapped_column(String, nullable=True)
    doc_id: Mapped[str | None] = mapped_column(String, nullable=True)
    event: Mapped[str] = mapped_column(String(20), nullable=False)
    agent: Mapped[str] = mapped_column(String(20), nullable=False)
    from_agent: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_agent: Mapped[str | None] = mapped_column(String(20), nullable=True)
    loop: Mapped[str | None] = mapped_column(String(40), nullable=True)
    iteration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    input: Mapped[Any | None] = mapped_column(_JSONField, nullable=True)
    output: Mapped[Any | None] = mapped_column(_JSONField, nullable=True)
    llm: Mapped[Any | None] = mapped_column(_JSONField, nullable=True)
