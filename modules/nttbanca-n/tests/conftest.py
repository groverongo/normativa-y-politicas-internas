import os

# Variables dummy ANTES de importar la app: los tests no tocan RDS ni S3 reales.
os.environ.update(
    {
        "DB_HOST": "localhost",
        "DB_NAME": "test",
        "DB_USER": "test",
        "DB_PASSWORD": "test",
        "DB_AUTO_CREATE_TABLES": "false",
        "S3_BUCKET_NAME": "test-bucket",
        "AWS_REGION": "us-east-1",
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AGENT_STUB_DELAY_MS": "0",
    }
)

import boto3  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from moto import mock_aws  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import get_db, get_session_factory  # noqa: E402
from app.main import app  # noqa: E402
from app.services.s3 import S3Service, get_s3_service  # noqa: E402

TEST_BUCKET = "test-bucket"


@pytest.fixture
def session_factory():
    # SQLite en memoria en lugar de Postgres
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def s3_service():
    # moto simula S3 en memoria
    with mock_aws():
        s3_client = boto3.client("s3", region_name="us-east-1")
        s3_client.create_bucket(Bucket=TEST_BUCKET)
        yield S3Service(s3_client, TEST_BUCKET)


@pytest.fixture
def bucket_keys(s3_service):
    """Devuelve las keys que hay realmente en el bucket simulado."""

    def _keys() -> list[str]:
        resp = s3_service.client.list_objects_v2(Bucket=TEST_BUCKET)
        return sorted(obj["Key"] for obj in resp.get("Contents", []))

    return _keys


@pytest.fixture
def client(session_factory, s3_service):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_s3_service] = lambda: s3_service
    yield TestClient(app)
    app.dependency_overrides.clear()
