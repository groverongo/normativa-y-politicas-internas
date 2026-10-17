-- Documents: the metadata "node" for each ingested regulatory/policy document.
-- Shared by both modules/ingesta's S3DbStorage and modules/nttbanca-n's
-- DocumentGraphStorage -- raw text lives in S3 (source_uri is the S3 object
-- key), the metadata graph lives here. Mirrors identity_metadata +
-- lifecycle_metadata in both modules' schema/lifecycle pydantic models.
-- Lineage edges live in a separate table -- see 0005_create_document_lineage.sql.
--
-- Reconciles an earlier divergence where nttbanca-n's ported copy of this
-- table used an inline `raw_text` column instead of `source_uri`: source_uri
-- (S3-backed) is the canonical design, matching ingesta's original storage.py
-- and nttbanca-n's existing S3 infrastructure (app/services/s3.py).

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
    source_uri            TEXT,                        -- S3 object key holding the raw document text
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
