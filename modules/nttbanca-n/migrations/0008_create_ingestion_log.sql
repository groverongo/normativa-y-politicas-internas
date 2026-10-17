-- Agent-interaction log for the ingestion pipeline (Classifier/Extraction/
-- Validation/Graph-Update), one row per event. Ported from the event
-- taxonomy of modules/ingesta/logging_trace.py's InteractionLogger, but
-- backed by Postgres instead of local runs/<run_id>/interaction_log.jsonl
-- files (which wouldn't survive an EC2 redeploy or be shared across
-- instances). Referenced by: app/services/ingestion_logger.py (new),
-- app/db/migrate.py's migration runner.
-- Facts: called by app/db/migrate.py; confirmed absent via parallel ls; pure
-- DDL, no data records; part of the approved "richer ingesta workflow" plan.

CREATE TABLE ingestion_log (
    id          BIGSERIAL PRIMARY KEY,
    run_id      TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_file TEXT,
    doc_id      TEXT,
    event       TEXT NOT NULL
                CHECK (event IN (
                    'run_start', 'document_start', 'agent_call', 'agent_result',
                    'feedback', 'loop_decision', 'storage_op', 'error',
                    'document_end', 'run_end'
                )),
    agent       TEXT NOT NULL,
    from_agent  TEXT,
    to_agent    TEXT,
    loop        TEXT,
    iteration   INTEGER,
    attempt     INTEGER,
    message     TEXT NOT NULL DEFAULT '',
    input       JSONB,
    output      JSONB,
    llm         JSONB,
    UNIQUE (run_id, seq)
);

CREATE INDEX idx_ingestion_log_run_id ON ingestion_log (run_id, seq);
CREATE INDEX idx_ingestion_log_doc_id ON ingestion_log (doc_id);
