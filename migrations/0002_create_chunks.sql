-- Chunks: the embedded text units for RAG retrieval. Mirrors schema.Chunk.
-- Vector embeddings are intentionally NOT modeled here -- the embedding
-- store/index is a separate concern from this metadata graph (add a
-- pgvector `embedding` column, or a separate vector-store table/reference,
-- when that integration happens).

-- +migrate Up

CREATE TABLE chunks (
    chunk_id     TEXT PRIMARY KEY,                 -- "<doc_id>#<chunk_index>"
    doc_id       TEXT NOT NULL REFERENCES documents (doc_id) ON DELETE CASCADE,
    chunk_index  INT NOT NULL,
    text         TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (doc_id, chunk_index)
);

CREATE INDEX idx_chunks_doc_id ON chunks (doc_id);

-- +migrate Down

DROP TABLE IF EXISTS chunks;
