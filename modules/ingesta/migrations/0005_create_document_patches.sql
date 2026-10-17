-- Patch records applied by a "fe de erratas" (minor patch/erratum) document.
-- Mirrors schema.PatchRecord, attached to the document being patched.
-- patched_by is also recorded as a document_lineage row with
-- relation='patched_by' (see 0003_create_document_lineage.sql) -- this table
-- holds the structured clause/old_text/new_text content the lineage edge
-- alone can't carry.

-- +migrate Up

CREATE TABLE document_patches (
    id               BIGSERIAL PRIMARY KEY,
    doc_id           TEXT NOT NULL REFERENCES documents (doc_id) ON DELETE CASCADE,  -- the patched (target) document
    clause           TEXT NOT NULL,
    old_text         TEXT NOT NULL DEFAULT '',
    new_text         TEXT NOT NULL DEFAULT '',
    patched_by       TEXT,            -- doc_id of the erratum document
    effective_date   DATE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_document_patches_doc_id ON document_patches (doc_id);

-- +migrate Down

DROP TABLE IF EXISTS document_patches;
