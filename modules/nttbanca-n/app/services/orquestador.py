"""Orquestador del asistente normativo: corre los agentes en orden y persiste cada paso.

Se ejecuta en segundo plano (BackgroundTasks) y nunca lanza excepciones: cualquier fallo
queda registrado en la ejecución con estado ERROR, sin afectar a la API.
"""

import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.agentes.buscador import buscador
from app.agentes.conflictos import conflictos
from app.agentes.contratos import SalidaBuscador, SalidaConflictos, SalidaRedactor, SalidaVigencia
from app.agentes.redactor import redactor
from app.agentes.vigencia import vigencia
from app.db.session import SessionLocal
from app.models.ejecucion import Ejecucion, PasoAgente
from app.models.enums import Agente, EstadoEjecucion, EstadoPaso

logger = logging.getLogger(__name__)

AgentFunction = Callable[[str, dict[str, Any]], dict[str, Any]]

# Orden del pipeline: (agente, función, contrato de su salida)
PIPELINE: list[tuple[Agente, AgentFunction, type[BaseModel]]] = [
    (Agente.BUSCADOR, buscador, SalidaBuscador),
    (Agente.VIGENCIA, vigencia, SalidaVigencia),
    (Agente.CONFLICTOS, conflictos, SalidaConflictos),
    (Agente.REDACTOR, redactor, SalidaRedactor),
]


def ejecutar_pipeline(ejecucion_id: uuid.UUID, session_factory: sessionmaker = SessionLocal) -> None:
    """Punto de entrada para BackgroundTasks: abre su propia sesión de BD."""
    with session_factory() as db:
        try:
            _run(db, ejecucion_id)
        except Exception:
            # Fallo fuera de los agentes (p. ej. la BD): se registra sin tumbar la API.
            logger.exception("Falló el orquestador en la ejecución %s", ejecucion_id)
            db.rollback()
            _mark_error(db, ejecucion_id)


def _run(db: Session, ejecucion_id: uuid.UUID) -> None:
    ejecucion = db.get(Ejecucion, ejecucion_id)
    if ejecucion is None:
        logger.error("No existe la ejecución %s", ejecucion_id)
        return

    contexto: dict[str, Any] = {}
    for orden, (agente, funcion, contrato) in enumerate(PIPELINE, start=1):
        ejecucion.paso_actual = agente.value
        ejecucion.estado = EstadoEjecucion.EN_PROCESO.value
        db.commit()

        inicio = time.perf_counter()
        try:
            salida = contrato.model_validate(funcion(ejecucion.pregunta, dict(contexto))).model_dump()
        except Exception as exc:
            logger.exception("El agente %s falló en la ejecución %s", agente, ejecucion_id)
            db.add(
                PasoAgente(
                    ejecucion_id=ejecucion.id,
                    agente=agente.value,
                    orden=orden,
                    estado=EstadoPaso.ERROR.value,
                    duracion_ms=_elapsed_ms(inicio),
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            ejecucion.estado = EstadoEjecucion.ERROR.value
            db.commit()
            return

        db.add(
            PasoAgente(
                ejecucion_id=ejecucion.id,
                agente=agente.value,
                orden=orden,
                estado=EstadoPaso.COMPLETADO.value,
                salida=salida,
                duracion_ms=_elapsed_ms(inicio),
            )
        )
        db.commit()
        contexto[agente.value] = salida

    ejecucion.respuesta = contexto[Agente.REDACTOR.value]["respuesta"]
    ejecucion.estado = EstadoEjecucion.COMPLETADO.value
    ejecucion.paso_actual = None
    db.commit()


def _mark_error(db: Session, ejecucion_id: uuid.UUID) -> None:
    try:
        ejecucion = db.get(Ejecucion, ejecucion_id)
        if ejecucion is not None:
            ejecucion.estado = EstadoEjecucion.ERROR.value
            db.commit()
    except Exception:
        logger.exception("No se pudo marcar la ejecución %s como ERROR", ejecucion_id)


def _elapsed_ms(inicio: float) -> int:
    return int((time.perf_counter() - inicio) * 1000)
