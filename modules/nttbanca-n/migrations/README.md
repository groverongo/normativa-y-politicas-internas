# Database migrations (single shared sequence)

One numbered SQL sequence, shared by both `modules/ingesta` and
`modules/nttbanca-n`, applied against one Postgres database. Previously each
module had its own `migrations/` directory and its own (diverged) copy of the
`documents` table (`source_uri` vs. `raw_text`); they are consolidated here.

Applied by `modules/nttbanca-n/app/db/migrate.py` (tracked in a
`schema_migrations` table, one transaction per file, guarded by a Postgres
advisory lock so two processes never migrate at once).

## Running it

From the repo root:

```bash
make migrate               # apply all pending migrations
make migrate-status        # show applied vs. pending
make migrate-dry-run       # apply + roll back, to validate a new migration
```

Equivalently, from `modules/nttbanca-n/`: `python -m app.db.migrate [--status|--dry-run]`.
`modules/nttbanca-n`'s FastAPI app also auto-applies pending migrations on
startup when `DB_AUTO_CREATE_TABLES=true` (the default) -- the explicit `make
migrate` command is the same code path, just invoked ahead of time.

`modules/ingesta` no longer self-migrates: run `make migrate` once against
the target database before using `STORAGE_BACKEND=postgres`.

## Files

| File | Table(s) | Owner |
|---|---|---|
| `0001_esquema_inicial.sql` | `items`, `files` | nttbanca-n's original schema |
| `0002_orquestador.sql` | `items` (ALTER), `ejecucion`, `paso_agente` | nttbanca-n's agent orchestrator |
| `0003_create_documents.sql` | `documents` | shared ingestion-pipeline metadata graph |
| `0004_create_chunks.sql` | `chunks` | shared |
| `0005_create_document_lineage.sql` | `document_lineage` | shared |
| `0006_create_document_definition_sources.sql` | `document_definition_sources` | shared |
| `0007_create_document_patches.sql` | `document_patches` | shared |
| `0008_create_ingestion_log.sql` | `ingestion_log` | nttbanca-n's agent-interaction log |
| `0009_nttdatabanca_rag_support.sql` | `documents`/`chunks` (ALTER), `chunk_vectors` | modules/nttdatabanca's registry + pgvector-backed search |

The shared tables (`0003`-`0007`) mirror `modules/ingesta/schema.py` /
`modules/nttbanca-n/app/schemas/lifecycle.py`'s pydantic models; see each
module's `storage.py` / `document_graph_storage.py` for how they're read and
written. Raw document text is never stored inline -- `documents.source_uri`
is an S3 object key, fetched/written via each module's S3 client.

## Adding a new migration

Add a new numbered `NNNN_description.sql` file here -- never edit one already
applied. Plain SQL, no Up/Down markers: each file is executed once, as one
statement (so Postgres's simple query protocol handles multiple
semicolon-separated statements, including `$$ ... $$` function bodies,
correctly), inside the single transaction `run_migrations` wraps around it.
