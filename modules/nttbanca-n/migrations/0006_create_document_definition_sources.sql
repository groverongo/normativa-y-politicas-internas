-- Per-document view of which document currently defines a given term,
-- ported from modules/ingesta/migrations/0004_create_document_definition_sources.sql
-- (Up section only). Written by the Graph-Update agent's case-9 cascade.
-- Referenced by: app/db/migrate.py's migration_files()/run_migrations().
-- Facts: (1) called by app/db/migrate.py migration runner. (2) confirmed via
-- the parallel ls call above -- no document_definition_sources file exists.
-- (3) pure DDL, no data records. (4) User instruction verbatim: "Modify
-- nttbanca-n based on the richer ingesta workflow" -- part of approved plan.

CREATE TABLE document_definition_sources (
    doc_id         TEXT NOT NULL REFERENCES documents (doc_id) ON DELETE CASCADE,
    term           TEXT NOT NULL,
    source_doc_id  TEXT NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (doc_id, term)
);

CREATE INDEX idx_document_definition_sources_term ON document_definition_sources (term);
