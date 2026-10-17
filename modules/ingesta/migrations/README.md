# Database migrations

Schema for the metadata graph that `storage.S3DbStorage` reads and writes
(raw document text lives in S3, not here -- see `storage.py`'s `_s3_key`/
`_put_raw_text`). Field names and types mirror `schema.py`'s pydantic models
exactly; see the table below.

**Engine assumption:** PostgreSQL 13+ (JSONB, native `ENUM` types, `GENERATED`-free
triggers). No engine was specified upstream ("db probably" in the original
problem statement) -- Postgres was chosen for its JSONB support, which fits
the nested lifecycle/lineage metadata well. If the real deployment target is
a different engine, treat these files as the reference schema to port, not
as drop-in SQL.

## Files

Applied in order, `0001` through `0005`. Each file contains both halves,
marked with `-- +migrate Up` / `-- +migrate Down` (the convention used by
`sql-migrate` and `goose`; trivially portable to two-file-per-migration tools
like `golang-migrate` or `node-pg-migrate` by splitting on those markers).

| File | Table(s) | Mirrors (`schema.py`) |
|---|---|---|
| `0001_create_documents.sql` | `documents` | `DocumentMetadata.identity_metadata` + `.lifecycle_metadata` (scalar/list fields) |
| `0002_create_chunks.sql` | `chunks` | `Chunk` |
| `0003_create_document_lineage.sql` | `document_lineage` | `LineageMetadata`'s 13 list fields, normalized into one edge table |
| `0004_create_document_definition_sources.sql` | `document_definition_sources` | `LineageMetadata.definition_sources` |
| `0005_create_document_patches.sql` | `document_patches` | `PatchRecord` (via `LifecycleMetadata.patch_log`) |

## Applying them

**Manually**, in order:

```bash
for f in migrations/0*.sql; do
  awk '/-- \+migrate Up/{flag=1; next} /-- \+migrate Down/{flag=0} flag' "$f" | psql "$DATABASE_URL"
done
```

**Automatically**, for local dev/testing only: set `DB_AUTO_CREATE_TABLES=true`
in `.env`. `S3DbStorage.__init__` checks whether the `documents` table exists
and, if not, reads every `migrations/*.sql` file directly off disk and
executes its "Up" half (see `storage._ensure_schema`) -- so this always stays
in sync with the files here, nothing is duplicated. Leave it `false` (the
default) for any environment with its own migration/deployment process.

**Rolling back** one migration: run the `-- +migrate Down` half of its file,
in reverse order (`0005` before `0001`, since later tables have FKs onto
`documents`).

## Design notes

- **`document_lineage` is one table, not 13 columns.** `LineageMetadata` has
  13 list fields (`supersedes`, `superseded_by`, `amends`, `patched_by`,
  `consolidates`, `split_from`, `split_into`, `contradicts`, `revokes`,
  `revoked_by`, `overrides`, `overridden_by`, `impacts`). They're all the
  same shape -- "this document relates to that document, by relation X" --
  so they're normalized into one `(doc_id, relation, target_doc_id)` edge
  table instead of 13 nullable columns. `UNIQUE (doc_id, relation,
  target_doc_id)` mirrors the de-dup behavior in `InMemoryStorage.append_lineage`.
- **`target_doc_id` has no foreign key.** The spec's "missing dependency"
  case (see README.md section on Loop 1) requires recording a reference to a
  document that may not exist yet. A FK would make that impossible to store.
- **Simple list fields stay as JSONB columns on `documents`**
  (`topic_tags`, `defined_terms`, `referenced_terms`, `review_flags`,
  `missing_dependencies`, `notes`) rather than being normalized into their
  own tables -- they don't participate in joins the way lineage edges and
  definition sources do, so the extra tables wouldn't earn their keep.
  GIN indexes are added on `defined_terms`/`referenced_terms` since those are
  the ones queried (case-9 cross-document impact search).
- **`document_patches` is separate from the lineage edge it also implies.**
  A patch's `patched_by` is recorded twice on purpose: once as a full
  `document_patches` row (clause/old_text/new_text, for RAG/audit use), and
  once as a `document_lineage` row with `relation='patched_by'` (for cheap
  graph traversal without touching the heavier table). Both are written by
  `S3DbStorage.append_patch_metadata` in one call.
- **No embeddings/vector columns.** Chunk embeddings for RAG retrieval are a
  separate concern from this metadata graph. Add a `pgvector` column (or a
  separate vector-store table/reference) to `chunks` when that integration
  happens -- it wasn't needed to satisfy the ingestion spec this schema
  supports.
- **`updated_at` on `documents` is trigger-maintained**, not
  application-maintained, so it stays correct even for direct SQL writes
  outside `S3DbStorage`.

## Verified

Each file was applied against a real disposable PostgreSQL 16 container
(`docker run postgres:16-alpine`), in order, with no errors; a representative
row was inserted per table (mirroring an actual pipeline run's output) and
the key queries -- the "active rule" filter, the lineage-edge join, the
case-9 definition-source join, the patch join, the `UNIQUE` dedup constraint,
and an unconstrained "missing dependency" reference -- all behaved as
designed. All five `Down` migrations were then applied in reverse order and
left a clean database (no leftover tables or types). The full pipeline was
also run end-to-end against this schema via `storage.S3DbStorage` (real
Postgres + a mocked S3 bucket), reproducing the same classification results
and metadata transformations as the in-memory backend's smoke test.
