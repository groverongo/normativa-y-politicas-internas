"""Agent-interaction log: one JSONL file per run recording every agent step
and feedback-loop message, in order, with timestamps.

This is the primary evidence artifact for the hackathon submission: since no
live demo is required, this log is what proves the multi-agent reasoning
(including both feedback loops) actually happened.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from schema import FeedbackMessage


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


_EVENTS = {
    "run_start", "document_start", "agent_call", "agent_result",
    "feedback", "loop_decision", "storage_op", "error", "document_end", "run_end",
}


class InteractionLogger:
    def __init__(self, runs_dir: Path, run_id: str | None = None, truncate_chars: int = 600) -> None:
        self.run_id = run_id or (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
        )
        self.truncate_chars = truncate_chars
        self.run_dir = Path(runs_dir) / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.run_dir / "interaction_log.jsonl"
        self._fh = open(self.log_path, "a", encoding="utf-8")
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
    ) -> dict:
        if event not in _EVENTS:
            raise ValueError(f"unknown event type: {event!r}")
        self._seq += 1
        entry = {
            "seq": self._seq,
            "ts": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "run_id": self.run_id,
            "source_file": self._source_file,
            "doc_id": doc_id if doc_id is not None else self._doc_id,
            "event": event,
            "agent": agent,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "loop": loop,
            "iteration": iteration,
            "attempt": attempt,
            "message": message,
            "input": to_jsonable(input),
            "output": to_jsonable(output),
            "llm": llm,
        }
        self._fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._fh.flush()
        return entry

    def feedback(self, msg: FeedbackMessage, doc_id: str | None = None) -> dict:
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

    def write_json(self, name: str, data: Any) -> Path:
        path = self.run_dir / name
        path.write_text(json.dumps(to_jsonable(data), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()
