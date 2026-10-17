-- Document lineage graph: one row per directed edge, ported from
-- modules/ingesta/migrations/0003_create_document_lineage.sql (Up section
-- only). target_doc_id is intentionally NOT a foreign key to documents: a
-- "missing dependency" case records a reference to a document that may not
-- exist in this corpus yet (see validation_to_classifier feedback loop).
-- Referenced by: app/db/migrate.py's migration_files()/run_migrations().

CREATE TYPE lineage_relation AS ENUM (
    'supersedes', 'superseded_by',
    'amends', 'patched_by',
    'consolidates',
    'split_from', 'split_into',
    'contradicts',
    'revokes', 'revoked_by',
    'overrides', 'overridden_by',
    'impacts'
);

CREATE TABLE document_lineage (
    id             BIGSERIAL PRIMARY KEY,
    doc_id         TEXT NOT NULL REFERENCES documents (doc_id) ON DELETE CASCADE,
    relation       lineage_relation NOT NULL,
    target_doc_id  TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (doc_id, relation, target_doc_id)
);

CREATE INDEX idx_document_lineage_doc_id ON document_lineage (doc_id, relation);
CREATE INDEX idx_document_lineage_target ON document_lineage (target_doc_id, relation);
