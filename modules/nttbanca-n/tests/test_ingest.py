"""End-to-end tests for the ported ingestion pipeline (/ingest, /documents),
covering a representative subset of modules/ingesta/smoke_test.py's 9 cases,
all against MockProvider (LLM_PROVIDER=mock set by tests/conftest.py's env,
no credentials needed). Uses the existing SQLite-in-memory `client` fixture.
"""


def test_new_statement(client):
    resp = client.post(
        "/ingest",
        json={
            "source_name": "01_nuevo.txt",
            "text": (
                "ID: SBS-RES-1000-2020\n"
                "Se establece el nuevo reglamento de gestion de riesgos "
                "operacionales, vigente desde 2020-03-15."
            ),
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["final_case"] == "NEW_STATEMENT"
    assert body["doc_id"] == "SBS-RES-1000-2020"
    assert body["errors"] == []


def test_full_replacement_updates_lineage(client):
    r1 = client.post(
        "/ingest",
        json={
            "source_name": "01_nuevo.txt",
            "text": (
                "ID: SBS-RES-1000-2020\n"
                "Se establece el nuevo reglamento de gestion de riesgos "
                "operacionales, vigente desde 2020-03-15."
            ),
        },
    )
    assert r1.status_code == 201, r1.text

    r2 = client.post(
        "/ingest",
        json={
            "source_name": "02_sustituye.txt",
            "text": (
                "ID: SBS-RES-2000-2021\n"
                "Esta norma sustituye a la SBS-RES-1000-2020 en su "
                "totalidad, vigente desde 2021-01-10."
            ),
        },
    )
    assert r2.status_code == 201, r2.text
    body2 = r2.json()
    assert body2["final_case"] == "FULL_REPLACEMENT"
    assert body2["doc_id"] == "SBS-RES-2000-2021"

    old_doc = client.get("/documents/SBS-RES-1000-2020")
    assert old_doc.status_code == 200, old_doc.text
    old_body = old_doc.json()
    assert old_body["lifecycle_metadata"]["status"] == "SUPERSEDED"
    assert "SBS-RES-2000-2021" in old_body["lineage_metadata"]["superseded_by"]

    catalog = client.get("/documents")
    assert catalog.status_code == 200
    doc_ids = {entry["doc_id"] for entry in catalog.json()}
    assert {"SBS-RES-1000-2020", "SBS-RES-2000-2021"} <= doc_ids


def test_patch_erratum_adds_patch_record(client):
    r1 = client.post(
        "/ingest",
        json={
            "source_name": "01_nuevo.txt",
            "text": (
                "ID: SBS-RES-1000-2020\n"
                "Se establece el nuevo reglamento de gestion de riesgos "
                "operacionales, vigente desde 2020-03-15."
            ),
        },
    )
    assert r1.status_code == 201, r1.text

    r3 = client.post(
        "/ingest",
        json={
            "source_name": "03_errata.txt",
            "text": (
                "ID: SBS-RES-3000-2022\n"
                "Fe de erratas que corrige el articulo 5 de la "
                "SBS-RES-1000-2020, vigente desde 2022-05-01."
            ),
        },
    )
    assert r3.status_code == 201, r3.text
    body3 = r3.json()
    assert body3["final_case"] == "PATCH_ERRATUM"
    assert body3["operations_applied"] > 0

    patched_doc = client.get("/documents/SBS-RES-1000-2020")
    assert patched_doc.status_code == 200
    patch_log = patched_doc.json()["lifecycle_metadata"]["patch_log"]
    assert len(patch_log) == 1
    assert patch_log[0]["patched_by"] == "SBS-RES-3000-2022"


def test_indirect_dependency_update_cascades_to_referencing_doc(client):
    r1 = client.post(
        "/ingest",
        json={
            "source_name": "04_politica.txt",
            "text": (
                "ID: BCP-POL-0050-2022\n"
                "Politica interna sobre atencion a clientes, incluyendo "
                "disposiciones para cliente vulnerable, vigente desde "
                "2022-01-01."
            ),
        },
    )
    assert r1.status_code == 201, r1.text
    assert r1.json()["final_case"] == "NEW_STATEMENT"

    r2 = client.post(
        "/ingest",
        json={
            "source_name": "05_redefinicion.txt",
            "text": (
                "ID: SBS-RES-4000-2023\n"
                'Para efectos de esta norma, se entiende por "cliente '
                "vulnerable\" a toda persona natural en situacion de "
                "desventaja, vigente desde 2023-06-01."
            ),
        },
    )
    assert r2.status_code == 201, r2.text
    body2 = r2.json()
    assert body2["final_case"] == "INDIRECT_DEPENDENCY_UPDATE"
    assert "BCP-POL-0050-2022" in body2["impacted_docs"]

    impacted = client.get("/documents/BCP-POL-0050-2022")
    assert impacted.status_code == 200
    impacted_body = impacted.json()
    assert impacted_body["lineage_metadata"]["definition_sources"]["cliente vulnerable"] == "SBS-RES-4000-2023"
    assert any(
        flag.startswith("TERM_REDEFINED:cliente vulnerable:")
        for flag in impacted_body["lifecycle_metadata"]["review_flags"]
    )
