import logging

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.s3 import S3Service, get_s3_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health():
    return {"status": "ok"}


@router.get("/db")
def health_db(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.exception("Fallo el health check de Postgres")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Postgres: {exc.__class__.__name__}")
    return {"status": "ok", "service": "postgres"}


@router.get("/s3")
def health_s3(s3: S3Service = Depends(get_s3_service)):
    try:
        s3.check_bucket()
    except (BotoCoreError, ClientError) as exc:
        logger.exception("Fallo el health check de S3")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"S3: {exc}")
    return {"status": "ok", "service": "s3", "bucket": s3.bucket}
