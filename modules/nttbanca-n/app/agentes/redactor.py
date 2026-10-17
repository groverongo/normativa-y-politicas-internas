"""REDACTOR: arma la respuesta final para el analista, con citas y alertas.

STUB: redacta una respuesta de ejemplo a partir de la salida de los agentes anteriores.
Al conectar el LLM, mantén la firma y el contrato SalidaRedactor (app/agentes/contratos.py).
"""

from typing import Any

from app.agentes.demo import simular_trabajo


def redactor(pregunta: str, contexto_previo: dict[str, Any]) -> dict[str, Any]:
    simular_trabajo()
    vigentes = contexto_previo["VIGENCIA"]["vigentes"]
    descartados = contexto_previo["VIGENCIA"]["descartados"]
    conflictos = contexto_previo["CONFLICTOS"]["conflictos"]

    citas = [{"documento_id": a["documento_id"], "articulo": a["articulo"]} for a in vigentes]
    alertas = [{"tipo": "CONFLICTO", "mensaje": f"{c['tema']}: {c['descripcion']}"} for c in conflictos]
    alertas += [
        {
            "tipo": "VIGENCIA",
            "mensaje": f"El documento {d['documento_id']} no está vigente ({d['motivo']}); "
            f"reemplazado por el documento {d['reemplazado_por']}.",
        }
        for d in descartados
    ]

    fuentes = "; ".join(f"{a['articulo']} del documento {a['documento_id']}" for a in vigentes)
    respuesta = f"[Respuesta de ejemplo] Sobre «{pregunta}»: según {fuentes or 'las normas encontradas'}, "
    respuesta += "el plazo aplicable es de 30 días calendario."
    if conflictos:
        respuesta += " Ojo: hay diferencias con la política interna; revisa las alertas."

    return {"respuesta": respuesta, "citas": citas, "alertas": alertas}
