-- Adds what modules/nttdatabanca needs to move off registry.json/corpus/Qdrant
-- and onto the shared documents/chunks schema + Postgres-native vector search,
-- mirroring modules/ingesta's S3DbStorage connection/interaction style.
-- Referenced by: modules/nttdatabanca's db.go (connection), registry.go
-- (reads/writes documents + document_lineage instead of registry.json),
-- pgvectorstore.go (chunk_vectors + chunks.tsv instead of Qdrant).
--
-- All changes are additive (ALTER ... ADD COLUMN IF NOT EXISTS, CREATE TABLE
-- IF NOT EXISTS) so modules/ingesta and modules/nttbanca-n are unaffected.

CREATE EXTENSION IF NOT EXISTS vector;

-- nttdatabanca's registry.json carried two fields the shared `documents`
-- table has no equivalent for: `numero` (a short regulatory code like
-- "877-2020", used to recognize references in free text -- see
-- Registry.DocIDsDesdeTexto) and `url` (a public source link, distinct from
-- source_uri which is the internal S3 object key for the raw text).
ALTER TABLE documents ADD COLUMN IF NOT EXISTS external_code TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS external_url TEXT;
CREATE INDEX IF NOT EXISTS idx_documents_external_code ON documents (external_code);

-- registry.json's derogado_por / modificado_por map onto document_lineage
-- relations already in the shared enum (revoked_by / superseded_by / patched_by)
-- instead of new columns -- see nttdatabanca's registry.go for the mapping.

-- nttdatabanca's chunks are split by regulatory article (Ruta, e.g. "Artículo
-- 5") and track the source page for citation -- the shared `chunks` table
-- only had chunk_id/doc_id/chunk_index/text.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS section_label TEXT;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS page_number INT;

-- Lexical search (replaces nttdatabanca's hand-rolled BM25-over-Qdrant sparse
-- vectors): a generated tsvector column + GIN index, queried with
-- ts_rank_cd/websearch_to_tsquery and fused in Go with the dense vector
-- search below via reciprocal rank fusion (mirrors Qdrant's server-side RRF).
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('spanish', text)) STORED;
CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING GIN (tsv);

-- Dense embeddings, one row per chunk. `embedding` is left dimension-less
-- (pgvector allows this) rather than `vector(N)` because nttdatabanca can be
-- reconfigured between embedding providers/models with different dimensions
-- (EMB_PROVIDER=voyage|jina) -- same reason Qdrant kept one collection per
-- provider. `dim` records the dimension actually stored so a mismatched
-- provider switch fails fast instead of comparing incompatible vectors;
-- switching providers requires re-ingesting (TRUNCATE + re-upsert), same as
-- Qdrant's `ingest -reset`. No ANN index (ivfflat/hnsw need a fixed
-- dimension): ORDER BY embedding <=> $1 does an exact brute-force scan,
-- acceptable at this corpus's scale.
CREATE TABLE IF NOT EXISTS chunk_vectors (
    chunk_id   TEXT PRIMARY KEY REFERENCES chunks (chunk_id) ON DELETE CASCADE,
    doc_id     TEXT NOT NULL REFERENCES documents (doc_id) ON DELETE CASCADE,
    embedding  vector NOT NULL,
    dim        INT NOT NULL,
    model      TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chunk_vectors_doc_id ON chunk_vectors (doc_id);
