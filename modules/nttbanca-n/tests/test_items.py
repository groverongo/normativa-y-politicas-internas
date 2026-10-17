def test_items_crud(client):
    # Create
    resp = client.post("/items", json={"name": "Cuenta ahorro", "description": "Producto base"})
    assert resp.status_code == 201
    item = resp.json()
    assert item["name"] == "Cuenta ahorro"
    assert item["is_active"] is True
    item_id = item["id"]

    # Read
    resp = client.get(f"/items/{item_id}")
    assert resp.status_code == 200
    assert resp.json()["description"] == "Producto base"

    # List
    client.post("/items", json={"name": "Tarjeta"})
    resp = client.get("/items")
    assert resp.status_code == 200
    assert [i["name"] for i in resp.json()] == ["Cuenta ahorro", "Tarjeta"]

    # Update parcial
    resp = client.patch(f"/items/{item_id}", json={"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
    assert resp.json()["name"] == "Cuenta ahorro"

    # Delete
    resp = client.delete(f"/items/{item_id}")
    assert resp.status_code == 204
    assert client.get(f"/items/{item_id}").status_code == 404


def test_item_not_found(client):
    assert client.get("/items/999").status_code == 404
    assert client.patch("/items/999", json={"name": "x"}).status_code == 404
    assert client.delete("/items/999").status_code == 404


def test_item_validation(client):
    assert client.post("/items", json={"name": ""}).status_code == 422
    assert client.post("/items", json={}).status_code == 422
    item_id = client.post("/items", json={"name": "x"}).json()["id"]
    assert client.patch(f"/items/{item_id}", json={"name": None}).status_code == 422
    assert client.patch(f"/items/{item_id}", json={"is_active": None}).status_code == 422


def test_item_sin_campos_normativos_mantiene_comportamiento(client):
    item = client.post("/items", json={"name": "Solo nombre"}).json()
    assert item["tipo"] is None
    assert item["codigo_norma"] is None
    assert item["fecha_vigencia"] is None
    assert item["estado"] == "VIGENTE"
    assert item["reemplaza_a"] is None


def test_documento_normativo(client):
    anterior = client.post(
        "/items",
        json={
            "name": "Reglamento de riesgo operacional (2009)",
            "tipo": "SBS",
            "codigo_norma": "SBS-EJ-2009",
            "fecha_vigencia": "2009-07-01",
            "estado": "DEROGADA",
        },
    ).json()
    assert anterior["tipo"] == "SBS"
    assert anterior["fecha_vigencia"] == "2009-07-01"
    assert anterior["estado"] == "DEROGADA"

    resp = client.post(
        "/items",
        json={
            "name": "Reglamento de riesgo operacional (2020)",
            "tipo": "SBS",
            "codigo_norma": "SBS-EJ-2020",
            "fecha_vigencia": "2020-03-15",
            "reemplaza_a": anterior["id"],
        },
    )
    assert resp.status_code == 201
    nuevo = resp.json()
    assert nuevo["reemplaza_a"] == anterior["id"]
    assert nuevo["estado"] == "VIGENTE"

    # Update parcial de los campos nuevos
    resp = client.patch(f"/items/{nuevo['id']}", json={"tipo": "POLITICA_INTERNA", "reemplaza_a": None})
    assert resp.status_code == 200
    assert resp.json()["tipo"] == "POLITICA_INTERNA"
    assert resp.json()["reemplaza_a"] is None
    assert resp.json()["codigo_norma"] == "SBS-EJ-2020"


def test_documento_validaciones(client):
    doc_id = client.post("/items", json={"name": "Doc"}).json()["id"]
    assert client.post("/items", json={"name": "x", "tipo": "OTRO"}).status_code == 422
    assert client.post("/items", json={"name": "x", "estado": "ANULADA"}).status_code == 422
    assert client.post("/items", json={"name": "x", "fecha_vigencia": "no-es-fecha"}).status_code == 422
    assert client.post("/items", json={"name": "x", "reemplaza_a": 999}).status_code == 404
    assert client.patch(f"/items/{doc_id}", json={"estado": None}).status_code == 422
    assert client.patch(f"/items/{doc_id}", json={"reemplaza_a": 999}).status_code == 404
    assert client.patch(f"/items/{doc_id}", json={"reemplaza_a": doc_id}).status_code == 422


def test_delete_item_removes_its_files(client, bucket_keys):
    item_id = client.post("/items", json={"name": "Cliente"}).json()["id"]
    for name in ("dni.pdf", "contrato.pdf"):
        client.post("/files", data={"item_id": str(item_id)}, files={"file": (name, b"pdf", "application/pdf")})
    unlinked = client.post("/files", files={"file": ("suelto.txt", b"x", "text/plain")}).json()
    assert len(bucket_keys()) == 3

    assert client.delete(f"/items/{item_id}").status_code == 204
    assert client.get(f"/items/{item_id}/files").status_code == 404
    assert [f["id"] for f in client.get("/files").json()] == [unlinked["id"]]
    assert bucket_keys() == [unlinked["s3_key"]]
