from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import EstadoDocumento, TipoDocumento


class ItemBase(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    is_active: bool = True
    tipo: TipoDocumento | None = None
    codigo_norma: str | None = None
    fecha_vigencia: date | None = None
    estado: EstadoDocumento = EstadoDocumento.VIGENTE
    reemplaza_a: int | None = Field(None, description="id del documento que este reemplaza.")


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    is_active: bool | None = None
    tipo: TipoDocumento | None = None
    codigo_norma: str | None = None
    fecha_vigencia: date | None = None
    estado: EstadoDocumento | None = None
    reemplaza_a: int | None = Field(None, description="null quita el reemplazo.")

    @field_validator("name", "is_active", "estado")
    @classmethod
    def not_null(cls, value):
        # Omitirlos está permitido; enviarlos explícitamente como null no.
        if value is None:
            raise ValueError("no puede ser null")
        return value


class ItemRead(ItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
