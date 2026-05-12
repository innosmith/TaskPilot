# TaskPilot Test-Anleitung

> **Stand:** Mai 2026 — 4-Schichten-Testkonzept

---

## Kurzreferenz

```bash
make test           # Schicht 1: Backend Unit-Tests (schnell, keine Credentials)
make test-smoke     # Schicht 2: Integration Health + Auth (interaktiver Passwort-Prompt)
make test-contract  # Frontend↔Backend-Kompatibilitaet (keine Credentials)
make test-e2e       # Schicht 3: Playwright UI-Tests (interaktiver Passwort-Prompt)
make test-explore   # Schicht 4: AI-Audit mit browser-use (interaktiv, 5–15 Min)
make test-all       # Schicht 1 + 2 + Contract zusammen
```

---

## Schicht 1 — Backend Unit-Tests

**Befehl:** `make test`

**Was wird getestet:**
- Router-Contracts (Auth, Tasks, Projects — RBAC, Schema-Validierung)
- API-Client-Mocking (Graph, Pipedrive, Bexio, Toggl — via respx)
- Isolierte Helper-Funktionen (XSS-Sanitize, Assignee-Aufloesung, Cron-Validierung)
- Triage-Prompt-Qualitaet, MCP-Handler

**Voraussetzungen:**
- PostgreSQL laeuft auf Port 5435 (`make infra` oder `make dev`)
- Python-venv aktiviert

**Keine Credentials noetig.** Alle externen APIs und Auth werden gemockt.

```bash
cd /home/innosmith/dev/github/TaskPilot
make test

# Einzelne Datei:
cd src/backend && python -m pytest tests/test_auth_router.py -v

# Nach Keyword:
cd src/backend && python -m pytest tests/ -k "sanitize" -v
```

**Aktueller Stand:** 151 Tests, ~6 Sekunden.

---

## Schicht 2 — Smoke-Tests (Multi-Container)

**Befehl:** `make test-smoke`

**Was wird getestet:**
- Health-Checks: Backend (`/api/health`), Frontend (HTTP 200), OpenAPI-Schema
- Auth-Roundtrip: Login → Token → geschuetzter Endpoint
- Kritische Endpoints: `/api/projects`, `/api/pipeline`, `/api/tags`, SSE
- LLM-Gateway: `/api/models/available` (Ollama/LiteLLM erreichbar?)
- InvoiceInsight: `/api/creditors/dashboard` (MCP-Konnektivitaet)
- Docker-Integration: Upload-Volumes beschreibbar, Alembic im Image, Nginx body-size, Pipeline-Struktur

**Voraussetzungen:**
- Integration-Umgebung laeuft (`make int`)

**Credentials:**
- Health-Checks brauchen **kein Passwort**
- Auth-Tests fragen das Passwort **interaktiv** ab (getpass — nicht sichtbar, nicht gespeichert)
- Leere Eingabe = Auth-Tests werden uebersprungen, Health-Tests laufen trotzdem

```bash
make int            # Integration starten (einmalig)
make test-smoke     # Smoke-Tests ausfuehren
```

**Gegen andere Umgebung (z.B. Dev):**
```bash
TP_SMOKE_BACKEND_URL=http://localhost:8000 \
TP_SMOKE_FRONTEND_URL=http://localhost:5173 \
make test-smoke
```

---

## OpenAPI-Contract-Guard

**Befehl:** `make test-contract`

**Was wird getestet:**
- 45+ API-Endpoints die das Frontend nutzt, muessen im Backend-Schema existieren
- Methode (GET/POST/PATCH/DELETE) muss uebereinstimmen

**Voraussetzungen:**
- Backend laeuft (Dev oder Integration)
- **Keine Credentials noetig**

```bash
make test-contract

# Gegen Integration:
TP_SMOKE_BACKEND_URL=http://localhost:8100 make test-contract
```

---

## Schicht 3 — Playwright E2E-Tests

**Befehl:** `make test-e2e`

**Was wird getestet:**
- Login-Flow (Formular, Fehler, Redirect)
- Geschuetzte Routen (Redirect zu /login ohne Auth)
- Owner-Navigation (alle Seiten erreichbar)
- Task-CRUD (Board-Navigation, Pipeline-Spalten)
- RBAC (Member sieht kein Cockpit/Inbox/Agenten, Owner sieht alles)

**Voraussetzungen:**
- Integration-Umgebung laeuft (`make int`)
- Playwright + Chromium installiert (einmalig: `pip install playwright pytest-playwright && playwright install chromium`)

**Credentials:**
Beim Start erscheint ein interaktiver Prompt:

```
============================================================
  TaskPilot E2E-Tests — Credential-Eingabe
  Ziel: http://localhost:3100
============================================================

  Owner-Email: (aus TP_OWNER_EMAIL)
  Owner-Passwort: ********      ← Eingabe nicht sichtbar

  Kein TP_TEST_MEMBER_EMAIL gesetzt — Member-Tests uebersprungen.
============================================================
```

- Passwort lebt nur im RAM waehrend der Test-Session
- Ohne Passwort: Login-abhaengige Tests werden uebersprungen
- Login-Seite-Tests und Protected-Route-Tests laufen immer

**Member-Tests aktivieren (optional):**
```bash
export TP_TEST_MEMBER_EMAIL=kunde@example.com
make test-e2e
# → Member-Passwort wird zusaetzlich abgefragt
```

**Gegen andere Umgebung:**
```bash
TP_E2E_BASE_URL=http://localhost:5173 \
TP_E2E_BACKEND_URL=http://localhost:8000 \
make test-e2e
```

---

## Schicht 4 — AI-Explorations-Audit

**Befehl:** `make test-explore`

**Was wird getestet:**
- Navigations-Audit: Alle Hauptseiten laden korrekt
- Visual-Audit: Kanban-Spalten, ueberlagerte Elemente, Button-Sichtbarkeit
- Ergebnis: Markdown-Report in `tests/ai-audit/reports/`

**Voraussetzungen:**
- Integration-Umgebung laeuft (`make int`)
- Ollama laeuft mit `qwen3.5:latest`
- Einmalig: `pip install browser-use langchain-ollama`

**Credentials:**
- Passwort wird interaktiv abgefragt (gleich wie E2E)

**Laufzeit:** 5–15 Minuten (Vision-Analyse ist langsam lokal)

```bash
make test-explore

# Report lesen:
ls tests/ai-audit/reports/
cat tests/ai-audit/reports/audit_*.md
```

---

## Credential-Sicherheit

### Grundregel

Passwoerter werden **nie** in Dateien gespeichert — weder in Testdateien, noch in `.env`-Dateien die Tests laden.

| Kontext | Woher kommen Credentials? |
|---------|--------------------------|
| `make test` (Backend) | Keine noetig — alles gemockt |
| `make test-smoke` | Interaktiver Prompt (getpass) |
| `make test-contract` | Keine noetig |
| `make test-e2e` | Interaktiver Prompt (getpass) |
| `make test-explore` | Interaktiver Prompt |

### .env.test

Die Datei `.env.test` enthaelt **nur** DB-Verbindungsdaten und Auth-Defaults fuer Backend-Unit-Tests. Sie enthaelt **keine externen API-Keys** (kein Graph, Pipedrive, Toggl, Bexio, LLM).

### Was `.env.test` nicht enthaelt (bewusst)

- `TP_GRAPH_*` — kein Microsoft-365-Zugriff in Tests
- `TP_PIPEDRIVE_*` — kein CRM-Zugriff in Tests
- `TP_TOGGL_*` — kein Zeiterfassungs-Zugriff in Tests
- `TP_BEXIO_*` — kein Buchhaltungs-Zugriff in Tests
- `TP_OPENAI_API_KEY`, `TP_ANTHROPIC_API_KEY` etc. — keine LLM-Kosten in Tests

---

## Dateistruktur

```
tests/
├── smoke/
│   └── test_smoke.py              # Schicht 2: Health, Auth, Endpoints
├── contract/
│   └── test_openapi_contract.py   # Frontend↔Backend-Kompatibilitaet
├── e2e/
│   ├── conftest.py                # Interaktiver Passwort-Prompt
│   ├── test_auth_flow.py          # Login, Protected Routes, Navigation
│   ├── test_task_crud.py          # Board, Pipeline
│   └── test_rbac.py               # Member-Restriktionen, Owner-Zugriff
├── ai-audit/
│   ├── run_audit.py               # browser-use + Qwen 3.5
│   └── reports/                   # Generierte Audit-Reports (gitignored)
└── TEST-HOWTO.md                  # Diese Datei

src/backend/tests/
├── conftest.py                    # FakeUser, Auth-Overrides, AsyncClient
├── test_auth_router.py            # /me, Anonymous-Rejection
├── test_tasks_router.py           # RBAC, Schema-Validierung
├── test_projects_router.py        # Owner-only, Anonymous
├── test_task_helpers.py           # Sanitize, Cron, Assignee
├── test_graph_client.py           # Graph-Client (bestehend)
├── test_mcp_handlers.py           # MCP-Handler (bestehend)
├── test_triage_prompt.py          # Triage-Prompt (bestehend)
├── test_pipedrive_client.py       # Pipedrive-Client (bestehend)
├── test_bexio_client.py           # Bexio-Client (bestehend)
├── test_toggl_client.py           # Toggl-Client (bestehend)
└── test_linkedin_extract.py       # LinkedIn-Extraktion (bestehend)
```

---

## Typischer Workflow

```
Code-Aenderung in Cursor
        │
        ▼
   make test              ← bei jeder Aenderung (~6s)
        │
        ▼
   make int               ← nach groesseren Aenderungen
        │
        ▼
   make test-smoke        ← Container laufen? Auth funktioniert?
   make test-contract     ← Frontend/Backend kompatibel?
        │
        ▼
   make test-e2e          ← vor Prod-Deployment
        │
        ▼
   make test-explore      ← 1–2x pro Woche (AI-Audit)
        │
        ▼
   make prod              ← Deployment
```
