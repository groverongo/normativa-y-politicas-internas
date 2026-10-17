-- Chunks: text units of a document, ported from
-- modules/ingesta/migrations/0002_create_chunks.sql (Up section only).
-- Referenced by: app/db/migrate.py's migration_files()/run_migrations().

CREATE TABLE chunks (
    chunk_id     TEXT PRIMARY KEY,                 -- "<doc_id>#<chunk_index>"
    doc_id       TEXT NOT NULL REFERENCES documents (doc_id) ON DELETE CASCADE,
    chunk_index  INT NOT NULL,
    text         TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (doc_id, chunk_index)
);

CREATE INDEX idx_chunks_doc_id ON chunks (doc_id);
