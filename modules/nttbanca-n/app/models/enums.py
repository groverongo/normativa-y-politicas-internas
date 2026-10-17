"""Valores permitidos del asistente normativo. En la BD se guardan como texto (VARCHAR + CHECK)."""

from enum import StrEnum


class TipoDocumento(StrEnum):
    SBS = "SBS"
    POLITICA_INTERNA = "POLITICA_INTERNA"


class EstadoDocumento(StrEnum):
    VIGENTE = "VIGENTE"
    DEROGADA = "DEROGADA"


class EstadoEjecucion(StrEnum):
    PENDIENTE = "PENDIENTE"
    EN_PROCESO = "EN_PROCESO"
    COMPLETADO = "COMPLETADO"
    ERROR = "ERROR"


class Agente(StrEnum):
    BUSCADOR = "BUSCADOR"
    VIGENCIA = "VIGENCIA"
    CONFLICTOS = "CONFLICTOS"
    REDACTOR = "REDACTOR"


class EstadoPaso(StrEnum):
    COMPLETADO = "COMPLETADO"
    ERROR = "ERROR"


class DocStatus(StrEnum):
    """Lifecycle status of a `documents` row (ingestion pipeline), ported from
    modules/ingesta/schema.py's DocStatus."""

    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    PARTIALLY_SUPERSEDED = "PARTIALLY_SUPERSEDED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class LineageRelation(StrEnum):
    """Edge type in `document_lineage` (ingestion pipeline), ported from
    modules/ingesta/schema.py's LineageMetadata field names."""

    SUPERSEDES = "supersedes"
    SUPERSEDED_BY = "superseded_by"
    AMENDS = "amends"
    PATCHED_BY = "patched_by"
    CONSOLIDATES = "consolidates"
    SPLIT_FROM = "split_from"
    SPLIT_INTO = "split_into"
    CONTRADICTS = "contradicts"
    REVOKES = "revokes"
    REVOKED_BY = "revoked_by"
    OVERRIDES = "overrides"
    OVERRIDDEN_BY = "overridden_by"
    IMPACTS = "impacts"
