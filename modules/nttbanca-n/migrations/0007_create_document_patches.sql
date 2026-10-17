-- Patch records applied by a "fe de erratas" document, ported from
-- modules/ingesta/migrations/0005_create_document_patches.sql (Up section
-- only). Referenced by: app/db/migrate.py's migration_files()/run_migrations().
-- Facts: called by app/db/migrate.py; confirmed absent via parallel ls; pure
-- DDL, no data records; part of the approved "richer ingesta workflow" plan.

CREATE TABLE document_patches (
    id               BIGSERIAL PRIMARY KEY,
    doc_id           TEXT NOT NULL REFERENCES documents (doc_id) ON DELETE CASCADE,
    clause           TEXT NOT NULL,
    old_text         TEXT NOT NULL DEFAULT '',
    new_text         TEXT NOT NULL DEFAULT '',
    patched_by       TEXT,
    effective_date   DATE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_document_patches_doc_id ON document_patches (doc_id);
