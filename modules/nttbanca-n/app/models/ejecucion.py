import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import EstadoEjecucion


def _now() -> datetime:
    # Con microsegundos: el historial se ordena bien aunque haya varias consultas por segundo.
    return datetime.now(UTC)


class Ejecucion(Base):
    """Una pregunta del analista y el avance del pipeline de agentes."""

    __tablename__ = "ejecucion"
    __table_args__ = (Index("ix_ejecucion_sesion_id_creado_en", "sesion_id", "creado_en"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sesion_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    pregunta: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default=EstadoEjecucion.PENDIENTE.value)
    paso_actual: Mapped[str | None] = mapped_column(String(20), nullable=True)
    respuesta: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now, server_default=func.now()
    )

    pasos: Mapped[list["PasoAgente"]] = relationship(
        back_populates="ejecucion", order_by="PasoAgente.orden", cascade="all, delete-orphan"
    )


class PasoAgente(Base):
    """Resultado de un agente dentro de una ejecución."""

    __tablename__ = "paso_agente"
    __table_args__ = (UniqueConstraint("ejecucion_id", "orden", name="uq_paso_agente_ejecucion_orden"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ejecucion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ejecucion.id", ondelete="CASCADE"), nullable=False
    )
    agente: Mapped[str] = mapped_column(String(20), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    # JSONB en PostgreSQL; JSON en otras bases (los tests usan SQLite)
    salida: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    duracion_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now()
    )

    ejecucion: Mapped[Ejecucion] = relationship(back_populates="pasos")
