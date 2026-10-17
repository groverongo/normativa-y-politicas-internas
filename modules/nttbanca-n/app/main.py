import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from app import models  # noqa: F401  (registra los modelos en Base.metadata)
from app.api.routes import consultas, files, health, ingest, items
from app.core.config import get_settings
from app.db.migrate import run_migrations
from app.db.session import engine

settings = get_settings()
logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.db_auto_create_tables:
        try:
            applied = run_migrations(engine)
            logger.info("Migraciones aplicadas: %s", ", ".join(applied) if applied else "ninguna pendiente")
        except SQLAlchemyError:
            # No tumbamos la app: /health/db mostrará el problema de conexión.
            logger.exception("No se pudieron aplicar las migraciones en Postgres")
    yield
    engine.dispose()


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

app.include_router(health.router)
app.include_router(items.router)
app.include_router(files.router)
app.include_router(consultas.router)
app.include_router(ingest.router)
