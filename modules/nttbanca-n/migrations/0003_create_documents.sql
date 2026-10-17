-- Documents: the metadata "node" for each ingested regulatory/policy document,
-- ported from modules/ingesta/migrations/0001_create_documents.sql (Up section
-- only -- this runner has no Up/Down marker support, see app/db/migrate.py).
-- Mirrors app/schemas/lifecycle.py's DocumentMetadata.identity_metadata +
-- lifecycle_metadata. This is additive: separate from `items`/`files`.

CREATE TYPE doc_status AS ENUM (
    'ACTIVE',
    'SUPERSEDED',
    'PARTIALLY_SUPERSEDED',
    'REVOKED',
    'EXPIRED'
);

CREATE TABLE documents (
    doc_id                TEXT PRIMARY KEY,
    doc_type              TEXT NOT NULL DEFAULT 'unknown',
    title                 TEXT NOT NULL DEFAULT '',
    issuer                TEXT NOT NULL DEFAULT '',
    raw_text              TEXT NOT NULL DEFAULT '',
    status                doc_status NOT NULL DEFAULT 'ACTIVE',
    valid_from            DATE,
    valid_until           DATE,
    version               TEXT,
    topic_tags            JSONB NOT NULL DEFAULT '[]'::jsonb,
    defined_terms         JSONB NOT NULL DEFAULT '[]'::jsonb,
    referenced_terms      JSONB NOT NULL DEFAULT '[]'::jsonb,
    review_flags          JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_dependencies  JSONB NOT NULL DEFAULT '[]'::jsonb,
    notes                 JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_documents_status ON documents (status);
CREATE INDEX idx_documents_doc_type ON documents (doc_type);
CREATE INDEX idx_documents_valid_window ON documents (valid_from, valid_until);
CREATE INDEX idx_documents_defined_terms ON documents USING GIN (defined_terms);
CREATE INDEX idx_documents_referenced_terms ON documents USING GIN (referenced_terms);

CREATE OR REPLACE FUNCTION set_documents_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_documents_set_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION set_documents_updated_at();
