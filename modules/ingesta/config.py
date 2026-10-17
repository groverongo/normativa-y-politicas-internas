"""Runtime settings loaded from environment variables (and optional CLI overrides).

Secrets are read inside the classes that need them, not here: ANTHROPIC_API_KEY,
OPENAI_API_KEY, GEMINI_API_KEY (fallback GOOGLE_API_KEY) in llm_provider.py;
DB_PASSWORD in storage.py's S3DbStorage. AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY/
AWS_SESSION_TOKEN are read by boto3's own default credential chain.
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
    storage_backend: str = "memory"
    db_host: str | None = None
    db_port: int = 5432
    db_name: str | None = None
    db_user: str | None = None
    db_sslmode: str | None = None
    db_connect_timeout: int = 10
    aws_region: str | None = None
    s3_bucket_name: str | None = None
    s3_endpoint_url: str | None = None
    s3_key_prefix: str = ""
    s3_presigned_url_expiration: int = 3600

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
            storage_backend=_env_str("STORAGE_BACKEND", "memory"),
            db_host=_env_str("DB_HOST", None),
            db_port=_env_int("DB_PORT", 5432),
            db_name=_env_str("DB_NAME", None),
            db_user=_env_str("DB_USER", None),
            db_sslmode=_env_str("DB_SSLMODE", None),
            db_connect_timeout=_env_int("DB_CONNECT_TIMEOUT", 10),
            aws_region=_env_str("AWS_REGION", None),
            s3_bucket_name=_env_str("S3_BUCKET_NAME", None),
            s3_endpoint_url=_env_str("S3_ENDPOINT_URL", None),
            s3_key_prefix=_env_str("S3_KEY_PREFIX", ""),
            s3_presigned_url_expiration=_env_int("S3_PRESIGNED_URL_EXPIRATION", 3600),
        )
        clean_overrides = {k: v for k, v in overrides.items() if v is not None}
        return replace(base, **clean_overrides) if clean_overrides else base
