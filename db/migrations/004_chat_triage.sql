-- Migration: Teams-Chat-Triage-Tabelle
-- Datum: 2026-05-03

CREATE TABLE IF NOT EXISTS chat_triage (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id         TEXT NOT NULL,
    message_id      TEXT NOT NULL UNIQUE,
    from_name       TEXT,
    from_id         TEXT,
    body_preview    TEXT,
    chat_type       TEXT,
    received_at     TIMESTAMPTZ,
    triage_class    TEXT CHECK (triage_class IN ('task', 'fyi', 'meeting_summary')),
    confidence      REAL,
    suggested_action JSONB,
    agent_job_id    UUID REFERENCES agent_jobs(id),
    status          TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'acted', 'dismissed')),
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_triage_status ON chat_triage(status);
CREATE INDEX IF NOT EXISTS idx_chat_triage_message_id ON chat_triage(message_id);
CREATE INDEX IF NOT EXISTS idx_chat_triage_chat_id ON chat_triage(chat_id);

CREATE TRIGGER chat_triage_notify AFTER INSERT OR UPDATE ON chat_triage
    FOR EACH ROW EXECUTE FUNCTION notify_change('chat_triage_changed');
