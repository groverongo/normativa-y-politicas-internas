"""FastAPI layer exposing the ingestion pipeline over HTTP.

This is synchronous request/response only: a client POSTs document text and
gets an IngestionResult back in the same call. A producer/consumer
(message-queue) integration is explicitly out of scope -- see README.md
section 9.5.

Run with:
    uvicorn api:app --reload --port 8000

Storage is a single shared, process-lifetime StorageInterface instance (see
storage.get_storage) -- in-memory by default (STORAGE_BACKEND=memory), or the
real S3/Postgres-backed storage.S3DbStorage when STORAGE_BACKEND=postgres.
SEED_PATH=sample_docs/seed_corpus.json preloads it at startup; seeding is only
supported with the memory backend.
"""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config import Settings
from llm_provider import LLMError, LLMProvider, get_provider
from logging_trace import InteractionLogger
from pipeline import IngestionPipeline
from schema import CatalogEntry, DocumentMetadata, IngestionResult
from storage import InMemoryStorage, StorageError, StorageInterface, get_storage

# Populated by `lifespan` on startup (not at import time), so a misconfigured
# provider or seed file fails with a clear FastAPI startup error instead of
# crashing module import, and tests can run against a fresh instance per app.
settings: Settings
provider: LLMProvider
storage: StorageInterface

# Storage backends are not guaranteed thread-safe (InMemoryStorage isn't, and
# S3DbStorage holds one shared connection), and FastAPI runs sync `def` routes
# in a thread pool; one lock serializes all storage access (reads and writes)
# so concurrent requests can't interleave mutations or race with reads.
_storage_lock = Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global settings, provider, storage
    settings = Settings.from_env()

    try:
        provider = get_provider(settings)
    except LLMError as exc:
        raise RuntimeError(f"failed to initialize LLM provider at startup: {exc}") from exc

    seed_path = os.environ.get("SEED_PATH")
    if seed_path and settings.storage_backend != "memory":
        raise RuntimeError(
            f"SEED_PATH is only supported with the memory storage backend "
            f"(STORAGE_BACKEND={settings.storage_backend!r})"
        )
    if seed_path:
        try:
            storage = InMemoryStorage.from_seed_file(Path(seed_path))
        except Exception as exc:
            raise RuntimeError(f"failed to load seed file {seed_path!r}: {exc}") from exc
    else:
        try:
            storage = get_storage(settings)
        except StorageError as exc:
            raise RuntimeError(f"failed to initialize storage backend at startup: {exc}") from exc

    yield


app = FastAPI(
    title="Regulatory Document Ingestion API",
    description=(
        "Multi-agent lifecycle classification and metadata-graph ingestion "
        "for regulatory/policy documents. Synchronous request/response only."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


class DocumentIn(BaseModel):
    source_name: str = Field(..., min_length=1, description="Filename or logical identifier for the document")
    text: str = Field(..., min_length=1, description="Raw document text")


class BatchIngestIn(BaseModel):
    documents: list[DocumentIn] = Field(..., min_length=1)


class IngestResponse(BaseModel):
    run_id: str
    results: list[IngestionResult]
    has_errors: bool = Field(description="True if any document in this run produced errors")


class HealthResponse(BaseModel):
    status: str
    llm_provider: str
    documents_in_storage: int


def run_ingest(documents: list[DocumentIn]) -> IngestResponse:
    """Shared core used by both /ingest and /ingest/batch."""
    with _storage_lock:
        logger = InteractionLogger(settings.runs_dir)
        try:
            pipeline = IngestionPipeline(storage, provider, logger, settings)
            logger.log(
                "run_start",
                agent="pipeline",
                message=f"API run over {len(documents)} document(s)",
                input={"source_files": [d.source_name for d in documents]},
            )
            results = [pipeline.ingest_document(d.text, d.source_name) for d in documents]
            logger.log(
                "run_end",
                agent="pipeline",
                message=f"processed {len(results)} document(s)",
                output={"count": len(results), "documents_with_errors": sum(1 for r in results if r.errors)},
            )
            logger.write_json("summary.json", results)
            logger.write_json("storage_snapshot.json", storage.snapshot())
            run_id = logger.run_id
        finally:
            logger.close()
    has_errors = any(r.errors for r in results)
    return IngestResponse(run_id=run_id, results=results, has_errors=has_errors)


def _run_file_text(run_id: str, filename: str) -> str:
    if "/" in run_id or "\\" in run_id or run_id in (".", ".."):
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    path = settings.runs_dir / run_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    return path.read_text(encoding="utf-8")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    with _storage_lock:
        doc_count = len(storage.catalog())
    return HealthResponse(status="ok", llm_provider=settings.llm_provider, documents_in_storage=doc_count)


@app.post("/ingest", response_model=IngestResponse)
def ingest_one(doc: DocumentIn) -> IngestResponse:
    return run_ingest([doc])


@app.post("/ingest/batch", response_model=IngestResponse)
def ingest_batch(batch: BatchIngestIn) -> IngestResponse:
    return run_ingest(batch.documents)


@app.get("/documents", response_model=list[CatalogEntry])
def list_documents() -> list[CatalogEntry]:
    with _storage_lock:
        return storage.catalog()


@app.get("/documents/{doc_id}", response_model=DocumentMetadata)
def get_document(doc_id: str) -> DocumentMetadata:
    with _storage_lock:
        meta = storage.get_document(doc_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"document not found: {doc_id}")
    return meta


@app.get("/runs/{run_id}/log")
def get_run_log(run_id: str) -> list[dict[str, Any]]:
    text = _run_file_text(run_id, "interaction_log.jsonl")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


@app.get("/runs/{run_id}/summary", response_model=list[IngestionResult])
def get_run_summary(run_id: str) -> list[IngestionResult]:
    text = _run_file_text(run_id, "summary.json")
    return json.loads(text)
