-- Runs once, on first boot of the `db` volume (postgres entrypoint applies
-- everything under /docker-entrypoint-initdb.d/ in lexical order).
--
-- POSTGRES_DB only creates the nttbanca-n database. ingesta and nttbanca-n
-- have diverged schemas for a same-named `documents` table (source_uri vs.
-- raw_text), so they can't share one database -- give ingesta its own,
-- co-located on the same local Postgres instance/server.
CREATE DATABASE ingesta;
