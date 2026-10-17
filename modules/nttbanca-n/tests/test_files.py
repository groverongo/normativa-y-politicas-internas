import pytest
from sqlalchemy.orm import Session


def _upload(client, content=b"hola mundo", filename="contrato.txt", content_type="text/plain", **data):
    return client.post("/files", data=data, files={"file": (filename, content, content_type)})


def test_files_crud(client, bucket_keys):
    # Create: sube a S3 y guarda el registro que apunta al objeto
    resp = _upload(client)
    assert resp.status_code == 201
    record = resp.json()
    file_id = record["id"]
    assert record["original_filename"] == "contrato.txt"
    assert record["size_bytes"] == len(b"hola mundo")
    assert record["content_type"] == "text/plain"
    assert record["bucket"] == "test-bucket"
    assert record["s3_key"].startswith("uploads/") and record["s3_key"].endswith(".txt")
    assert record["item_id"] is None
    assert bucket_keys() == [record["s3_key"]]

    # Read
    assert client.get(f"/files/{file_id}").json() == record
    assert [f["id"] for f in client.get("/files").json()] == [file_id]

    # Download: sale de S3 con el nombre original
    resp = client.get(f"/files/{file_id}/download")
    assert resp.status_code == 200
    assert resp.content == b"hola mundo"
    assert "contrato.txt" in resp.headers["content-disposition"]

    # Presigned URL
    resp = client.get(f"/files/{file_id}/presigned-url", params={"expires_in": 120})
    assert resp.status_code == 200
    assert record["s3_key"] in resp.json()["url"]
    assert resp.json()["expires_in"] == 120

    # Update de contenido: nueva key, el objeto viejo se borra
    resp = client.put(f"/files/{file_id}", files={"file": ("contrato_v2.txt", b"version 2", "text/plain")})
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["id"] == file_id
    assert updated["original_filename"] == "contrato_v2.txt"
    assert updated["size_bytes"] == len(b"version 2")
    assert updated["s3_key"] != record["s3_key"]
    assert bucket_keys() == [updated["s3_key"]]
    assert client.get(f"/files/{file_id}/download").content == b"version 2"

    # Update de metadatos
    resp = client.patch(f"/files/{file_id}", json={"original_filename": "renombrado.txt"})
    assert resp.status_code == 200
    assert resp.json()["original_filename"] == "renombrado.txt"
    assert resp.json()["s3_key"] == updated["s3_key"]

    # Delete: borra registro y objeto
    assert client.delete(f"/files/{file_id}").status_code == 204
    assert client.get(f"/files/{file_id}").status_code == 404
    assert bucket_keys() == []


def test_file_linked_to_item(client):
    item_id = client.post("/items", json={"name": "Cliente 1"}).json()["id"]
    other_id = client.post("/items", json={"name": "Cliente 2"}).json()["id"]

    f1 = _upload(client, item_id=str(item_id)).json()
    _upload(client, filename="otro.pdf", content_type="application/pdf").json()
    assert f1["item_id"] == item_id

    assert [f["id"] for f in client.get(f"/items/{item_id}/files").json()] == [f1["id"]]
    assert [f["id"] for f in client.get("/files", params={"item_id": item_id}).json()] == [f1["id"]]

    # Mover a otro item y luego desvincular
    assert client.patch(f"/files/{f1['id']}", json={"item_id": other_id}).json()["item_id"] == other_id
    assert client.patch(f"/files/{f1['id']}", json={"item_id": None}).json()["item_id"] is None


def test_upload_to_missing_item(client, bucket_keys):
    assert _upload(client, item_id="999").status_code == 404
    assert bucket_keys() == []


def test_patch_validation(client):
    file_id = _upload(client).json()["id"]
    assert client.patch(f"/files/{file_id}", json={"original_filename": None}).status_code == 422
    assert client.patch(f"/files/{file_id}", json={"item_id": 999}).status_code == 404


def test_filename_with_path_is_cleaned(client):
    resp = _upload(client, filename="C:\\Users\\yo\\foto.PNG", content_type="image/png")
    assert resp.json()["original_filename"] == "foto.PNG"
    assert resp.json()["s3_key"].endswith(".png")


def test_db_failure_on_upload_cleans_s3(client, bucket_keys, monkeypatch):
    def failing_commit(self):
        raise RuntimeError("BD caída")

    monkeypatch.setattr(Session, "commit", failing_commit)
    with pytest.raises(RuntimeError):
        _upload(client)
    assert bucket_keys() == []


def test_object_missing_in_s3(client, s3_service):
    record = _upload(client).json()
    s3_service.delete(record["s3_key"])
    resp = client.get(f"/files/{record['id']}/download")
    assert resp.status_code == 404
    assert "no está en S3" in resp.json()["detail"]


def test_file_not_found(client):
    assert client.get("/files/999").status_code == 404
    assert client.get("/files/999/download").status_code == 404
    assert client.get("/files/999/presigned-url").status_code == 404
    assert client.put("/files/999", files={"file": ("a.txt", b"a")}).status_code == 404
    assert client.patch("/files/999", json={"original_filename": "x"}).status_code == 404
    assert client.delete("/files/999").status_code == 404
