from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import EstadoDocumento

if TYPE_CHECKING:
    from app.models.file import FileRecord


class Item(Base):
    """Documento normativo (norma SBS o política interna); sus archivos están en `files`."""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tipo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    codigo_norma: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    fecha_vigencia: Mapped[date | None] = mapped_column(Date, nullable=True)
    estado: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=EstadoDocumento.VIGENTE.value,
        server_default=EstadoDocumento.VIGENTE.value,
    )
    # Documento anterior que este reemplaza (p. ej. una norma derogada por esta)
    reemplaza_a: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    files: Mapped[list["FileRecord"]] = relationship(back_populates="item", cascade="all, delete-orphan")
