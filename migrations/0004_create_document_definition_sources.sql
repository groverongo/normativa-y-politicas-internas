-- Per-document view of which document currently defines a given term.
-- Mirrors schema.LineageMetadata.definition_sources (dict[term, source_doc_id]).
-- Written by the Graph-Update agent's case-9 (indirect dependency update)
-- cross-document impact cascade: storage.set_definition_source(doc_id, term,
-- source_doc_id).

-- +migrate Up

CREATE TABLE document_definition_sources (
    doc_id         TEXT NOT NULL REFERENCES documents (doc_id) ON DELETE CASCADE,
    term           TEXT NOT NULL,
    source_doc_id  TEXT NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (doc_id, term)
);

CREATE INDEX idx_document_definition_sources_term ON document_definition_sources (term);

-- +migrate Down

DROP TABLE IF EXISTS document_definition_sources;
