"""Contrato de salida de cada agente.

El orquestador valida cada salida contra su modelo: si un agente devuelve otra forma,
el paso queda en ERROR con el detalle de qué campo falta o sobra de tipo.
`documento_id` siempre es el id de la tabla items (el documento normativo).
"""

from typing import Literal

from pydantic import BaseModel


class ArticuloEncontrado(BaseModel):
    documento_id: int
    articulo: str
    fragmento: str
    score: float


class SalidaBuscador(BaseModel):
    articulos: list[ArticuloEncontrado]


class DocumentoDescartado(BaseModel):
    documento_id: int
    motivo: str
    reemplazado_por: int | None = None


class SalidaVigencia(BaseModel):
    vigentes: list[ArticuloEncontrado]
    descartados: list[DocumentoDescartado]


class Conflicto(BaseModel):
    documento_a: int
    documento_b: int
    tema: str
    descripcion: str


class SalidaConflictos(BaseModel):
    conflictos: list[Conflicto]


class Cita(BaseModel):
    documento_id: int
    articulo: str


class Alerta(BaseModel):
    tipo: Literal["CONFLICTO", "VIGENCIA"]
    mensaje: str


class SalidaRedactor(BaseModel):
    respuesta: str
    citas: list[Cita]
    alertas: list[Alerta]
