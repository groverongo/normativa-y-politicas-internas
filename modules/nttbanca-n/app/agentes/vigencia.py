"""VIGENCIA: separa los artículos de documentos vigentes de los derogados o reemplazados.

STUB con datos de ejemplo: trata el documento 2 como derogado y reemplazado por el 1.
Al conectar la lógica real (consultando items.estado y items.reemplaza_a), mantén la
firma y el contrato SalidaVigencia (app/agentes/contratos.py).
"""

from typing import Any

from app.agentes.demo import simular_trabajo

_DEROGADOS_EJEMPLO = {2: 1}  # documento derogado -> documento que lo reemplaza


def vigencia(pregunta: str, contexto_previo: dict[str, Any]) -> dict[str, Any]:
    simular_trabajo()
    articulos = contexto_previo["BUSCADOR"]["articulos"]
    vigentes = [a for a in articulos if a["documento_id"] not in _DEROGADOS_EJEMPLO]
    descartados = [
        {
            "documento_id": a["documento_id"],
            "motivo": "[Ejemplo] Norma derogada",
            "reemplazado_por": _DEROGADOS_EJEMPLO[a["documento_id"]],
        }
        for a in articulos
        if a["documento_id"] in _DEROGADOS_EJEMPLO
    ]
    return {"vigentes": vigentes, "descartados": descartados}
