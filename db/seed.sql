-- TaskPilot Seed-Daten fuer Dev-Umgebung

-- Pipeline-Spalten (Agenda-Zeithorizonte)
INSERT INTO pipeline_columns (id, name, position, column_type) VALUES
    ('a0000000-0000-0000-0000-000000000001', 'Focus',                1.0, 'active'),
    ('a0000000-0000-0000-0000-000000000002', 'This Week',            2.0, 'active'),
    ('a0000000-0000-0000-0000-000000000003', 'Next Week',            3.0, 'planned'),
    ('a0000000-0000-0000-0000-000000000004', 'Waiting for Feedback', 4.0, 'parked'),
    ('a0000000-0000-0000-0000-000000000005', 'This Month',           5.0, 'planned'),
    ('a0000000-0000-0000-0000-000000000006', 'Next Month',           6.0, 'planned'),
    ('a0000000-0000-0000-0000-000000000007', 'Beyond',               7.0, 'horizon');

-- Tags
INSERT INTO tags (id, name, color) VALUES
    ('b0000000-0000-0000-0000-000000000001', 'Urgent',     '#EF4444'),
    ('b0000000-0000-0000-0000-000000000002', 'Important',  '#F59E0B'),
    ('b0000000-0000-0000-0000-000000000003', 'Quick Win',  '#10B981'),
    ('b0000000-0000-0000-0000-000000000004', 'Research',   '#6366F1'),
    ('b0000000-0000-0000-0000-000000000005', 'Admin',      '#8B5CF6'),
    ('b0000000-0000-0000-0000-000000000006', 'Kunde',      '#3B82F6');

-- Projekt 1: TaskPilot Development
INSERT INTO projects (id, name, color, description, background_url, status) VALUES
    ('c0000000-0000-0000-0000-000000000001',
     'TaskPilot Development',
     '#6366F1',
     'Entwicklung des TaskPilot AI-Agenten-Systems',
     'https://images.unsplash.com/photo-1518770660439-4636190af475?w=1920',
     'active');

INSERT INTO board_columns (id, project_id, name, color, position, is_archive) VALUES
    ('d0000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000001', 'Backlog',     '#6B7280', 1.0, false),
    ('d0000000-0000-0000-0000-000000000002', 'c0000000-0000-0000-0000-000000000001', 'In Progress', '#3B82F6', 2.0, false),
    ('d0000000-0000-0000-0000-000000000003', 'c0000000-0000-0000-0000-000000000001', 'Review',      '#F59E0B', 3.0, false),
    ('d0000000-0000-0000-0000-000000000004', 'c0000000-0000-0000-0000-000000000001', 'Done',        '#10B981', 4.0, true);

-- Projekt 2: Kunde Alpha
INSERT INTO projects (id, name, color, description, background_url, status) VALUES
    ('c0000000-0000-0000-0000-000000000002',
     'Kunde Alpha — Beratungsmandat',
     '#3B82F6',
     'Strategieberatung und Digitalisierung',
     'https://images.unsplash.com/photo-1497366216548-37526070297c?w=1920',
     'active');

INSERT INTO board_columns (id, project_id, name, color, position, is_archive) VALUES
    ('d0000000-0000-0000-0000-000000000010', 'c0000000-0000-0000-0000-000000000002', 'Open',         '#6B7280', 1.0, false),
    ('d0000000-0000-0000-0000-000000000011', 'c0000000-0000-0000-0000-000000000002', 'In Arbeit',    '#3B82F6', 2.0, false),
    ('d0000000-0000-0000-0000-000000000012', 'c0000000-0000-0000-0000-000000000002', 'Warten auf FB','#F59E0B', 3.0, false),
    ('d0000000-0000-0000-0000-000000000013', 'c0000000-0000-0000-0000-000000000002', 'Erledigt',     '#10B981', 4.0, true);

-- Projekt 3: Admin & Recurring
INSERT INTO projects (id, name, color, description, status) VALUES
    ('c0000000-0000-0000-0000-000000000003',
     'Admin & Recurring',
     '#8B5CF6',
     'Wiederkehrende administrative Aufgaben',
     'active');

INSERT INTO board_columns (id, project_id, name, color, position, is_archive) VALUES
    ('d0000000-0000-0000-0000-000000000020', 'c0000000-0000-0000-0000-000000000003', 'Todo',     '#6B7280', 1.0, false),
    ('d0000000-0000-0000-0000-000000000021', 'c0000000-0000-0000-0000-000000000003', 'Doing',    '#3B82F6', 2.0, false),
    ('d0000000-0000-0000-0000-000000000022', 'c0000000-0000-0000-0000-000000000003', 'Archiv',   '#10B981', 3.0, true);

-- Tasks fuer TaskPilot Development
INSERT INTO tasks (id, title, description, project_id, board_column_id, board_position, pipeline_column_id, pipeline_position, assignee) VALUES
    ('e0000000-0000-0000-0000-000000000001',
     'nanobot End-to-End Spike',
     '## Ziel\nKann nanobot eine Mail lesen (Graph API MCP), einen Task-Vorschlag generieren und zur Bestaetigung vorlegen?\n\n## Schritte\n- nanobot installieren\n- LiteLLM konfigurieren\n- Ollama-Anbindung testen\n- Function-Calling pruefen',
     'c0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000002', 1.0,
     'a0000000-0000-0000-0000-000000000001', 1.0, 'me'),
    ('e0000000-0000-0000-0000-000000000002',
     'Cockpit MVP: Agenda Pipeline',
     'Cross-Project Pipeline mit 7 Zeithorizont-Spalten und Drag-and-Drop implementieren.',
     'c0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000002', 2.0,
     'a0000000-0000-0000-0000-000000000001', 2.0, 'me'),
    ('e0000000-0000-0000-0000-000000000003',
     'CoPilot-Kategorien via Graph API pruefen',
     'Im Graph Explorer testen, ob CoPilot-Kategorien als `categories` Property sichtbar sind.',
     'c0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000001', 1.0,
     'a0000000-0000-0000-0000-000000000002', 1.0, 'me'),
    ('e0000000-0000-0000-0000-000000000004',
     'PostgreSQL Backup-Cronjob einrichten',
     'Taeglich pg_dump + GPG-Verschluesselung auf separates Volume.',
     'c0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000001', 2.0,
     'a0000000-0000-0000-0000-000000000005', 1.0, 'me');

-- Tasks fuer Kunde Alpha
INSERT INTO tasks (id, title, description, project_id, board_column_id, board_position, pipeline_column_id, pipeline_position, assignee) VALUES
    ('e0000000-0000-0000-0000-000000000010',
     'Statusbericht Q2 erstellen',
     'Quartalsbericht fuer Kunde Alpha mit Fortschritt, naechste Schritte und Budget-Update.',
     'c0000000-0000-0000-0000-000000000002', 'd0000000-0000-0000-0000-000000000011', 1.0,
     'a0000000-0000-0000-0000-000000000002', 2.0, 'me'),
    ('e0000000-0000-0000-0000-000000000011',
     'Workshop-Unterlagen vorbereiten',
     'Miro-Board strukturieren, Praesentation in Markdown erstellen, dann via Converter in PowerPoint exportieren.',
     'c0000000-0000-0000-0000-000000000002', 'd0000000-0000-0000-0000-000000000010', 1.0,
     'a0000000-0000-0000-0000-000000000003', 1.0, 'me'),
    ('e0000000-0000-0000-0000-000000000012',
     'Offerte fuer Phase 2 versenden',
     'Basierend auf Workshop-Ergebnissen Offerte erstellen und an Kunde senden.',
     'c0000000-0000-0000-0000-000000000002', 'd0000000-0000-0000-0000-000000000012', 1.0,
     'a0000000-0000-0000-0000-000000000004', 1.0, 'me');

-- Tasks fuer Admin & Recurring
INSERT INTO tasks (id, title, description, project_id, board_column_id, board_position, pipeline_column_id, pipeline_position, assignee, recurrence_rule) VALUES
    ('e0000000-0000-0000-0000-000000000020',
     'Weekly Review',
     '## Checkliste\n- [ ] Inbox Zero erreichen\n- [ ] Wochenplan fuer naechste Woche erstellen\n- [ ] Offene Approvals pruefen\n- [ ] Toggl-Eintraege kontrollieren',
     'c0000000-0000-0000-0000-000000000003', 'd0000000-0000-0000-0000-000000000020', 1.0,
     'a0000000-0000-0000-0000-000000000001', 3.0, 'me', '0 7 * * MON'),
    ('e0000000-0000-0000-0000-000000000021',
     'Monatsabschluss: Rechnungen + Rapporte',
     'Leistungsrapporte generieren, Rechnungen in Bexio erstellen, PDFs exportieren, E-Mails vorbereiten.',
     'c0000000-0000-0000-0000-000000000003', 'd0000000-0000-0000-0000-000000000020', 2.0,
     'a0000000-0000-0000-0000-000000000006', 1.0, 'me', '0 8 1 * *');

-- Checklisten
INSERT INTO checklist_items (task_id, text, is_checked, position) VALUES
    ('e0000000-0000-0000-0000-000000000020', 'Inbox Zero erreichen', false, 1.0),
    ('e0000000-0000-0000-0000-000000000020', 'Wochenplan fuer naechste Woche erstellen', false, 2.0),
    ('e0000000-0000-0000-0000-000000000020', 'Offene Approvals pruefen', false, 3.0),
    ('e0000000-0000-0000-0000-000000000020', 'Toggl-Eintraege kontrollieren', false, 4.0),
    ('e0000000-0000-0000-0000-000000000021', 'Toggl: alle Eintraege des Monats pruefen', false, 1.0),
    ('e0000000-0000-0000-0000-000000000021', 'Leistungsrapporte als PDF generieren', false, 2.0),
    ('e0000000-0000-0000-0000-000000000021', 'Rechnungen in Bexio erstellen', false, 3.0),
    ('e0000000-0000-0000-0000-000000000021', 'PDFs exportieren und pruefen', false, 4.0),
    ('e0000000-0000-0000-0000-000000000021', 'E-Mails mit Rechnungen vorbereiten', false, 5.0);

-- Task-Tags
INSERT INTO task_tags (task_id, tag_id) VALUES
    ('e0000000-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-000000000002'),
    ('e0000000-0000-0000-0000-000000000003', 'b0000000-0000-0000-0000-000000000003'),
    ('e0000000-0000-0000-0000-000000000010', 'b0000000-0000-0000-0000-000000000006'),
    ('e0000000-0000-0000-0000-000000000011', 'b0000000-0000-0000-0000-000000000006'),
    ('e0000000-0000-0000-0000-000000000012', 'b0000000-0000-0000-0000-000000000006'),
    ('e0000000-0000-0000-0000-000000000012', 'b0000000-0000-0000-0000-000000000002'),
    ('e0000000-0000-0000-0000-000000000020', 'b0000000-0000-0000-0000-000000000005'),
    ('e0000000-0000-0000-0000-000000000021', 'b0000000-0000-0000-0000-000000000005');
