from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int | None
    original_filename: str
    content_type: str | None
    size_bytes: int
    etag: str | None
    bucket: str
    s3_key: str
    created_at: datetime
    updated_at: datetime


class FileUpdate(BaseModel):
    """Solo metadatos; para cambiar el contenido se usa PUT."""

    original_filename: str | None = Field(None, min_length=1, max_length=255)
    item_id: int | None = Field(None, description="null desvincula el archivo del item.")

    @field_validator("original_filename")
    @classmethod
    def not_null(cls, value: str | None) -> str:
        # Omitirlo está permitido; enviarlo explícitamente como null no.
        if value is None:
            raise ValueError("no puede ser null")
        return value


class PresignedUrl(BaseModel):
    id: int
    url: str
    expires_in: int
