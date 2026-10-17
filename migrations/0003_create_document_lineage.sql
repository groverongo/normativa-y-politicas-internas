-- Document lineage graph: one row per directed edge. Replaces all 13 list
-- fields on schema.LineageMetadata (supersedes, superseded_by, amends,
-- patched_by, consolidates, split_from, split_into, contradicts, revokes,
-- revoked_by, overrides, overridden_by, impacts) with a single normalized
-- edge table, keyed by relation type -- this is the actual "lineage graph"
-- the ingestion agents build.
--
-- target_doc_id is intentionally NOT a foreign key to documents: the spec's
-- "missing dependency" case requires recording a reference to a document
-- that may not exist in this corpus yet (see the validation_to_classifier
-- feedback loop / schema.ValidationReport.missing_refs).

-- +migrate Up

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
    UNIQUE (doc_id, relation, target_doc_id)        -- mirrors storage.append_lineage's de-dup
);

CREATE INDEX idx_document_lineage_doc_id ON document_lineage (doc_id, relation);
CREATE INDEX idx_document_lineage_target ON document_lineage (target_doc_id, relation);

-- +migrate Down

DROP TABLE IF EXISTS document_lineage;
DROP TYPE IF EXISTS lineage_relation;
