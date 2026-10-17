-- Esquema inicial: lo mismo que creaba Base.metadata.create_all antes de existir las migraciones.
-- Es idempotente: en una base que ya tenía estas tablas no cambia nada.

CREATE TABLE IF NOT EXISTS items (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    description TEXT,
    is_active   BOOLEAN NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_items_name ON items (name);

CREATE TABLE IF NOT EXISTS files (
    id                SERIAL PRIMARY KEY,
    item_id           INTEGER REFERENCES items (id) ON DELETE CASCADE,
    bucket            VARCHAR(63) NOT NULL,
    s3_key            VARCHAR(1024) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    content_type      VARCHAR(255),
    size_bytes        BIGINT NOT NULL,
    etag              VARCHAR(255),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_files_bucket_s3_key UNIQUE (bucket, s3_key)
);
CREATE INDEX IF NOT EXISTS ix_files_item_id ON files (item_id);
