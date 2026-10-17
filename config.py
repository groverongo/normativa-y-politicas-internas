"""Runtime settings loaded from environment variables (and optional CLI overrides).

API keys are read inside the provider classes in llm_provider.py, not here:
ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY (fallback GOOGLE_API_KEY).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv


def _env_str(name: str, default: str | None) -> str | None:
    val = os.environ.get(name)
    return val if val not in (None, "") else default


def _env_float(name: str, default: float) -> float:
    val = os.environ.get(name)
    return float(val) if val not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    return int(val) if val not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"
    llm_model: str | None = None
    llm_temperature: float = 0.0
    llm_max_tokens: int = 4096
    openai_base_url: str | None = None
    max_reclassify_attempts: int = 2
    max_impact_docs: int = 5
    max_cascade_depth: int = 1
    runs_dir: Path = Path("runs")
    text_truncate_chars: int = 600

    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        load_dotenv()
        base = cls(
            llm_provider=_env_str("LLM_PROVIDER", "mock"),
            llm_model=_env_str("LLM_MODEL", None),
            llm_temperature=_env_float("LLM_TEMPERATURE", 0.0),
            llm_max_tokens=_env_int("LLM_MAX_TOKENS", 4096),
            openai_base_url=_env_str("OPENAI_BASE_URL", None),
            max_reclassify_attempts=_env_int("MAX_RECLASSIFY_ATTEMPTS", 2),
            max_impact_docs=_env_int("MAX_IMPACT_DOCS", 5),
            max_cascade_depth=_env_int("MAX_CASCADE_DEPTH", 1),
            runs_dir=Path(_env_str("RUNS_DIR", "runs")),
            text_truncate_chars=600,
        )
        clean_overrides = {k: v for k, v in overrides.items() if v is not None}
        return replace(base, **clean_overrides) if clean_overrides else base
