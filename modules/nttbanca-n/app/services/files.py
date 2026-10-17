"""Operaciones que tocan S3 y Postgres a la vez.

Regla de consistencia: un registro de la BD nunca debe apuntar a un objeto
que no existe. Por eso:
- Al subir: primero S3, luego BD. Si la BD falla, se borra el objeto subido.
- Al borrar: primero BD, luego S3. Si S3 falla, el objeto queda huérfano
  (se registra en el log) pero ningún registro apunta a algo inexistente.
"""

import logging
from collections.abc import Iterable
from pathlib import PureWindowsPath

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.crud import item as item_crud
from app.models.file import FileRecord
from app.models.item import Item
from app.services.s3 import S3Service

logger = logging.getLogger(__name__)


def _clean_filename(filename: str | None) -> str:
    # PureWindowsPath quita rutas tanto con "/" como con "\"
    name = PureWindowsPath(filename or "").name.strip()
    return (name or "archivo")[:255]


def delete_objects_safely(s3: S3Service, pointers: Iterable[tuple[str, str]]) -> None:
    for bucket, key in pointers:
        try:
            s3.delete(key, bucket=bucket)
        except (BotoCoreError, ClientError):
            logger.exception("No se pudo borrar s3://%s/%s; quedó huérfano en S3", bucket, key)


def _upload(s3: S3Service, upload: UploadFile) -> tuple[str, str, dict]:
    filename = _clean_filename(upload.filename)
    key = s3.new_key(filename)
    meta = s3.upload(key, upload.file, upload.content_type)
    return key, filename, meta


def _apply_object_metadata(record: FileRecord, bucket: str, key: str, filename: str, meta: dict) -> None:
    record.bucket = bucket
    record.s3_key = key
    record.original_filename = filename
    record.content_type = meta.get("ContentType")
    record.size_bytes = meta["ContentLength"]
    record.etag = meta["ETag"].strip('"')


def create_file(db: Session, s3: S3Service, upload: UploadFile, item_id: int | None = None) -> FileRecord:
    key, filename, meta = _upload(s3, upload)
    record = FileRecord(item_id=item_id)
    _apply_object_metadata(record, s3.bucket, key, filename, meta)
    try:
        db.add(record)
        db.commit()
    except Exception:
        db.rollback()
        delete_objects_safely(s3, [(s3.bucket, key)])
        raise
    db.refresh(record)
    return record


def replace_file_content(db: Session, s3: S3Service, record: FileRecord, upload: UploadFile) -> FileRecord:
    # Se sube con una key nueva y el objeto anterior se borra solo tras el commit,
    # así el registro siempre apunta a un objeto completo.
    old_pointer = (record.bucket, record.s3_key)
    key, filename, meta = _upload(s3, upload)
    _apply_object_metadata(record, s3.bucket, key, filename, meta)
    try:
        db.commit()
    except Exception:
        db.rollback()
        delete_objects_safely(s3, [(s3.bucket, key)])
        raise
    delete_objects_safely(s3, [old_pointer])
    db.refresh(record)
    return record


def delete_file(db: Session, s3: S3Service, record: FileRecord) -> None:
    pointer = (record.bucket, record.s3_key)
    db.delete(record)
    db.commit()
    delete_objects_safely(s3, [pointer])


def delete_item_with_files(db: Session, s3: S3Service, item: Item) -> None:
    pointers = [(f.bucket, f.s3_key) for f in item.files]
    item_crud.delete_item(db, item)  # cascade borra los registros de files
    delete_objects_safely(s3, pointers)
