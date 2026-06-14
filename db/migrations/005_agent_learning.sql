-- Migration: Agent-Lern-Schicht (Memory & Self-Learning)
-- Datum: 2026-06-14
--
-- Fuegt die strukturierte, sichtbare Lern-Schicht hinzu:
--   agent_feedback  -- erfasste Korrektursignale (Draft-Edits, Reklassifikation, Daumen)
--   agent_episodes  -- episodisches Gedaechtnis mit lokalem Embedding (pgvector-Recall)
--   learned_rules   -- vom Agenten vorgeschlagene, vom Berater freigegebene Regeln
-- sowie Tone-of-Voice-Felder auf sender_profiles.

CREATE EXTENSION IF NOT EXISTS "vector";

-- ── Korrektur-/Feedback-Signale ──────────────────────────
CREATE TABLE IF NOT EXISTS agent_feedback (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_job_id    UUID REFERENCES agent_jobs(id) ON DELETE SET NULL,
    sender_email    TEXT,
    source          TEXT NOT NULL DEFAULT 'cockpit' CHECK (source IN ('cockpit', 'outlook', 'chat', 'system')),
    feedback_type   TEXT NOT NULL CHECK (feedback_type IN (
        'draft_edit', 'approved_clean', 'rejected',
        'triage_reclass', 'task_deleted', 'task_moved',
        'thumbs_up', 'thumbs_down', 'chat_teach'
    )),
    original        JSONB DEFAULT '{}'::jsonb,
    corrected       JSONB DEFAULT '{}'::jsonb,
    diff_text       TEXT,
    reason          TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_feedback_job ON agent_feedback(agent_job_id);
CREATE INDEX IF NOT EXISTS idx_agent_feedback_type ON agent_feedback(feedback_type);
CREATE INDEX IF NOT EXISTS idx_agent_feedback_sender ON agent_feedback(sender_email);
CREATE INDEX IF NOT EXISTS idx_agent_feedback_created ON agent_feedback(created_at DESC);

-- ── Episodisches Gedaechtnis (Recall via pgvector) ───────
CREATE TABLE IF NOT EXISTS agent_episodes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_job_id    UUID REFERENCES agent_jobs(id) ON DELETE SET NULL,
    job_type        TEXT,
    sender_email    TEXT,
    summary         TEXT NOT NULL,
    decision        JSONB DEFAULT '{}'::jsonb,
    was_corrected   BOOLEAN DEFAULT false,
    lesson          TEXT,
    embedding       vector(1024),
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_episodes_job ON agent_episodes(agent_job_id);
CREATE INDEX IF NOT EXISTS idx_agent_episodes_type ON agent_episodes(job_type);
CREATE INDEX IF NOT EXISTS idx_agent_episodes_sender ON agent_episodes(sender_email);
CREATE INDEX IF NOT EXISTS idx_agent_episodes_corrected ON agent_episodes(was_corrected);
-- Vektor-Index (IVFFlat, Cosine). Greift erst ab einigen hundert Zeilen sinnvoll.
CREATE INDEX IF NOT EXISTS idx_agent_episodes_embedding
    ON agent_episodes USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ── Gelernte Regeln (Agent schlaegt vor, Berater gibt frei) ──
CREATE TABLE IF NOT EXISTS learned_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope           TEXT NOT NULL DEFAULT 'triage' CHECK (scope IN ('triage', 'draft', 'task', 'calendar', 'general')),
    rule_text       TEXT NOT NULL,
    evidence        JSONB DEFAULT '{}'::jsonb,
    status          TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'active', 'rejected', 'archived')),
    autonomy_hint   TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    approved_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_learned_rules_status ON learned_rules(status);
CREATE INDEX IF NOT EXISTS idx_learned_rules_scope ON learned_rules(scope);

-- ── Tone-of-Voice-Lernen auf sender_profiles ─────────────
ALTER TABLE sender_profiles ADD COLUMN IF NOT EXISTS learned_tone JSONB DEFAULT '{}'::jsonb;
ALTER TABLE sender_profiles ADD COLUMN IF NOT EXISTS style_notes TEXT;
ALTER TABLE sender_profiles ADD COLUMN IF NOT EXISTS correction_count INT DEFAULT 0;

-- NOTIFY-Trigger fuer Real-Time-Sichtbarkeit im Cockpit
CREATE TRIGGER agent_feedback_notify AFTER INSERT OR UPDATE ON agent_feedback
    FOR EACH ROW EXECUTE FUNCTION notify_change('agent_feedback_changed');

CREATE TRIGGER learned_rules_notify AFTER INSERT OR UPDATE ON learned_rules
    FOR EACH ROW EXECUTE FUNCTION notify_change('learned_rules_changed');
