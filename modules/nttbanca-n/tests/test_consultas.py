import uuid

from sqlalchemy import select

from app.models.ejecucion import Ejecucion
from app.models.enums import Agente
from app.services import orquestador

AGENTES = ["BUSCADOR", "VIGENCIA", "CONFLICTOS", "REDACTOR"]


def _replace_agent(monkeypatch, agente: Agente, funcion):
    pipeline = [(a, funcion if a == agente else f, c) for a, f, c in orquestador.PIPELINE]
    monkeypatch.setattr(orquestador, "PIPELINE", pipeline)


def test_consulta_completa(client):
    resp = client.post("/consultas", json={"pregunta": "¿Plazo para reportar eventos de pérdida?"})
    assert resp.status_code == 202
    creada = resp.json()
    assert set(creada) == {"ejecucion_id", "sesion_id", "estado"}
    assert creada["estado"] == "PENDIENTE"
    uuid.UUID(creada["sesion_id"])  # se generó una sesión nueva

    # TestClient ejecuta la tarea en segundo plano antes de devolver la respuesta
    detalle = client.get(f"/consultas/{creada['ejecucion_id']}").json()
    assert detalle["estado"] == "COMPLETADO"
    assert detalle["paso_actual"] is None
    pasos = detalle["pasos"]
    assert [p["agente"] for p in pasos] == AGENTES
    assert [p["orden"] for p in pasos] == [1, 2, 3, 4]
    assert all(p["estado"] == "COMPLETADO" and p["error"] is None and p["duracion_ms"] >= 0 for p in pasos)

    # Contrato exacto de cada agente
    buscador, vigencia, conflictos, redactor = (p["salida"] for p in pasos)
    assert set(buscador) == {"articulos"}
    assert set(buscador["articulos"][0]) == {"documento_id", "articulo", "fragmento", "score"}
    assert set(vigencia) == {"vigentes", "descartados"}
    assert set(vigencia["descartados"][0]) == {"documento_id", "motivo", "reemplazado_por"}
    assert set(conflictos["conflictos"][0]) == {"documento_a", "documento_b", "tema", "descripcion"}
    assert set(redactor) == {"respuesta", "citas", "alertas"}
    assert set(redactor["citas"][0]) == {"documento_id", "articulo"}
    assert {a["tipo"] for a in redactor["alertas"]} == {"CONFLICTO", "VIGENCIA"}
    assert detalle["respuesta"] == redactor["respuesta"]


def test_en_proceso_antes_de_cada_agente(client, session_factory, monkeypatch):
    vistos = []

    def espiar(funcion):
        def _agente(pregunta, contexto_previo):
            with session_factory() as db:
                ejecucion = db.scalars(select(Ejecucion)).one()
                vistos.append((ejecucion.paso_actual, ejecucion.estado, len(ejecucion.pasos), sorted(contexto_previo)))
            return funcion(pregunta, contexto_previo)

        return _agente

    monkeypatch.setattr(orquestador, "PIPELINE", [(a, espiar(f), c) for a, f, c in orquestador.PIPELINE])
    client.post("/consultas", json={"pregunta": "¿Qué norma aplica?"})

    assert vistos == [
        ("BUSCADOR", "EN_PROCESO", 0, []),
        ("VIGENCIA", "EN_PROCESO", 1, ["BUSCADOR"]),
        ("CONFLICTOS", "EN_PROCESO", 2, ["BUSCADOR", "VIGENCIA"]),
        ("REDACTOR", "EN_PROCESO", 3, ["BUSCADOR", "CONFLICTOS", "VIGENCIA"]),
    ]


def test_agente_que_falla_detiene_el_pipeline(client, monkeypatch):
    def conflictos_roto(pregunta, contexto_previo):
        raise RuntimeError("LLM no disponible")

    _replace_agent(monkeypatch, Agente.CONFLICTOS, conflictos_roto)
    resp = client.post("/consultas", json={"pregunta": "¿Hay contradicciones?"})
    assert resp.status_code == 202

    detalle = client.get(f"/consultas/{resp.json()['ejecucion_id']}").json()
    assert detalle["estado"] == "ERROR"
    assert detalle["paso_actual"] == "CONFLICTOS"
    assert detalle["respuesta"] is None
    assert [p["agente"] for p in detalle["pasos"]] == ["BUSCADOR", "VIGENCIA", "CONFLICTOS"]
    fallido = detalle["pasos"][-1]
    assert fallido["estado"] == "ERROR"
    assert fallido["salida"] is None
    assert "RuntimeError: LLM no disponible" == fallido["error"]

    # La API sigue funcionando
    assert client.get("/health").status_code == 200
    assert client.post("/consultas", json={"pregunta": "otra"}).status_code == 202


def test_salida_fuera_de_contrato_es_error(client, monkeypatch):
    _replace_agent(monkeypatch, Agente.BUSCADOR, lambda pregunta, contexto_previo: {"resultados": []})
    ejecucion_id = client.post("/consultas", json={"pregunta": "x"}).json()["ejecucion_id"]

    detalle = client.get(f"/consultas/{ejecucion_id}").json()
    assert detalle["estado"] == "ERROR"
    assert len(detalle["pasos"]) == 1
    assert "articulos" in detalle["pasos"][0]["error"]


def test_historial_de_sesion(client):
    sesion_id = str(uuid.uuid4())
    ids = [
        client.post("/consultas", json={"sesion_id": sesion_id, "pregunta": f"Pregunta {i}"}).json()
        for i in range(3)
    ]
    assert all(c["sesion_id"] == sesion_id for c in ids)
    client.post("/consultas", json={"pregunta": "De otra sesión"})

    historial = client.get(f"/sesiones/{sesion_id}/consultas").json()
    assert [h["id"] for h in historial] == [c["ejecucion_id"] for c in reversed(ids)]
    assert [h["pregunta"] for h in historial] == ["Pregunta 2", "Pregunta 1", "Pregunta 0"]
    assert "pasos" not in historial[0]
    assert client.get(f"/sesiones/{uuid.uuid4()}/consultas").json() == []


def test_consulta_validaciones(client):
    assert client.post("/consultas", json={"pregunta": "   "}).status_code == 422
    assert client.post("/consultas", json={}).status_code == 422
    assert client.post("/consultas", json={"pregunta": "x", "sesion_id": "no-es-uuid"}).status_code == 422
    assert client.get(f"/consultas/{uuid.uuid4()}").status_code == 404
    assert client.get("/consultas/no-es-uuid").status_code == 422
