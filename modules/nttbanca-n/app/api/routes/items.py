from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.crud import file as file_crud
from app.crud import item as crud
from app.db.session import get_db
from app.models.item import Item
from app.schemas.file import FileRead
from app.schemas.item import ItemCreate, ItemRead, ItemUpdate
from app.services.files import delete_item_with_files
from app.services.s3 import S3Service, get_s3_service

router = APIRouter(prefix="/items", tags=["items (Postgres)"])


def get_item_or_404(item_id: int, db: Session = Depends(get_db)) -> Item:
    item = crud.get_item(db, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item no encontrado")
    return item


def ensure_replaced_exists(db: Session, reemplaza_a: int | None, item_id: int | None = None) -> None:
    if reemplaza_a is None:
        return
    if reemplaza_a == item_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Un documento no puede reemplazarse a sí mismo"
        )
    if crud.get_item(db, reemplaza_a) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento a reemplazar no encontrado")


@router.post("", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
def create_item(data: ItemCreate, db: Session = Depends(get_db)):
    ensure_replaced_exists(db, data.reemplaza_a)
    return crud.create_item(db, data)


@router.get("", response_model=list[ItemRead])
def list_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return crud.list_items(db, skip=skip, limit=limit)


@router.get("/{item_id}", response_model=ItemRead)
def get_item(item: Item = Depends(get_item_or_404)):
    return item


@router.get("/{item_id}/files", response_model=list[FileRead])
def list_item_files(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    item: Item = Depends(get_item_or_404),
    db: Session = Depends(get_db),
):
    return file_crud.list_files(db, item_id=item.id, skip=skip, limit=limit)


@router.patch("/{item_id}", response_model=ItemRead)
def update_item(data: ItemUpdate, item: Item = Depends(get_item_or_404), db: Session = Depends(get_db)):
    ensure_replaced_exists(db, data.reemplaza_a, item_id=item.id)
    return crud.update_item(db, item, data)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item: Item = Depends(get_item_or_404),
    db: Session = Depends(get_db),
    s3: S3Service = Depends(get_s3_service),
):
    """Borra el item, sus registros de archivos y los objetos en S3."""
    delete_item_with_files(db, s3, item)
