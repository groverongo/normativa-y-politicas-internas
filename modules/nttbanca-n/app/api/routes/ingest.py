"""HTTP entry points for the ingestion pipeline, mirroring
modules/ingesta/api.py's /ingest, /ingest/batch, /documents, /documents/{doc_id}.

Additive: independent of /items, /files, /consultas. A request-scoped
DocumentGraphStorage + InteractionLogger share the same Session as the rest
of the app (via get_db), so a pipeline run and its interaction-log rows
commit together.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.lifecycle import CatalogEntry, DocumentMetadata, IngestionResult
from app.services.document_graph_storage import DocumentGraphStorage
from app.services.ingestion_logger import InteractionLogger
from app.services.ingestion_pipeline import IngestionPipeline
from app.services.llm_provider import get_provider
from app.services.s3 import S3Service, get_s3_service

router = APIRouter(tags=["ingest (pipeline de clasificación de vigencia)"])


class IngestRequest(BaseModel):
    source_name: str
    text: str


class IngestBatchRequest(BaseModel):
    documents: list[IngestRequest] = Field(default_factory=list)


def _build_pipeline(db: Session, settings: Settings, s3: S3Service) -> IngestionPipeline:
    storage = DocumentGraphStorage(db, s3)
    logger = InteractionLogger(db)
    llm = get_provider(settings)
    return IngestionPipeline(storage, llm, logger, settings)


@router.post("/ingest", response_model=IngestionResult, status_code=status.HTTP_201_CREATED)
def ingest(
    data: IngestRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    s3: S3Service = Depends(get_s3_service),
):
    pipeline = _build_pipeline(db, settings, s3)
    result = pipeline.ingest_document(data.text, data.source_name)
    db.commit()
    return result


@router.post("/ingest/batch", response_model=list[IngestionResult])
def ingest_batch(
    data: IngestBatchRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    s3: S3Service = Depends(get_s3_service),
):
    pipeline = _build_pipeline(db, settings, s3)
    results = [pipeline.ingest_document(doc.text, doc.source_name) for doc in data.documents]
    db.commit()
    return results


@router.get("/documents", response_model=list[CatalogEntry])
def list_documents(db: Session = Depends(get_db), s3: S3Service = Depends(get_s3_service)):
    storage = DocumentGraphStorage(db, s3)
    return storage.catalog()


@router.get("/documents/{doc_id}", response_model=DocumentMetadata)
def get_document(doc_id: str, db: Session = Depends(get_db), s3: S3Service = Depends(get_s3_service)):
    storage = DocumentGraphStorage(db, s3)
    metadata = storage.get_document(doc_id)
    if metadata is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento no encontrado")
    return metadata
