# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

FastAPI service ("NttBanca API") backing a regulatory assistant (SBS banking regulations) for an analyst
to ask questions and get answers backed by a 4-agent pipeline: **BUSCADOR → VIGENCIA → CONFLICTOS → REDACTOR**
(search → validity check → conflict check → draft). It runs on PostgreSQL (AWS RDS) and S3. This module was
imported into the parent monorepo via `git subtree` (see the root `CLAUDE.md`); it is self-contained with its
own `.venv`, `.env`, `Dockerfile`, and dependencies.

Full functional guide (endpoints, query lifecycle, use cases, how to wire agents to an LLM):
`docs/ASISTENTE_NORMATIVO.md`. AWS setup: `docs/SETUP_AWS.md`. EC2 deploy: `docs/DEPLOY_EC2.md`.

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate   # or .\.venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt
cp .env.example .env        # fill in DB/AWS credentials, see docs/SETUP_AWS.md

# Run (dev server, auto-reload)
fastapi dev app/main.py     # http://127.0.0.1:8000/docs

# Tests (no AWS/DB credentials needed — SQLite in-memory + moto-mocked S3)
pip install -r requirements-dev.txt
pytest
pytest tests/test_files.py::test_name   # single test

# Migrations (plain SQL files in migrations/, applied by app/db/migrate.py)
python -m app.db.migrate --status    # read-only: applied vs pending
python -m app.db.migrate --dry-run   # apply + rollback, to validate a new migration
python -m app.db.migrate             # apply pending migrations

# Docker (local)
docker compose up --build --watch                                              # against real RDS + S3 from .env
docker compose -f docker-compose.yml -f docker-compose.local-db.yml up --build # local Postgres 18 (port 5433), real S3
docker compose logs -f api
docker compose down   # add both -f flags above if using local-db, and -v to also drop the local DB volume
```

Health checks once running: `GET /health/db` (`SELECT 1` against RDS), `GET /health/s3` (`head_bucket`).

## Architecture

### Data model and traceability chain

`ejecucion` (a question) → `paso_agente` (one row per agent step) → `salida` (JSON, cites `documento_id`) →
`items` (a regulatory document/internal policy) → `files` (pointer to the S3 object) → S3 object.

- **`items`**: a document (SBS regulation or internal policy). Normative fields (`tipo`, `codigo_norma`,
  `fecha_vigencia`, `estado` VIGENTE/DEROGADA, `reemplaza_a` → self-FK to the document it replaces) are all
  optional on create.
- **`files`**: a DB row pointing at an S3 object (`bucket` + `s3_key`, unique together). May belong to an
  `item` (`item_id`, nullable, cascades on item delete) or stand alone. The DB never stores the file content.
- **`ejecucion`**: one user question (`pregunta`), tracked by `estado` (PENDIENTE → EN_PROCESO → COMPLETADO |
  ERROR) and `paso_actual` (which agent is running). Grouped by `sesion_id` for history.
- **`paso_agente`**: one row per pipeline step per execution, with that agent's validated JSON `salida`,
  timing, and error detail if it failed.

Schema is versioned as plain SQL files in `migrations/*.sql`, applied once each, in order, inside a single
transaction, tracked in `schema_migrations` (see `app/db/migrate.py`). They also auto-apply on API startup
when `DB_AUTO_CREATE_TABLES=true` (default) and on every EC2 deploy. **Add a new numbered file for schema
changes — never edit one already applied.**

### Agent pipeline (`app/services/orquestador.py`, `app/agentes/`)

- `POST /consultas` returns `202` immediately with `{ejecucion_id, sesion_id, estado}` and runs the pipeline
  via FastAPI `BackgroundTasks`; clients poll `GET /consultas/{id}` every 1-2s until `COMPLETADO` or `ERROR`.
- The orchestrator runs `PIPELINE` (defined in `orquestador.py`) in order: BUSCADOR → VIGENCIA → CONFLICTOS →
  REDACTOR. Each agent function has signature `(pregunta, contexto_previo) -> dict`, where
  `contexto_previo["BUSCADOR"]` etc. holds the prior agents' already-validated output.
  Each agent currently lives in `app/agentes/<agente>.py` as a **stub** returning example data (marked
  `[Ejemplo]`); `demo.py` and `AGENT_STUB_DELAY_MS` (default 1000ms) simulate latency for demo purposes.
  Replacing a stub with a real LLM call means keeping the same signature and satisfying its contract.
- Every agent's output is validated against a Pydantic contract in `app/agentes/contratos.py`
  (`SalidaBuscador`, `SalidaVigencia`, `SalidaConflictos`, `SalidaRedactor`). If validation fails, the
  orchestrator marks that step `ERROR` (with the failing field) and halts the pipeline — the API itself
  never raises; `ejecutar_pipeline` catches everything and records failure on the `ejecucion` row.
- If the API restarts mid-pipeline, that `ejecucion` is stuck in `EN_PROCESO` and is **not** resumed
  (known gap, see README "Próximos pasos").

### S3/DB consistency (`app/services/files.py`, `app/services/s3.py`)

A `files` row must never point at a nonexistent S3 object, enforced by ordering, not transactions spanning
both systems:
- **Create/replace**: upload to S3 first, then write the DB row. If the DB write fails, the just-uploaded
  object is deleted. On replace, a *new* S3 key is used and the old object is deleted only after the DB
  commit succeeds (so the record always points at a complete object).
- **Delete** (a file, or an item cascading to its files): delete the DB row(s) first, then the S3 object(s).
  If the S3 delete fails, the object is orphaned in the bucket and logged, but no DB row references it.
- S3 keys are generated as `S3_KEY_PREFIX/<uuid>.<ext>`; the original filename is kept only in the DB.

### Layout

```
app/
├── main.py                  # app factory, router registration, runs migrations on startup
├── core/config.py           # pydantic-settings, reads .env (Settings, get_settings())
├── db/                      # engine/session (session.py), Base (base.py), migration runner (migrate.py)
├── models/                  # SQLAlchemy ORM models + enums (Agente, EstadoEjecucion, EstadoPaso, ...)
├── schemas/                 # Pydantic request/response models
├── crud/                    # direct Postgres queries, one file per entity
├── agentes/                 # one file per pipeline agent (stubs) + contratos.py (output contracts)
├── services/s3.py           # S3 client wrapper
├── services/files.py        # combined S3+DB operations (see consistency rules above)
├── services/orquestador.py  # runs the 4-agent pipeline, persists each step
└── api/routes/              # health, items, files, consultas endpoints
migrations/                  # versioned schema SQL, applied by app/db/migrate.py
tests/                       # pytest + SQLite in-memory + moto-mocked S3 (see tests/conftest.py)
scripts/                     # aws_setup_dev.sh, aws_deploy_ec2.sh, ec2/deploy_remote.sh
```

### Testing approach

`tests/conftest.py` sets dummy env vars *before* importing the app (so nothing touches real RDS/S3), then
overrides `get_db`/`get_session_factory` with a SQLite in-memory engine and `get_s3_service` with a
`moto`-mocked S3 client via FastAPI dependency overrides. No AWS or DB credentials are ever needed to run
the suite.
