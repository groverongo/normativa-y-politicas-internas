"""Agent-interaction log for the ingestion pipeline: one row per event, in
order, with timestamps.

Ported from modules/ingesta/logging_trace.py's InteractionLogger -- same
event taxonomy and log()/feedback() signatures -- but writes to the
`ingestion_log` Postgres table (app/models/ingestion_log.py) via a
SQLAlchemy Session instead of a local runs/<run_id>/interaction_log.jsonl
file, so traceability survives an EC2 redeploy and is shared across
instances (see migrations/0008_create_ingestion_log.sql).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.ingestion_log import IngestionLogEntry
from app.schemas.lifecycle import FeedbackMessage

_EVENTS = {
    "run_start", "document_start", "agent_call", "agent_result",
    "feedback", "loop_decision", "storage_op", "error", "document_end", "run_end",
}


def summarize_text(text: str, limit: int) -> dict:
    import hashlib

    text = text or ""
    return {
        "chars": len(text),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
        "preview": text[:limit],
    }


def to_jsonable(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    return obj


class InteractionLogger:
    def __init__(self, db: Session, run_id: str | None = None, truncate_chars: int = 600) -> None:
        self.db = db
        self.run_id = run_id or (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
        )
        self.truncate_chars = truncate_chars
        self._seq = 0
        self._doc_id: str | None = None
        self._source_file: str | None = None

    def set_context(self, *, doc_id: str | None = None, source_file: str | None = None) -> None:
        if doc_id is not None:
            self._doc_id = doc_id
        if source_file is not None:
            self._source_file = source_file

    def log(
        self,
        event: str,
        *,
        agent: str,
        message: str = "",
        input: Any = None,
        output: Any = None,
        from_agent: str | None = None,
        to_agent: str | None = None,
        loop: str | None = None,
        iteration: int | None = None,
        attempt: int | None = None,
        llm: dict | None = None,
        doc_id: str | None = None,
    ) -> IngestionLogEntry:
        if event not in _EVENTS:
            raise ValueError(f"unknown event type: {event!r}")
        self._seq += 1
        entry = IngestionLogEntry(
            run_id=self.run_id,
            seq=self._seq,
            source_file=self._source_file,
            doc_id=doc_id if doc_id is not None else self._doc_id,
            event=event,
            agent=agent,
            from_agent=from_agent,
            to_agent=to_agent,
            loop=loop,
            iteration=iteration,
            attempt=attempt,
            message=message,
            input=to_jsonable(input),
            output=to_jsonable(output),
            llm=llm,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def feedback(self, msg: FeedbackMessage, doc_id: str | None = None) -> IngestionLogEntry:
        return self.log(
            "feedback",
            agent=msg.from_agent,
            from_agent=msg.from_agent,
            to_agent=msg.to_agent,
            loop=msg.loop,
            iteration=msg.iteration,
            message=msg.content,
            input=msg.payload,
            doc_id=doc_id,
        )
