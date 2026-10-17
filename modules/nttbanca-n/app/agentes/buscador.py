"""BUSCADOR: encuentra los artículos de normas SBS y políticas internas relevantes para la pregunta.

STUB con datos de ejemplo. Al conectar el LLM o la búsqueda real, mantén la firma y el
contrato SalidaBuscador (app/agentes/contratos.py).
"""

from typing import Any

from app.agentes.demo import simular_trabajo


def buscador(pregunta: str, contexto_previo: dict[str, Any]) -> dict[str, Any]:
    simular_trabajo()
    return {
        "articulos": [
            {
                "documento_id": 1,
                "articulo": "Artículo 5",
                "fragmento": "[Ejemplo] Las empresas deben reportar a la SBS los eventos de pérdida "
                "significativos dentro de los 30 días calendario.",
                "score": 0.92,
            },
            {
                "documento_id": 2,
                "articulo": "Artículo 12",
                "fragmento": "[Ejemplo] El reporte de eventos de pérdida se presenta en un plazo de 60 días.",
                "score": 0.85,
            },
            {
                "documento_id": 3,
                "articulo": "Numeral 4.2",
                "fragmento": "[Ejemplo] Las áreas de negocio reportan los eventos de pérdida a Riesgos "
                "en un plazo máximo de 45 días.",
                "score": 0.78,
            },
        ]
    }
