-- Erstellt die Integration-Datenbank im shared Postgres-Container.
-- Die Dev-DB (taskpilot_dev) wird ueber POSTGRES_DB automatisch angelegt.

SELECT 'CREATE DATABASE taskpilot_int OWNER taskpilot'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'taskpilot_int')\gexec

\connect taskpilot_int

-- pgvector Extension
CREATE EXTENSION IF NOT EXISTS vector;
