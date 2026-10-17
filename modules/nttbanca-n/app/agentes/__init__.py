"""Agentes del asistente normativo.

Cada agente es una función independiente con la firma
    (pregunta: str, contexto_previo: dict) -> dict
donde contexto_previo trae la salida de los agentes anteriores, por nombre
(p. ej. contexto_previo["BUSCADOR"]). La forma de cada salida está en contratos.py.
"""
