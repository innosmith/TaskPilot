-- Erstellt die Integration-Datenbank im shared Postgres-Container.
-- Die Dev-DB (taskpilot_dev) wird ueber POSTGRES_DB automatisch angelegt.

SELECT 'CREATE DATABASE taskpilot_int OWNER taskpilot'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'taskpilot_int')\gexec

\connect taskpilot_int

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

\i /docker-entrypoint-initdb.d/01-schema.sql
\i /docker-entrypoint-initdb.d/02-seed.sql
