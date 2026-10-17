"""Shared base class for all four pipeline agents.

Implements the common "call the LLM, validate the JSON, retry once on
failure, log every step" pattern described in the implementation plan
(.omc/plans/autopilot-impl.md, section 2.6), plus the prompt tag convention
(``<document>``, ``<catalog>``, ``<feedback>``) shared by the agent modules.
Agents never call ``llm.complete_json`` directly; they go through
``BaseAgent._llm_json`` so that every LLM call is logged uniformly.
"""
from __future__ import annotations

import json
import time
from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel, ValidationError

from config import Settings
from llm_provider import LLMError, LLMProvider
from logging_trace import InteractionLogger, summarize_text
from schema import CatalogEntry, FeedbackMessage
from storage import StorageInterface

T = TypeVar("T", bound=BaseModel)


class AgentError(RuntimeError):
    """Raised when an agent's LLM call fails validation twice in a row."""


class BaseAgent:
    """Common constructor + LLM-call-and-validate helper for every agent."""

    name: ClassVar[str]

    def __init__(
        self,
        llm: LLMProvider,
        storage: StorageInterface,
        logger: InteractionLogger,
        settings: Settings,
    ) -> None:
        self.llm = llm
        self.storage = storage
        self.logger = logger
        self.settings = settings

    def _llm_json(
        self,
        *,
        task: str,
        system_prompt: str,
        user_prompt: str,
        output_model: type[T],
        context: dict | None = None,
        doc_id: str | None = None,
        attempt: int | None = None,
        loop: str | None = None,
    ) -> T:
        """Call the LLM for ``task``, validate the result, retry once on failure.

        Step-by-step (plan section 2.6):
        1. log "agent_call" before each attempt.
        2. call llm.complete_json with json_schema=output_model.model_json_schema().
        3. output_model.model_validate(raw); on ValidationError/LLMError, retry
           ONCE with the error text appended to the prompt.
        4. on success, log "agent_result" with llm={"provider","model",
           "latency_ms","retried"}.
        5. after 2 failures, log "error" and raise AgentError.
        """
        schema = output_model.model_json_schema()
        context_keys = sorted(context.keys()) if context else []
        prompt_for_attempt = user_prompt
        retried = False
        last_error: Exception | None = None

        for pass_index in range(2):
            self.logger.log(
                "agent_call",
                agent=self.name,
                message=f"{task}" + (" (repair retry)" if pass_index else ""),
                input={
                    "task": task,
                    "user_prompt": summarize_text(prompt_for_attempt, self.settings.text_truncate_chars),
                    "context_keys": context_keys,
                },
                doc_id=doc_id,
                attempt=attempt,
                loop=loop,
            )
            t0 = time.monotonic()
            try:
                raw = self.llm.complete_json(
                    task=task,
                    system_prompt=system_prompt,
                    user_prompt=prompt_for_attempt,
                    json_schema=schema,
                    context=context,
                )
                result = output_model.model_validate(raw)
            except (LLMError, ValidationError) as exc:
                latency_ms = int((time.monotonic() - t0) * 1000)
                last_error = exc
                if pass_index == 0:
                    prompt_for_attempt = (
                        f"{user_prompt}\n\n<repair>\n"
                        f"Your previous response was invalid: {exc}\n"
                        f"Respond again with ONLY a corrected JSON object matching the schema.\n"
                        f"</repair>"
                    )
                    retried = True
                    continue
                self.logger.log(
                    "error",
                    agent=self.name,
                    message=f"{task} failed validation after retry: {exc}",
                    input={"task": task},
                    doc_id=doc_id,
                    attempt=attempt,
                    loop=loop,
                )
                raise AgentError(f"{self.name}.{task} failed validation twice: {exc}") from exc
            else:
                latency_ms = int((time.monotonic() - t0) * 1000)
                self.logger.log(
                    "agent_result",
                    agent=self.name,
                    message=f"{task} ok",
                    output=result,
                    doc_id=doc_id,
                    attempt=attempt,
                    loop=loop,
                    llm={
                        "provider": getattr(self.llm, "name", "unknown"),
                        "model": getattr(self.llm, "model", "unknown"),
                        "latency_ms": latency_ms,
                        "retried": retried,
                    },
                )
                return result

        # Unreachable: the loop above always either returns or raises.
        raise AgentError(f"{self.name}.{task} failed: {last_error}")


# ---------------------------------------------------------------------------
# Prompt tag convention (plan section 2.6): <document>, <catalog>, <feedback>
# ---------------------------------------------------------------------------

def render_document_tag(doc_text: str) -> str:
    return f"<document>\n{doc_text}\n</document>"


def render_catalog_tag(catalog: list[CatalogEntry]) -> str:
    payload = [entry.model_dump(mode="json") for entry in catalog]
    return "<catalog>\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n</catalog>"


def render_feedback_tag(feedback: FeedbackMessage | None) -> str:
    if feedback is None:
        return ""
    return (
        "<feedback>\n"
        + json.dumps(feedback.model_dump(mode="json"), ensure_ascii=False, indent=2)
        + "\n</feedback>"
    )
