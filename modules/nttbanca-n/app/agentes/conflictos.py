"""CONFLICTOS: detecta contradicciones entre los artículos vigentes (p. ej. norma SBS vs. política interna).

STUB con datos de ejemplo: marca un conflicto entre los dos primeros artículos vigentes.
Al conectar el LLM, mantén la firma y el contrato SalidaConflictos (app/agentes/contratos.py).
"""

from typing import Any

from app.agentes.demo import simular_trabajo


def conflictos(pregunta: str, contexto_previo: dict[str, Any]) -> dict[str, Any]:
    simular_trabajo()
    vigentes = contexto_previo["VIGENCIA"]["vigentes"]
    encontrados = []
    if len(vigentes) >= 2:
        a, b = vigentes[0], vigentes[1]
        encontrados.append(
            {
                "documento_a": a["documento_id"],
                "documento_b": b["documento_id"],
                "tema": "Plazo de reporte de eventos de pérdida",
                "descripcion": f"[Ejemplo] {a['articulo']} fija 30 días y {b['articulo']} fija 45 días.",
            }
        )
    return {"conflictos": encontrados}
