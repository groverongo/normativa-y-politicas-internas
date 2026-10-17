"""LLM provider seam for the ingestion pipeline: one `complete_json` contract
for every backend. Ported verbatim from modules/ingesta/llm_provider.py.

Real providers (Anthropic/OpenAI/Gemini) are thin, lazily-imported wrappers
that ask the model for raw JSON text and hand it to `extract_json`.
`MockProvider` is a fully deterministic, keyword/regex-driven heuristic
engine that lets the rest of the pipeline (and its tests) run with no API
key -- this is the default (`LLM_PROVIDER=mock`), matching nttbanca-n's
existing "tests need no credentials" property.
"""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.schemas.lifecycle import LifecycleCase, normalize_doc_id

TASKS = ("classify", "extract", "validate", "graph_update", "assess_impact", "extract_term_usage")


class LLMError(RuntimeError):
    """Raised for any provider/parsing failure in the LLM seam."""


class LLMProvider(ABC):
    """Common contract every backend (mock or real) implements."""

    name: str
    model: str

    @abstractmethod
    def complete_json(
        self,
        *,
        task: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
        context: dict | None = None,
    ) -> dict:
        """Return a parsed JSON object. Real providers ignore `context`."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# JSON extraction helper (shared by all real providers)
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> dict:
    """Strip ```json fences, take the outermost {...}, json.loads it.

    Raises LLMError on any failure (no object found, malformed JSON).
    """
    if not text or not text.strip():
        raise LLMError("empty response: cannot extract JSON from an empty string")
    stripped = text.strip()
    fence_match = _FENCE_RE.search(stripped)
    if fence_match:
        stripped = fence_match.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise LLMError(f"no JSON object found in response: {text[:200]!r}")
    candidate = stripped[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LLMError(f"failed to parse JSON from response: {exc}") from exc


# ---------------------------------------------------------------------------
# MockProvider heuristics
# ---------------------------------------------------------------------------

_DOC_REF_RE = re.compile(r"\b[A-Z]{2,6}-[A-Z]{2,6}-\d+-\d{4}\b")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_ID_HEADER_RE = re.compile(r"^\s*ID\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_QUOTED_TERM_RE = re.compile(
    r'(?:se entiende por|redefine)[^"“]*?["“]([^"”]+)["”]',
    re.IGNORECASE,
)

_CLASSIFY_PRIORITY: list[tuple[re.Pattern, LifecycleCase]] = [
    (re.compile(r"fe de erratas|errata"), LifecycleCase.PATCH_ERRATUM),
    (re.compile(r"texto único ordenado|tuo|consolida"), LifecycleCase.CONSOLIDATION),
    (re.compile(r"escisión|escinde|se divide"), LifecycleCase.SPLITTING),
    (
        re.compile(r"excepción temporal|temporalmente|régimen transitorio"),
        LifecycleCase.TEMPORARY_EXCEPTION,
    ),
    (re.compile(r"deroga|caduca|queda sin efecto"), LifecycleCase.REVOCATION_OR_EXPIRATION),
    (
        re.compile(r"contradice|en sentido contrario|deja sin efecto el criterio"),
        LifecycleCase.REPLACEMENT_WITH_CONTRADICTION,
    ),
    (re.compile(r"sustituye|reemplaza|nueva versión"), LifecycleCase.FULL_REPLACEMENT),
    (
        re.compile(r"se entiende por|redefine|nueva definición"),
        LifecycleCase.INDIRECT_DEPENDENCY_UPDATE,
    ),
]


def _keyword_case(text_lower: str) -> LifecycleCase:
    for pattern, case in _CLASSIFY_PRIORITY:
        if pattern.search(text_lower):
            return case
    return LifecycleCase.NEW_STATEMENT


def _coerce_case(value: Any) -> LifecycleCase:
    if isinstance(value, LifecycleCase):
        return value
    if isinstance(value, str):
        try:
            return LifecycleCase(value)
        except ValueError:
            try:
                return LifecycleCase[value]
            except KeyError:
                pass
    return LifecycleCase.NEW_STATEMENT


def _detect_own_id(document_text: str, source_name: str | None = None) -> str | None:
    """First match on line 1 / an 'ID:' header line, else normalize_doc_id(source_name)."""
    lines = document_text.splitlines()
    first_line = lines[0] if lines else ""
    m = _DOC_REF_RE.search(first_line)
    if m:
        return m.group(0)
    header_match = _ID_HEADER_RE.search(document_text)
    if header_match:
        candidate = header_match.group(1).strip()
        ref_match = _DOC_REF_RE.search(candidate)
        if ref_match:
            return ref_match.group(0)
        return normalize_doc_id(candidate)
    if source_name:
        return normalize_doc_id(Path(source_name).stem)
    return None


def _extract_refs(document_text: str, own_id: str | None) -> list[str]:
    """All canonical doc-id matches in the text, excluding the doc's own id, deduped in order."""
    seen: list[str] = []
    for m in _DOC_REF_RE.finditer(document_text):
        ref = m.group(0)
        if own_id and ref == own_id:
            continue
        if ref not in seen:
            seen.append(ref)
    return seen


def _model_dump_or_dict(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


class MockProvider(LLMProvider):
    """Deterministic keyword/regex heuristic engine -- no network calls."""

    name = "mock"
    model = "heuristic-v1"

    def complete_json(
        self,
        *,
        task: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
        context: dict | None = None,
    ) -> dict:
        context = context or {}
        if task == "classify":
            return self._classify(context)
        if task == "extract":
            return self._extract(context)
        if task == "validate":
            return self._validate(context)
        if task == "graph_update":
            return self._graph_update(context)
        if task == "assess_impact":
            return self._assess_impact(context)
        if task == "extract_term_usage":
            return self._extract_term_usage(context)
        raise LLMError(f"MockProvider: unknown task {task!r}; expected one of {TASKS}")

    # -- classify ------------------------------------------------------
    def _classify(self, context: dict) -> dict:
        document_text = context.get("document_text") or ""
        feedback = context.get("feedback")
        text_lower = document_text.lower()
        own_id = _detect_own_id(document_text, None)
        refs = _extract_refs(document_text, own_id)

        if isinstance(feedback, dict) and feedback.get("kind") in {
            "missing_dependency",
            "structural_issue",
        }:
            content = feedback.get("content") or feedback.get("kind")
            return {
                "case": LifecycleCase.NEW_STATEMENT.value,
                "confidence": 0.6,
                "rationale": (
                    f"Reconsidered after validator feedback ({feedback.get('kind')}): {content}"
                ),
                "candidate_references": refs,
            }

        case = _keyword_case(text_lower)
        return {
            "case": case.value,
            "confidence": 0.9 if case is not LifecycleCase.NEW_STATEMENT else 0.7,
            "rationale": f"Heuristic keyword match -> {case.value}",
            "candidate_references": refs,
        }

    # -- extract ---------------------------------------------------------
    def _extract(self, context: dict) -> dict:
        document_text = context.get("document_text") or ""
        case = _coerce_case(context.get("case"))
        source_name = context.get("source_name") or ""

        own_id = _detect_own_id(document_text, source_name)
        refs = _extract_refs(document_text, own_id)
        dates = _DATE_RE.findall(document_text)
        valid_from = dates[0] if dates else None
        valid_until = (
            dates[1] if (case is LifecycleCase.TEMPORARY_EXCEPTION and len(dates) > 1) else None
        )

        doc_id = own_id or normalize_doc_id(
            Path(source_name).stem if source_name else "UNKNOWN-DOC"
        )
        doc_type = "fe_de_erratas" if case is LifecycleCase.PATCH_ERRATUM else "unknown"

        redefined_terms: list[dict] = []
        defined_terms: list[str] = []
        if case is LifecycleCase.INDIRECT_DEPENDENCY_UPDATE:
            term_match = _QUOTED_TERM_RE.search(document_text)
            if term_match:
                term = term_match.group(1).strip()
                defined_terms = [term]
                redefined_terms = [{"term": term, "definition": ""}]

        patches: list[dict] = []
        if case is LifecycleCase.PATCH_ERRATUM:
            patches = [
                {
                    "clause": "clause-1",
                    "old_text": "",
                    "new_text": "",
                    "patched_by": None,
                    "effective_date": valid_from,
                }
            ]

        contradiction_scope = (
            "total" if case is LifecycleCase.REPLACEMENT_WITH_CONTRADICTION else "none"
        )
        contradiction_notes = (
            ["Heuristic: document text indicates contradiction with target document(s)."]
            if case is LifecycleCase.REPLACEMENT_WITH_CONTRADICTION
            else []
        )

        revocation_kind = None
        if case is LifecycleCase.REVOCATION_OR_EXPIRATION:
            revocation_kind = "expiration" if "caduca" in document_text.lower() else "revocation"

        metadata = {
            "identity_metadata": {
                "doc_id": doc_id,
                "chunk_index": 0,
                "doc_type": doc_type,
                "title": "",
                "issuer": "",
                "topic_tags": [],
                "defined_terms": defined_terms,
                "referenced_terms": [],
                "source_uri": None,
            },
            "lifecycle_metadata": {
                "status": "ACTIVE",
                "valid_from": valid_from,
                "valid_until": valid_until,
                "version": None,
                "review_flags": [],
                "missing_dependencies": [],
                "patch_log": [],
                "notes": [],
            },
            "lineage_metadata": {},
        }

        return {
            "metadata": metadata,
            "target_doc_ids": refs,
            "effective_date": valid_from,
            "contradiction_scope": contradiction_scope,
            "contradiction_notes": contradiction_notes,
            "revocation_kind": revocation_kind,
            "patches": patches,
            "redefined_terms": redefined_terms,
        }

    # -- validate ----------------------------------------------------
    def _validate(self, context: dict) -> dict:
        missing_refs = context.get("missing_refs") or []
        structural_issues = context.get("structural_issues") or []
        case = context.get("case")

        if missing_refs or structural_issues:
            reasons = []
            if missing_refs:
                reasons.append(f"missing references: {', '.join(missing_refs)}")
            if structural_issues:
                reasons.append(f"structural issues: {'; '.join(structural_issues)}")
            reasoning = "Validation found problems -> " + "; ".join(reasons)
            feedback_hint = "Reconsider classification given " + "; ".join(reasons)
            return {
                "recommendation": "reclassify",
                "reasoning": reasoning,
                "feedback_hint": feedback_hint,
            }

        return {
            "recommendation": "proceed",
            "reasoning": f"No missing references or structural issues for case {case}.",
            "feedback_hint": "",
        }

    # -- graph_update --------------------------------------------------
    def _graph_update(self, context: dict) -> dict:
        operations = context.get("operations") or []
        redefined_terms = context.get("redefined_terms") or []
        case = context.get("case")

        counts: dict[str, int] = {}
        for op in operations:
            op_dict = _model_dump_or_dict(op)
            doc_id = op_dict.get("doc_id") if isinstance(op_dict, dict) else None
            if doc_id is not None:
                counts[doc_id] = counts.get(doc_id, 0) + 1

        parts = [f"{doc_id}: {n} op(s)" for doc_id, n in counts.items()]
        rationale = f"case={case}: applied {len(operations)} operation(s)"
        if parts:
            rationale += " (" + ", ".join(parts) + ")"

        impact_terms = [_model_dump_or_dict(t) for t in redefined_terms]
        return {"rationale": rationale, "impact_terms": impact_terms, "warnings": []}

    # -- assess_impact -------------------------------------------------
    def _assess_impact(self, context: dict) -> dict:
        term = context.get("term") or ""
        target_text = context.get("target_text") or ""
        target_doc_id = context.get("target_doc_id") or ""
        affected = term.lower() in target_text.lower()
        rationale = (
            f"'{term}' appears in the text of {target_doc_id}."
            if affected
            else f"'{term}' does not appear in the text of {target_doc_id}."
        )
        return {
            "target_doc_id": target_doc_id,
            "term": term,
            "affected": affected,
            "rationale": rationale,
        }

    # -- extract_term_usage -----------------------------------------
    def _extract_term_usage(self, context: dict) -> dict:
        term = context.get("term") or ""
        target_text = context.get("target_text") or ""
        target_doc_id = context.get("target_doc_id") or ""
        sentences = re.split(r"(?<=[.;\n])\s+", target_text)
        clauses = [s.strip() for s in sentences if s.strip() and term.lower() in s.lower()]
        return {"target_doc_id": target_doc_id, "term": term, "clauses": clauses}


# ---------------------------------------------------------------------------
# Real providers -- lazy SDK imports, shared schema-instruction suffix
# ---------------------------------------------------------------------------

_SCHEMA_SUFFIX = "Respond with ONLY a JSON object matching this JSON Schema: "


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        try:
            import anthropic
        except ImportError as exc:
            raise LLMError(
                "AnthropicProvider requires the 'anthropic' package. "
                "Install it with `pip install anthropic`."
            ) from exc
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError(
                "AnthropicProvider requires the ANTHROPIC_API_KEY environment variable."
            )
        if not settings.llm_model:
            raise LLMError(
                "AnthropicProvider requires Settings.llm_model (env LLM_MODEL) to be set; "
                "there is no hardcoded model id."
            )
        self.model = settings.llm_model
        self._settings = settings
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete_json(
        self,
        *,
        task: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
        context: dict | None = None,
    ) -> dict:
        full_system = system_prompt + "\n\n" + _SCHEMA_SUFFIX + json.dumps(json_schema)
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self._settings.llm_max_tokens,
            temperature=self._settings.llm_temperature,
            system=full_system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        return extract_json(text)


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        try:
            import openai
        except ImportError as exc:
            raise LLMError(
                "OpenAIProvider requires the 'openai' package. "
                "Install it with `pip install openai`."
            ) from exc
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise LLMError("OpenAIProvider requires the OPENAI_API_KEY environment variable.")
        if not settings.llm_model:
            raise LLMError(
                "OpenAIProvider requires Settings.llm_model (env LLM_MODEL) to be set; "
                "there is no hardcoded model id."
            )
        self.model = settings.llm_model
        self._settings = settings
        self._client = openai.OpenAI(api_key=api_key, base_url=settings.openai_base_url)

    def complete_json(
        self,
        *,
        task: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
        context: dict | None = None,
    ) -> dict:
        full_system = system_prompt + "\n\n" + _SCHEMA_SUFFIX + json.dumps(json_schema)
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=self._settings.llm_temperature,
            max_tokens=self._settings.llm_max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": full_system},
                {"role": "user", "content": user_prompt},
            ],
        )
        text = response.choices[0].message.content or ""
        return extract_json(text)


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, settings: Settings) -> None:
        try:
            from google import genai
        except ImportError as exc:
            raise LLMError(
                "GeminiProvider requires the 'google-genai' package. "
                "Install it with `pip install google-genai`."
            ) from exc
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise LLMError(
                "GeminiProvider requires the GEMINI_API_KEY (or GOOGLE_API_KEY) "
                "environment variable."
            )
        if not settings.llm_model:
            raise LLMError(
                "GeminiProvider requires Settings.llm_model (env LLM_MODEL) to be set; "
                "there is no hardcoded model id."
            )
        self.model = settings.llm_model
        self._settings = settings
        self._client = genai.Client(api_key=api_key)

    def complete_json(
        self,
        *,
        task: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
        context: dict | None = None,
    ) -> dict:
        from google.genai import types

        full_system = system_prompt + "\n\n" + _SCHEMA_SUFFIX + json.dumps(json_schema)
        response = self._client.models.generate_content(
            model=self.model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=full_system,
                temperature=self._settings.llm_temperature,
                max_output_tokens=self._settings.llm_max_tokens,
                response_mime_type="application/json",
            ),
        )
        text = response.text or ""
        return extract_json(text)


PROVIDERS: dict[str, type[LLMProvider]] = {
    "mock": MockProvider,
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}


def get_provider(settings: Settings) -> LLMProvider:
    provider_cls = PROVIDERS.get(settings.llm_provider)
    if provider_cls is None:
        raise LLMError(
            f"Unknown LLM provider {settings.llm_provider!r}; "
            f"expected one of {sorted(PROVIDERS)}"
        )
    if provider_cls is MockProvider:
        return MockProvider()
    return provider_cls(settings)
