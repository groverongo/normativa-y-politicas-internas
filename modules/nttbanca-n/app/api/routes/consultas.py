import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, sessionmaker

from app.crud import ejecucion as crud
from app.db.session import get_db, get_session_factory
from app.schemas.consulta import ConsultaCreada, ConsultaCreate, EjecucionDetalle, EjecucionResumen
from app.services.orquestador import ejecutar_pipeline

router = APIRouter(tags=["consultas (asistente normativo)"])


@router.post("/consultas", response_model=ConsultaCreada, status_code=status.HTTP_202_ACCEPTED)
def create_consulta(
    data: ConsultaCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    session_factory: sessionmaker = Depends(get_session_factory),
):
    """Registra la pregunta y lanza el pipeline en segundo plano; responde de inmediato."""
    ejecucion = crud.create_ejecucion(db, pregunta=data.pregunta, sesion_id=data.sesion_id or uuid.uuid4())
    background_tasks.add_task(ejecutar_pipeline, ejecucion.id, session_factory)
    return ConsultaCreada(ejecucion_id=ejecucion.id, sesion_id=ejecucion.sesion_id, estado=ejecucion.estado)


@router.get("/consultas/{ejecucion_id}", response_model=EjecucionDetalle)
def get_consulta(ejecucion_id: uuid.UUID, db: Session = Depends(get_db)):
    """Estado de la ejecución y sus pasos en orden. Pensado para polling cada 1-2 s."""
    ejecucion = crud.get_ejecucion_con_pasos(db, ejecucion_id)
    if ejecucion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consulta no encontrada")
    return ejecucion


@router.get("/sesiones/{sesion_id}/consultas", response_model=list[EjecucionResumen])
def list_consultas_de_sesion(
    sesion_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Historial de la sesión, más reciente primero."""
    return crud.list_ejecuciones_de_sesion(db, sesion_id, limit=limit)
