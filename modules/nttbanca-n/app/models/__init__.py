# Importar aquí todos los modelos para que Base.metadata los registre.
from app.models.document import (
    Document,
    DocumentChunk,
    DocumentDefinitionSource,
    DocumentLineage,
    DocumentPatchRecord,
)
from app.models.ejecucion import Ejecucion, PasoAgente
from app.models.file import FileRecord
from app.models.ingestion_log import IngestionLogEntry
from app.models.item import Item

__all__ = [
    "Document",
    "DocumentChunk",
    "DocumentDefinitionSource",
    "DocumentLineage",
    "DocumentPatchRecord",
    "Ejecucion",
    "FileRecord",
    "IngestionLogEntry",
    "Item",
    "PasoAgente",
]
