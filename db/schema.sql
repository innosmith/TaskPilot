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
    mfa_secret      TEXT,
    mfa_enabled     BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT now(),
    last_login_at   TIMESTAMPTZ,
    invited_by      UUID REFERENCES users(id),
    must_change_password BOOLEAN DEFAULT false
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
    recurrence_end_date DATE,
    recurrence_max_instances INT,
    template_id     UUID REFERENCES tasks(id),
    email_message_id TEXT,
    calendar_event_id TEXT,
    calendar_duration_minutes INT,
    calendar_preferred_time TEXT,
    needs_review    BOOLEAN DEFAULT false,
    pipedrive_deal_id   INT,
    pipedrive_person_id INT,
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
    task_id         UUID REFERENCES tasks(id) ON DELETE CASCADE,
    job_type        TEXT,
    status          TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'awaiting_approval', 'completed', 'failed')),
    llm_model       TEXT,
    tokens_used     INT,
    cost_usd        NUMERIC(10,4),
    output          TEXT,
    error_message   TEXT,
    metadata        JSONB DEFAULT '{}'::jsonb,
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

-- Audit-Log (sicherheitsrelevante Aktionen, unabhaengig von Task-Activity)
CREATE TABLE audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    action          TEXT NOT NULL,
    resource        TEXT NOT NULL,
    resource_id     TEXT,
    ip_address      TEXT,
    user_agent      TEXT,
    details         JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_audit_log_user ON audit_log(user_id);
CREATE INDEX idx_audit_log_created ON audit_log(created_at DESC);
CREATE INDEX idx_audit_log_action ON audit_log(action);

-- Board-Members (Gast-Zugriff)
CREATE TABLE board_members (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role            TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('member', 'viewer')),
    invited_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(project_id, user_id)
);

-- E-Mail-Triage
CREATE TABLE email_triage (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id      TEXT NOT NULL UNIQUE,
    subject         TEXT,
    from_address    TEXT,
    from_name       TEXT,
    received_at     TIMESTAMPTZ,
    inference_class TEXT,
    triage_class    TEXT CHECK (triage_class IN ('auto_reply', 'task', 'fyi')),
    reply_expected  BOOLEAN DEFAULT false,
    confidence      REAL,
    suggested_action JSONB,
    agent_job_id    UUID REFERENCES agent_jobs(id),
    status          TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'acted', 'dismissed')),
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Absender-Profile (Beziehungsgedaechtnis)
CREATE TABLE sender_profiles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL UNIQUE,
    display_name    TEXT,
    organization    TEXT,
    relationship    TEXT CHECK (relationship IN ('kunde', 'partner', 'lieferant', 'intern', 'hochschule', 'behoerde', 'unbekannt')),
    tone            TEXT CHECK (tone IN ('formell', 'informell', 'neutral')),
    language        TEXT DEFAULT 'de' CHECK (language IN ('de', 'en', 'fr', 'it')),
    notes           TEXT,
    email_count     INT DEFAULT 0,
    last_contact_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
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
CREATE INDEX idx_email_triage_status ON email_triage(status);
CREATE INDEX idx_email_triage_message_id ON email_triage(message_id);
CREATE INDEX idx_tasks_email_message ON tasks(email_message_id);
CREATE INDEX idx_sender_profiles_email ON sender_profiles(email);

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

CREATE TRIGGER email_triage_notify AFTER INSERT OR UPDATE ON email_triage
    FOR EACH ROW EXECUTE FUNCTION notify_change('email_triage_changed');

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

CREATE TRIGGER sender_profiles_updated_at BEFORE UPDATE ON sender_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- LLM-Konversationen
CREATE TABLE llm_conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT,
    task_id         UUID REFERENCES tasks(id) ON DELETE SET NULL,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    model           TEXT NOT NULL,
    mode            TEXT DEFAULT 'chat' CHECK (mode IN ('chat', 'deep_research', 'web_search', 'agent', 'code_execute')),
    temperature     REAL DEFAULT 0.7,
    total_tokens    INT DEFAULT 0,
    total_cost_usd  NUMERIC(10,4) DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE llm_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES llm_conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    model           TEXT,
    tokens          INT,
    cost_usd        NUMERIC(10,6),
    attachments     JSONB DEFAULT '[]'::jsonb,
    citations       JSONB DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Web-Suchen (Tavily etc.)
CREATE TABLE web_searches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query           TEXT NOT NULL,
    provider        TEXT NOT NULL DEFAULT 'tavily',
    results         JSONB NOT NULL DEFAULT '[]'::jsonb,
    result_count    INT DEFAULT 0,
    triggered_by    TEXT NOT NULL DEFAULT 'user' CHECK (triggered_by IN ('user', 'agent', 'system')),
    task_id         UUID REFERENCES tasks(id) ON DELETE SET NULL,
    conversation_id UUID REFERENCES llm_conversations(id) ON DELETE SET NULL,
    user_id         UUID REFERENCES users(id),
    credits_used    INT DEFAULT 1,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Indizes
CREATE INDEX idx_llm_conversations_task ON llm_conversations(task_id);
CREATE INDEX idx_llm_conversations_user ON llm_conversations(user_id);
CREATE INDEX idx_llm_conversations_created ON llm_conversations(created_at DESC);
CREATE INDEX idx_llm_messages_conversation ON llm_messages(conversation_id);
CREATE INDEX idx_llm_messages_created ON llm_messages(created_at);
CREATE INDEX idx_web_searches_task ON web_searches(task_id);
CREATE INDEX idx_web_searches_query ON web_searches USING gin(to_tsvector('german', query));
CREATE INDEX idx_web_searches_created ON web_searches(created_at DESC);
CREATE INDEX idx_web_searches_user ON web_searches(user_id);

-- Trigger
CREATE TRIGGER llm_conversations_updated_at BEFORE UPDATE ON llm_conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Teams-Chat-Triage
CREATE TABLE chat_triage (
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

CREATE INDEX idx_chat_triage_status ON chat_triage(status);
CREATE INDEX idx_chat_triage_message_id ON chat_triage(message_id);
CREATE INDEX idx_chat_triage_chat_id ON chat_triage(chat_id);

CREATE TRIGGER chat_triage_notify AFTER INSERT OR UPDATE ON chat_triage
    FOR EACH ROW EXECUTE FUNCTION notify_change('chat_triage_changed');

-- Notifications
CREATE TABLE notifications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type            TEXT NOT NULL,
    title           TEXT NOT NULL,
    body            TEXT,
    link            TEXT,
    source_type     TEXT,
    source_id       UUID,
    is_read         BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_notifications_user ON notifications(user_id);
CREATE INDEX idx_notifications_user_unread ON notifications(user_id, is_read) WHERE NOT is_read;
CREATE INDEX idx_notifications_created ON notifications(created_at DESC);

CREATE TRIGGER notifications_notify AFTER INSERT OR UPDATE ON notifications
    FOR EACH ROW EXECUTE FUNCTION notify_change('notifications_changed');

-- Mind-Maps
CREATE TABLE mindmap_folders (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    parent_id   UUID REFERENCES mindmap_folders(id) ON DELETE CASCADE,
    owner_id    UUID NOT NULL REFERENCES users(id),
    color       TEXT,
    icon_emoji  TEXT,
    position    FLOAT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE mindmaps (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    folder_id       UUID REFERENCES mindmap_folders(id) ON DELETE SET NULL,
    project_id      UUID REFERENCES projects(id) ON DELETE SET NULL,
    owner_id        UUID NOT NULL REFERENCES users(id),
    visibility      TEXT NOT NULL DEFAULT 'private'
                    CHECK (visibility IN ('private', 'project', 'shared')),
    flow_data       JSONB NOT NULL DEFAULT '{}'::jsonb,
    settings        JSONB NOT NULL DEFAULT '{}'::jsonb,
    background_url  TEXT,
    background_color TEXT,
    thumbnail_url   TEXT,
    is_template     BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE mindmap_shares (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mindmap_id  UUID NOT NULL REFERENCES mindmaps(id) ON DELETE CASCADE,
    token       TEXT NOT NULL UNIQUE DEFAULT encode(gen_random_bytes(24), 'hex'),
    password_hash TEXT NOT NULL,
    permission  TEXT NOT NULL DEFAULT 'view' CHECK (permission IN ('view', 'edit')),
    label       TEXT,
    expires_at  TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_mindmap_folders_owner ON mindmap_folders(owner_id);
CREATE INDEX idx_mindmap_folders_parent ON mindmap_folders(parent_id);
CREATE INDEX idx_mindmaps_owner ON mindmaps(owner_id);
CREATE INDEX idx_mindmaps_folder ON mindmaps(folder_id);
CREATE INDEX idx_mindmaps_project ON mindmaps(project_id);
CREATE INDEX idx_mindmaps_visibility ON mindmaps(visibility);
CREATE INDEX idx_mindmap_shares_mindmap ON mindmap_shares(mindmap_id);
CREATE INDEX idx_mindmap_shares_token ON mindmap_shares(token);

CREATE TRIGGER mindmap_folders_updated_at BEFORE UPDATE ON mindmap_folders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER mindmaps_updated_at BEFORE UPDATE ON mindmaps
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER mindmaps_notify AFTER INSERT OR UPDATE OR DELETE ON mindmaps
    FOR EACH ROW EXECUTE FUNCTION notify_change('mindmaps_changed');

-- Kapazitätsplanung: Projekte (eigene Entität, entkoppelt von projects)
CREATE TABLE capacity_projects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    color           TEXT NOT NULL DEFAULT '#3B82F6',
    icon_url        TEXT,
    icon_emoji      TEXT,
    client_name     TEXT,
    hourly_rate     NUMERIC(10,2),
    is_billable     BOOLEAN DEFAULT true,
    status          TEXT NOT NULL DEFAULT 'bestätigt'
                    CHECK (status IN ('bestätigt', 'vorläufig')),
    project_id      UUID REFERENCES projects(id) ON DELETE SET NULL,
    toggl_project_id INT,
    pipedrive_deal_id INT,
    sort_order      INT DEFAULT 0,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_cap_projects_status ON capacity_projects(status);
CREATE INDEX idx_cap_projects_project ON capacity_projects(project_id);

-- Kapazitätsplanung: Zuweisungen pro Projekt und Woche/Tag
CREATE TABLE capacity_allocations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    capacity_project_id UUID NOT NULL REFERENCES capacity_projects(id) ON DELETE CASCADE,
    week_start          DATE NOT NULL,
    minutes             INT NOT NULL DEFAULT 0,
    allocation_type     TEXT NOT NULL DEFAULT 'week'
                        CHECK (allocation_type IN ('week', 'day')),
    series_id           UUID,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE(capacity_project_id, week_start)
);

CREATE INDEX idx_cap_alloc_week ON capacity_allocations(week_start);
CREATE INDEX idx_cap_alloc_series ON capacity_allocations(series_id);
CREATE INDEX idx_cap_alloc_project ON capacity_allocations(capacity_project_id);

-- Kapazitätsplanung: Ferien und freie Tage
CREATE TABLE capacity_time_off (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date            DATE NOT NULL UNIQUE,
    type            TEXT DEFAULT 'ferien'
                    CHECK (type IN ('ferien', 'feiertag', 'krank', 'sonstiges')),
    label           TEXT,
    hours           REAL DEFAULT 8.0,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_cap_timeoff_date ON capacity_time_off(date);

CREATE TRIGGER capacity_projects_updated_at BEFORE UPDATE ON capacity_projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER capacity_allocations_updated_at BEFORE UPDATE ON capacity_allocations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
