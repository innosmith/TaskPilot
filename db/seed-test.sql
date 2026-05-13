-- TaskPilot Test-Seed-Daten (deterministische Testdaten fuer make test)
-- Wird bei jedem Test-Lauf neu eingespielt (DROP + CREATE + Schema + Seed)
-- UUIDs muessen mit src/backend/tests/conftest.py uebereinstimmen

-- Users (Owner + Member)
INSERT INTO users (id, email, password_hash, display_name, role, is_active) VALUES
    ('00000000-0000-0000-0000-000000000001',
     'test-owner@innosmith.ai',
     '$2b$12$LJ3m4ys3Lz0Y6bK4kK4kKuKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK',
     'Test Owner',
     'owner',
     true),
    ('00000000-0000-0000-0000-000000000002',
     'test-member@innosmith.ai',
     '$2b$12$LJ3m4ys3Lz0Y6bK4kK4kKuKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK',
     'Test Member',
     'member',
     true);

-- Pipeline-Spalten (Agenda-Zeithorizonte)
INSERT INTO pipeline_columns (id, name, position, column_type) VALUES
    ('a0000000-0000-0000-0000-000000000001', 'Focus',                1.0, 'active'),
    ('a0000000-0000-0000-0000-000000000002', 'This Week',            2.0, 'active'),
    ('a0000000-0000-0000-0000-000000000003', 'Next Week',            3.0, 'planned'),
    ('a0000000-0000-0000-0000-000000000004', 'Waiting for Feedback', 4.0, 'parked'),
    ('a0000000-0000-0000-0000-000000000005', 'This Month',           5.0, 'planned'),
    ('a0000000-0000-0000-0000-000000000006', 'Next Month',           6.0, 'planned'),
    ('a0000000-0000-0000-0000-000000000007', 'Beyond',               7.0, 'horizon');

-- Test-Projekt
INSERT INTO projects (id, name, color, description, status) VALUES
    ('f0000000-0000-0000-0000-000000000001',
     'Test-Projekt',
     '#3B82F6',
     'Projekt fuer automatisierte Tests',
     'active');

-- Board-Spalten fuer Test-Projekt
INSERT INTO board_columns (id, project_id, name, color, position, is_archive) VALUES
    ('f1000000-0000-0000-0000-000000000001', 'f0000000-0000-0000-0000-000000000001', 'Backlog',     '#6B7280', 1.0, false),
    ('f1000000-0000-0000-0000-000000000002', 'f0000000-0000-0000-0000-000000000001', 'In Progress', '#3B82F6', 2.0, false),
    ('f1000000-0000-0000-0000-000000000003', 'f0000000-0000-0000-0000-000000000001', 'Done',        '#10B981', 3.0, true);

-- Board-Member: Member-User hat Zugriff auf Test-Projekt
INSERT INTO board_members (id, project_id, user_id, role) VALUES
    ('f2000000-0000-0000-0000-000000000001',
     'f0000000-0000-0000-0000-000000000001',
     '00000000-0000-0000-0000-000000000002',
     'member');

-- Tags
INSERT INTO tags (id, name, color) VALUES
    ('b0000000-0000-0000-0000-000000000001', 'Urgent',    '#EF4444'),
    ('b0000000-0000-0000-0000-000000000002', 'Important', '#F59E0B'),
    ('b0000000-0000-0000-0000-000000000003', 'Quick Win', '#10B981');
