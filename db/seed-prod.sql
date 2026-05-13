-- TaskPilot Prod-Seed (nur Systemdaten, keine Demo-Daten)
-- Idempotent: ON CONFLICT DO NOTHING

-- Pipeline-Spalten (Agenda-Zeithorizonte)
INSERT INTO pipeline_columns (id, name, position, column_type) VALUES
    ('a0000000-0000-0000-0000-000000000001', 'Focus',                1.0, 'active'),
    ('a0000000-0000-0000-0000-000000000002', 'This Week',            2.0, 'active'),
    ('a0000000-0000-0000-0000-000000000003', 'Next Week',            3.0, 'planned'),
    ('a0000000-0000-0000-0000-000000000004', 'Waiting for Feedback', 4.0, 'parked'),
    ('a0000000-0000-0000-0000-000000000005', 'This Month',           5.0, 'planned'),
    ('a0000000-0000-0000-0000-000000000006', 'Next Month',           6.0, 'planned'),
    ('a0000000-0000-0000-0000-000000000007', 'Beyond',               7.0, 'horizon')
ON CONFLICT DO NOTHING;
