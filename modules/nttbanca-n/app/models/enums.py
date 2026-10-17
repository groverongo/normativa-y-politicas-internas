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
