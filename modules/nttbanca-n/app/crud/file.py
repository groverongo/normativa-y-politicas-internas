from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.file import FileRecord
from app.schemas.file import FileUpdate


def get_file(db: Session, file_id: int) -> FileRecord | None:
    return db.get(FileRecord, file_id)


def list_files(
    db: Session, item_id: int | None = None, skip: int = 0, limit: int = 100
) -> Sequence[FileRecord]:
    stmt = select(FileRecord).order_by(FileRecord.id).offset(skip).limit(limit)
    if item_id is not None:
        stmt = stmt.where(FileRecord.item_id == item_id)
    return db.scalars(stmt).all()


def update_file(db: Session, record: FileRecord, data: FileUpdate) -> FileRecord:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    db.commit()
    db.refresh(record)
    return record
