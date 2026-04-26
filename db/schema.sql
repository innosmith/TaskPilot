-- TaskPilot PostgreSQL Schema v0.12
-- Basierend auf Pflichtenheft Sektion 7.5.2

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Projekte
CREATE TABLE projects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    color           TEXT NOT NULL DEFAULT '#3B82F6',
    description     TEXT,
    background_url  TEXT,
    icon_url        TEXT,
    icon_emoji      TEXT,
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived', 'paused')),
    priority        INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Board-Spalten pro Projekt (Custom-Kanban)
CREATE TABLE board_columns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    color           TEXT,
    icon_emoji      TEXT,
    position        FLOAT NOT NULL,
    is_archive      BOOLEAN DEFAULT false
);

-- Pipeline-Spalten (Agenda — globale Zeithorizonte)
CREATE TABLE pipeline_columns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    color           TEXT,
    icon_emoji      TEXT,
    position        FLOAT NOT NULL,
    column_type     TEXT NOT NULL DEFAULT 'horizon' CHECK (column_type IN ('active', 'planned', 'parked', 'horizon'))
);

-- Users
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    avatar_url      TEXT,
    role            TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'member', 'viewer')),
    is_active       BOOLEAN DEFAULT true,
    settings        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT now(),
    last_login_at   TIMESTAMPTZ
);

-- Tasks
CREATE TABLE tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    description     TEXT,
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    board_column_id UUID NOT NULL REFERENCES board_columns(id),
    board_position  FLOAT NOT NULL,
    pipeline_column_id UUID REFERENCES pipeline_columns(id),
    pipeline_position  FLOAT,
    assignee        TEXT NOT NULL DEFAULT 'me',
    due_date        DATE,
    data_class      TEXT NOT NULL DEFAULT 'internal' CHECK (data_class IN ('public', 'internal', 'confidential', 'highly_confidential')),
    llm_override    TEXT,
    autonomy_level  TEXT NOT NULL DEFAULT 'L1' CHECK (autonomy_level IN ('L0', 'L1', 'L2', 'L3')),
    is_completed    BOOLEAN DEFAULT false,
    is_pinned       BOOLEAN DEFAULT false,
    recurrence_rule TEXT,
    template_id     UUID REFERENCES tasks(id),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Checklisten-Eintraege
CREATE TABLE checklist_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    text            TEXT NOT NULL,
    is_checked      BOOLEAN DEFAULT false,
    position        FLOAT NOT NULL
);

-- Tags
CREATE TABLE tags (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL UNIQUE,
    color           TEXT NOT NULL DEFAULT '#6B7280'
);

CREATE TABLE task_tags (
    task_id         UUID REFERENCES tasks(id) ON DELETE CASCADE,
    tag_id          UUID REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, tag_id)
);

-- Anhaenge
CREATE TABLE attachments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    filepath        TEXT NOT NULL,
    mime_type       TEXT,
    uploaded_at     TIMESTAMPTZ DEFAULT now()
);

-- Agent-Jobs
CREATE TABLE agent_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'awaiting_approval', 'completed', 'failed')),
    llm_model       TEXT,
    tokens_used     INT,
    cost_usd        NUMERIC(10,4),
    output          TEXT,
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Aktivitaets-Log
CREATE TABLE activity_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    event_type      TEXT NOT NULL,
    actor           TEXT NOT NULL,
    details         JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Board-Members (Gast-Zugriff)
CREATE TABLE board_members (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role            TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('member', 'viewer')),
    invited_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(project_id, user_id)
);

-- Indizes
CREATE INDEX idx_tasks_project ON tasks(project_id);
CREATE INDEX idx_tasks_board_column ON tasks(board_column_id);
CREATE INDEX idx_tasks_pipeline_column ON tasks(pipeline_column_id);
CREATE INDEX idx_tasks_assignee ON tasks(assignee);
CREATE INDEX idx_tasks_is_completed ON tasks(is_completed);
CREATE INDEX idx_checklist_items_task ON checklist_items(task_id);
CREATE INDEX idx_activity_log_task ON activity_log(task_id);
CREATE INDEX idx_activity_log_created ON activity_log(created_at);
CREATE INDEX idx_agent_jobs_task ON agent_jobs(task_id);
CREATE INDEX idx_agent_jobs_status ON agent_jobs(status);
CREATE INDEX idx_board_columns_project ON board_columns(project_id);
CREATE INDEX idx_board_members_project ON board_members(project_id);
CREATE INDEX idx_board_members_user ON board_members(user_id);

-- NOTIFY-Trigger fuer Real-Time-Updates
CREATE OR REPLACE FUNCTION notify_change() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify(TG_ARGV[0], json_build_object(
        'op', TG_OP, 'id', COALESCE(NEW.id, OLD.id)
    )::text);
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tasks_notify AFTER INSERT OR UPDATE OR DELETE ON tasks
    FOR EACH ROW EXECUTE FUNCTION notify_change('tasks_changed');

CREATE TRIGGER agent_jobs_notify AFTER INSERT OR UPDATE ON agent_jobs
    FOR EACH ROW EXECUTE FUNCTION notify_change('agent_jobs_changed');

-- updated_at Trigger
CREATE OR REPLACE FUNCTION update_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER projects_updated_at BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER tasks_updated_at BEFORE UPDATE ON tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
