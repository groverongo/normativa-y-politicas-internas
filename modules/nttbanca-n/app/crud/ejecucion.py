import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.ejecucion import Ejecucion
from app.models.enums import EstadoEjecucion


def create_ejecucion(db: Session, pregunta: str, sesion_id: uuid.UUID) -> Ejecucion:
    ejecucion = Ejecucion(pregunta=pregunta, sesion_id=sesion_id, estado=EstadoEjecucion.PENDIENTE.value)
    db.add(ejecucion)
    db.commit()
    db.refresh(ejecucion)
    return ejecucion


def get_ejecucion_con_pasos(db: Session, ejecucion_id: uuid.UUID) -> Ejecucion | None:
    stmt = select(Ejecucion).where(Ejecucion.id == ejecucion_id).options(selectinload(Ejecucion.pasos))
    return db.scalar(stmt)


def list_ejecuciones_de_sesion(db: Session, sesion_id: uuid.UUID, limit: int = 50) -> Sequence[Ejecucion]:
    stmt = (
        select(Ejecucion)
        .where(Ejecucion.sesion_id == sesion_id)
        .order_by(Ejecucion.creado_en.desc())
        .limit(limit)
    )
    return db.scalars(stmt).all()
