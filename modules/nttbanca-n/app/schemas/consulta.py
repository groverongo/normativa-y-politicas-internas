import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Agente, EstadoEjecucion, EstadoPaso


class ConsultaCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    sesion_id: uuid.UUID | None = Field(None, description="Si se omite, se crea una sesión nueva.")
    pregunta: str = Field(..., min_length=1, max_length=4000)


class ConsultaCreada(BaseModel):
    ejecucion_id: uuid.UUID
    sesion_id: uuid.UUID
    estado: EstadoEjecucion


class PasoAgenteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agente: Agente
    orden: int
    estado: EstadoPaso
    salida: dict[str, Any] | None
    duracion_ms: int
    error: str | None
    creado_en: datetime


class EjecucionResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sesion_id: uuid.UUID
    pregunta: str
    estado: EstadoEjecucion
    paso_actual: Agente | None
    respuesta: str | None
    creado_en: datetime
    actualizado_en: datetime


class EjecucionDetalle(EjecucionResumen):
    pasos: list[PasoAgenteRead]
