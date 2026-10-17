from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.crud import file as crud
from app.crud.item import get_item
from app.db.session import get_db
from app.models.file import FileRecord
from app.schemas.file import FileRead, FileUpdate, PresignedUrl
from app.services import files as file_service
from app.services.s3 import S3ObjectNotFoundError, S3Service, content_disposition, get_s3_service

router = APIRouter(prefix="/files", tags=["files (Postgres + S3)"])


def get_file_or_404(file_id: int, db: Session = Depends(get_db)) -> FileRecord:
    record = crud.get_file(db, file_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado")
    return record


def ensure_item_exists(db: Session, item_id: int | None) -> None:
    if item_id is not None and get_item(db, item_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item no encontrado")


def _missing_in_s3(record: FileRecord) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"El registro existe pero el objeto no está en S3: s3://{record.bucket}/{record.s3_key}",
    )


@router.post("", response_model=FileRead, status_code=status.HTTP_201_CREATED)
def upload_file(
    file: UploadFile = File(...),
    item_id: int | None = Form(None, description="Item al que se asocia el archivo (opcional)."),
    db: Session = Depends(get_db),
    s3: S3Service = Depends(get_s3_service),
):
    ensure_item_exists(db, item_id)
    return file_service.create_file(db, s3, file, item_id)


@router.get("", response_model=list[FileRead])
def list_files(
    item_id: int | None = Query(None, description="Filtrar por item."),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return crud.list_files(db, item_id=item_id, skip=skip, limit=limit)


@router.get("/{file_id}", response_model=FileRead)
def get_file(record: FileRecord = Depends(get_file_or_404)):
    return record


@router.get("/{file_id}/download")
def download_file(record: FileRecord = Depends(get_file_or_404), s3: S3Service = Depends(get_s3_service)):
    try:
        chunks, obj = s3.download(record.s3_key, bucket=record.bucket)
    except S3ObjectNotFoundError:
        raise _missing_in_s3(record)
    return StreamingResponse(
        chunks,
        media_type=record.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": content_disposition(record.original_filename),
            "Content-Length": str(obj["ContentLength"]),
        },
    )


@router.get("/{file_id}/presigned-url", response_model=PresignedUrl)
def get_presigned_url(
    expires_in: int | None = Query(
        None, ge=60, le=604800, description="Segundos de validez (máx. 7 días). Por defecto el valor del .env."
    ),
    record: FileRecord = Depends(get_file_or_404),
    s3: S3Service = Depends(get_s3_service),
):
    expires_in = expires_in or s3.presigned_expiration
    url = s3.presigned_url(
        record.s3_key, bucket=record.bucket, expires_in=expires_in, filename=record.original_filename
    )
    return PresignedUrl(id=record.id, url=url, expires_in=expires_in)


@router.put("/{file_id}", response_model=FileRead)
def replace_file(
    file: UploadFile = File(...),
    record: FileRecord = Depends(get_file_or_404),
    db: Session = Depends(get_db),
    s3: S3Service = Depends(get_s3_service),
):
    return file_service.replace_file_content(db, s3, record, file)


@router.patch("/{file_id}", response_model=FileRead)
def update_file(
    data: FileUpdate,
    record: FileRecord = Depends(get_file_or_404),
    db: Session = Depends(get_db),
):
    ensure_item_exists(db, data.item_id)
    return crud.update_file(db, record, data)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    record: FileRecord = Depends(get_file_or_404),
    db: Session = Depends(get_db),
    s3: S3Service = Depends(get_s3_service),
):
    file_service.delete_file(db, s3, record)
