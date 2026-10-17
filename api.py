"""FastAPI layer exposing the ingestion pipeline over HTTP.

This is synchronous request/response only: a client POSTs document text and
gets an IngestionResult back in the same call.

# TODO: a producer/consumer (message-queue) integration -- e.g. an async
# worker that pulls documents off a queue and calls `run_ingest()` below,
# publishing results back onto another queue/topic -- is explicitly out of
# scope and not planned to be implemented. This module only supports direct
# synchronous HTTP request/response communication.

Run with:
    uvicorn api:app --reload --port 8000

Storage is a single shared, process-lifetime InMemoryStorage instance (per
the spec, this stands in for the real S3/DB layer being built separately --
see storage.py's `# TODO: link to real S3/DB client` markers). Optionally
seed it at startup with SEED_PATH=sample_docs/seed_corpus.json.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config import Settings
from llm_provider import LLMError, get_provider
from logging_trace import InteractionLogger
from pipeline import IngestionPipeline
from schema import CatalogEntry, DocumentMetadata, IngestionResult
from storage import InMemoryStorage

settings = Settings.from_env()

try:
    provider = get_provider(settings)
except LLMError as exc:
    raise RuntimeError(f"failed to initialize LLM provider at startup: {exc}") from exc

_seed_path = os.environ.get("SEED_PATH")
storage = InMemoryStorage.from_seed_file(Path(_seed_path)) if _seed_path else InMemoryStorage()

# InMemoryStorage is not thread-safe, and FastAPI runs sync `def` routes in a
# thread pool; one lock serializes pipeline runs so concurrent requests can't
# interleave mutations on the shared storage/logger.
_pipeline_lock = threading.Lock()

app = FastAPI(
    title="Regulatory Document Ingestion API",
    description=(
        "Multi-agent lifecycle classification and metadata-graph ingestion "
        "for regulatory/policy documents. Synchronous request/response only."
    ),
    version="0.1.0",
)


class DocumentIn(BaseModel):
    source_name: str = Field(..., description="Filename or logical identifier for the document")
    text: str = Field(..., description="Raw document text")


class BatchIngestIn(BaseModel):
    documents: list[DocumentIn]


class IngestResponse(BaseModel):
    run_id: str
    results: list[IngestionResult]


def run_ingest(documents: list[DocumentIn]) -> IngestResponse:
    """Shared core used by both /ingest and /ingest/batch (and, if ever
    added, a future queue consumer -- see the module TODO above)."""
    with _pipeline_lock:
        logger = InteractionLogger(settings.runs_dir)
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
        logger.close()
    return IngestResponse(run_id=run_id, results=results)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "llm_provider": settings.llm_provider, "documents_in_storage": len(storage.catalog())}


@app.post("/ingest", response_model=IngestResponse)
def ingest_one(doc: DocumentIn) -> IngestResponse:
    return run_ingest([doc])


@app.post("/ingest/batch", response_model=IngestResponse)
def ingest_batch(batch: BatchIngestIn) -> IngestResponse:
    if not batch.documents:
        raise HTTPException(status_code=422, detail="documents must be a non-empty list")
    return run_ingest(batch.documents)


@app.get("/documents", response_model=list[CatalogEntry])
def list_documents() -> list[CatalogEntry]:
    return storage.catalog()


@app.get("/documents/{doc_id}", response_model=DocumentMetadata)
def get_document(doc_id: str) -> DocumentMetadata:
    meta = storage.get_document(doc_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"document not found: {doc_id}")
    return meta


@app.get("/runs/{run_id}/log")
def get_run_log(run_id: str) -> list[dict[str, Any]]:
    log_path = settings.runs_dir / run_id / "interaction_log.jsonl"
    if not log_path.exists():
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]


@app.get("/runs/{run_id}/summary")
def get_run_summary(run_id: str) -> Any:
    path = settings.runs_dir / run_id / "summary.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    return json.loads(path.read_text(encoding="utf-8"))
