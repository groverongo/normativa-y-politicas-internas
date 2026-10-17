from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "NttBanca API"
    debug: bool = False

    # PostgreSQL (AWS RDS)
    db_host: str
    db_port: int = 5432
    db_name: str
    db_user: str
    db_password: str
    db_sslmode: str = "require"
    db_connect_timeout: int = 10
    # Al arrancar aplica las migraciones pendientes de migrations/
    db_auto_create_tables: bool = True

    # AWS / S3
    aws_region: str = "us-east-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    s3_bucket_name: str
    s3_key_prefix: str = "uploads"
    s3_presigned_url_expiration: int = 3600

    # Orquestador: pausa de cada agente stub, para que la demo muestre el avance (0 = sin pausa)
    agent_stub_delay_ms: int = 1000

    # Ingestion pipeline (Classifier/Extraction/Validation/Graph-Update), ported
    # from modules/ingesta/config.py's Settings. API keys are read inside the
    # provider classes (app/services/llm_provider.py), not here.
    llm_provider: str = "mock"
    llm_model: str | None = None
    llm_temperature: float = 0.0
    llm_max_tokens: int = 4096
    openai_base_url: str | None = None
    max_reclassify_attempts: int = 2
    max_impact_docs: int = 5
    max_cascade_depth: int = 1

    @property
    def database_url(self) -> URL:
        # URL.create escapa caracteres especiales del password (@, :, /, etc.)
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query={"sslmode": self.db_sslmode},
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
