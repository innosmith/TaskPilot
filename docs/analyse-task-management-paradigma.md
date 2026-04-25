# Analyse: Vom klassischen Kanban zum Agentic Task Management

> **Zweck:** Paradigmen-Challenge + Architektur-Empfehlung — muss TaskPilot ein klassisches Task-Management-System nutzen, oder ist ein eigenes agentisches Cockpit der richtige Weg?  
> **Datum:** 25. April 2026 (v2 — mit Gemini- und Perplexity-Research integriert)  
> **Status:** Entscheidungsvorlage — Auswirkungen auf Pflichtenheft separat zu besprechen  
> **Referenz:** [Pflichtenheft v0.8](pflichtenheft-taskpilot.md), Gemini Deep Research (April 2026), Perplexity Research (April 2026)

---

## 1. Die Kernthese

**Klassische Task-Management-Systeme (Trello, MeisterTask, Plane, Vikunja) sind die falsche Kategorie für TaskPilot.**

Sie wurden als "Systems of Record" für menschliche Akteure konzipiert. TaskPilot braucht ein "System of Collaboration" für Mensch-Agent-Teams. Das ist kein Optimierungsproblem (welches Kanban-Tool?), sondern ein **Paradigmenwechsel**.

Die Research bestätigt: Seit Anfang 2026 existiert eine neue Kategorie "Agentic Task Management", die genau diesen Paradigmenwechsel vollzieht — allerdings fast ausschliesslich für Coding-Agents. Für den allgemeinen Solo-Operator-Kontext (IT-Beratung, Schulung, Dokumentenerstellung) **existiert noch kein fertiges System**, das alle Kernanforderungen abdeckt.

Aber: Die Bausteine sind vorhanden. Und ein Trello-Klon mit Claude Code in Minuten zu bauen, ist keine Hexerei — die Herausforderung liegt nicht in der Board-Oberfläche, sondern im agentischen Interaktionsmodell dahinter.

---

## 2. Was klassisches Task-Management nicht leisten kann

| Was TaskPilot braucht | MeisterTask/Plane/Vikunja | Lücke |
|---|---|---|
| Tasks aus vielen Quellen (Mail, SIGNA, InvoiceInsight, Agent) | Tasks nur manuell oder via API | Keine Unified Inbox |
| Agent als Akteur mit eigenen States (running, blocked, awaiting-approval) | Kein Konzept von "Agent führt aus" | Kein Agent-Lifecycle |
| Approval-Workflows mit Rich Review (Dokumente, Mails prüfen) | Kein Approval-Konzept | Keine Review-Oberfläche |
| LLM-Wahl, Datenklasse, Autonomie-Stufe pro Task | Keine Agent-Metadaten | Kein Parametermodell |
| Agent-State-Visibility (was läuft, was ist in der Queue) | Kein Agent-Dashboard | Keine Echtzeit-Sicht |
| Memory-Inspektion und -Korrektur | Kein Memory-Konzept | Keine Lern-Transparenz |
| Kosten-Tracking pro Task (Tokens, Modell) | Keine LLM-Kosten-Dimension | Kein Cost-Logging |
| Wochenplanung als Mensch-Agent-Dialog | Rein manuelles Planen | Keine agentische Planung |

**Fazit:** Selbst das beste klassische Tool deckt bestenfalls 30% dessen ab, was TaskPilot braucht. Der Rest müsste drum herum gebaut werden — was die Komplexität erhöht, statt sie zu reduzieren.

---

## 3. State of the Art: Agentic Task Management (April 2026)

### 3.1 Drei Schichten am Markt

Die beiden Deep-Research-Ergebnisse (Gemini, Perplexity) identifizieren drei Schichten:

**Schicht 1 — Coding-fokussierte Agentic Boards** (architektonisch lehrreich, aber nicht direkt nutzbar):

| Tool | Stars | Kernidee | Stack | Verifiziert? |
|------|-------|----------|-------|-------------|
| **Multica** | 20K+ | Agents als Teammates, Skills-System, Task-Lifecycle | Next.js + Go + PostgreSQL + pgvector | Gemini: ja, Perplexity: **nicht verifizierbar** |
| **Vibe Kanban** (BloopAI) | 22K+ | Git-Worktree-Isolation pro Agent-Task, MCP-Config | Rust + JavaScript | Perplexity: ja |
| **Cline Kanban** | — | `npx kanban` aus jedem Git-Repo, Dependency-Chaining | CLI-basiert | Perplexity: ja |
| **kandev** | Mittel | Multi-Agent-Orchestrierung, YAML-Pipelines mit Gates | TypeScript | Gemini: ja, Perplexity: **nicht verifizierbar** |
| **Veritas Kanban** | Mittel | "Visual Command Center", YAML-Pipelines, 6 Gate-Typen | TypeScript | Gemini: ja |

**Schicht 2 — Allgemeine Agentic Boards für Solo-Operators** (direkt relevant):

| Tool | Stars | Kernidee | Stack | Verifiziert? |
|------|-------|----------|-------|-------------|
| **Mission Control** | 339 | **Explizit für Solo-Entrepreneurs mit AI-Agent-Teams.** Eisenhower-Matrix, Kanban, Goal Hierarchy, Agent Crew, Inbox/Decisions-Queue, Approval-Workflows, Spend-Limits, Loop-Detection, Cost/Token-Tracking | Next.js 15 + JSON-Files + PM2 | Perplexity: ja (AGPL-3.0) |
| **Symio** | — | Human-AI-Kanban mit Approvals, MCP-Integration | SaaS (closed) | Perplexity: **nicht verifizierbar** |

**Schicht 3 — Klassische Tools mit MCP-Bridge** (pragmatisch, aber paradigmatisch veraltet):

| Tool | Stars | MCP-Server | Eignung |
|------|-------|-----------|---------|
| **Plane CE** | ~35K | Offiziell (`makeplane/plane-mcp-server`) | Reife API, Docker, aber kein Agent-Lifecycle |
| **Vikunja** | ~15K | Community (`vikunja-mcp`) | Leichtgewichtig, aber gleiche Paradigma-Grenzen |
| **Huly** | 25K+ | Noch nicht | All-in-One (Inbox, Chat, Docs, Kalender), aber AI nur als Assistent, nicht als Akteur |

### 3.2 Mission Control: Der bisher beste Treffer

**Mission Control** (MeisnerDan, AGPL-3.0) ist das einzige verifizierte Projekt, das explizit für Solo-Entrepreneurs mit AI-Agent-Teams gebaut wurde:

**Stärken:**
- **Agent-First-Design:** Tasks haben Assignee (Agent-Rolle), Inbox, Decisions-Queue
- **Field Ops:** Approval-Workflows mit 3 Autonomie-Levels (Manual / Supervised / Full Autonomy) + Spend-Limits + Encrypted Vault
- **Loop-Detection:** Auto-Eskalation nach 3 gescheiterten Versuchen
- **Cost/Token-Tracking** pro Task und Session
- **Slash-Commands:** `/daily-plan`, `/standup`, `/orchestrate`
- Token-optimierte API: 50 Tokens statt 5.400 für einen Task-Context

**Schwächen / Grenzen:**
- Aktuell nur Claude Code als Agent-Runtime (kein nanobot/Ollama-Support out-of-the-box)
- Keine Mail-Integration (kein Unified Inbox)
- JSON-File-Storage (für Solo-Operator ok, aber kein PostgreSQL)
- 339 Stars — kleines Ökosystem, Abandoned-Risk
- AGPL-3.0-Lizenz — weniger permissiv als MIT
- Kein LLM-Routing/Override-Konzept

**Fazit:** Wertvoller als Design-Referenz (Patterns, Workflows, Slash-Commands), aber nicht als Basis-Framework. Zu eng an Claude Code gebunden, zu klein für langfristige Abhängigkeit.

### 3.3 Wichtige Warnung zur Verifizierbarkeit

Perplexity konnte **Multica, Symio, AgentBoard und kandev nicht verifizieren** — möglicherweise sehr frühe Projekte, Stealth-Phase oder Marketing-Namen ohne substantielle Codebase. Gemini listet sie als existent. Die Wahrheit liegt wahrscheinlich dazwischen: Real, aber noch unreif oder zu nischig, um als Basis zu dienen.

---

## 4. Architektur-Patterns aus der Research

### 4.1 Der agentische Task-Lifecycle

Beide Research-Berichte konvergieren auf ein Standard-Muster:

```
created → claimed → in-progress → awaiting-approval → [approved/rejected] → completed/failed
                        ↓                                          ↗
                     blocked (Agent meldet Hindernis proaktiv)
```

**Wichtig:** Der `awaiting`-State ist das technische Fundament für HITL-Workflows. Der Agent pausiert aktiv und wartet auf menschlichen Input. Erst nach explizitem `resume` geht die Ausführung weiter. Das ist fundamental anders als klassische Kanban-Spalten.

### 4.2 Fünf HITL-Patterns (aus Cordum/Applied AI Newsletter)

| Pattern | Auslöser | Throughput | TaskPilot-Relevanz |
|---------|----------|-----------|-------------------|
| **Pre-execution Approval Gate** | Jede Agent-Aktion | Niedrig | Mail-Entwürfe, externe Kommunikation (L1) |
| **Exception Escalation** | Confidence < Threshold | Hoch | Research-Outputs, unsichere Klassifikationen |
| **Graduated Autonomy** | Trust wächst über Zeit | Mittel | Standard-Berichte, Templates (L1→L2 Vorschlag) |
| **Sampled Audit** | Zufällige Stichproben | Sehr hoch | Batch-Tasks (Toggl-Einträge, FYI-Archivierung) |
| **Checkpoint** | Definierte Workflow-Stufe | Mittel | Dokument-Erstellung, Angebote |

**Kritische Design-Erkenntnis:** Der Unterschied zwischen *Escape-Hatch* (übergibt komplett an den Menschen) und *Checkpoint* (Agent wartet auf Feedback und arbeitet dann weiter) ist fundamental. TaskPilots L1-Approval sollte ein Checkpoint sein, kein Escape-Hatch.

### 4.3 Fünf Pflicht-UI-Elemente (aus Fuselab Creative Agent UX 2026)

1. **Planning Visibility** — zeige die intendierte Aktionssequenz *vor* der Ausführung
2. **Tool-Use Disclosure** — welche externen Systeme wurden aufgerufen, was wurde zurückgegeben
3. **Memory Surfacing** — persistenter Kontext diskret anzeigen (z.B. "Aus Kontext: Kunde X bevorzugt Deutsch")
4. **Multi-Step Workflow Tracking** — Fortschrittsanzeige bei langen Tasks
5. **Recovery Routing** — intuitive Override-Mechanismen ohne Friktion

### 4.4 Memory-Visibility-Patterns

| Pattern | Beschreibung | Umsetzung |
|---------|-------------|-----------|
| **Inline Memory Badges** | Agent zeigt diskret an, wenn er gespeichertes Wissen nutzt | "Aus Kontext: Kunde X hat Budget-Freeze bis Q3" |
| **Memory Browser** | Separates Panel zum Inspizieren und Korrigieren gespeicherter Fakten | Strukturierte Sicht auf MEMORY.md / pgvector |
| **Learning Events** | Explizite Benachrichtigung bei neuem Wissen | "Ich habe notiert: Projekt Y Deadline 30. Juni" |
| **Memory Decay Signaling** | Fakten mit Zeitstempel, die zur Re-Validierung vorgeschlagen werden | "Letztes Update zu Kunde Z ist 3 Monate alt — noch aktuell?" |

### 4.5 Skills als Package-System

Das **SKILL.md-Format** (agentskills.io, JFrog Agent Skills Registry) etabliert sich als Standard:

- Skills als Markdown-Dateien, versioniert in Git
- **Progressive Disclosure:** Erst Name + Beschreibung (Discovery), bei Match voller Inhalt (Activation), dann Execution
- Mission Control implementiert dies als Skills Library mit Bidirektional-Linking

Für TaskPilot bedeutet das: **Berater-spezifische Skill-Packs** (Angebotsschreibung, DSGVO-Analyse, Schulungsplanung, Mail-Triage) als SKILL.md-Dateien im Workspace. nanobot lädt sie bei Bedarf.

### 4.6 Observability: Langfuse als Baustein

Für Agent-State-Visibility empfiehlt Perplexity **Langfuse** (Open Source, Self-Hosted):
- Cost-Dashboard: Token-Kosten pro Agent/Task/Modell
- Latency-Dashboard: Performance-Trends
- Kompatibel mit LiteLLM als Proxy-Layer

Alternative: **AgentState** (leichtgewichtiger HTTP-Service für Real-Time Agent-State-Queries, <15ms Latenz).

---

## 5. Die fehlende Komponente: Das Cockpit

### 5.1 Warum Telegram + Kanban-Board nicht reicht

**Telegram** ist gut für Quick-Capture, einfache Approvals, Push-Notifications und Mobile. Aber:
- Ein 2-seitiger Mail-Entwurf lässt sich nicht im Chat reviewen
- 30+ Tasks über 10 Projekte priorisieren braucht eine visuelle Übersicht
- Agent-State-Monitoring braucht ein Dashboard, kein Chat-Scrolling
- LLM-Wahl und Datenklasse pro Task braucht strukturierte Eingabe

**Klassisches Kanban** kann Tasks visuell darstellen, aber:
- Kein Agent-Lifecycle (queued/running/awaiting-approval/completed/failed)
- Keine Approval-Review-Oberfläche
- Keine Unified Inbox
- Keine Memory-/Kosten-Sicht

### 5.2 Was das Cockpit leisten muss

```
┌─────────────────────────────────────────────────────────────────┐
│  TaskPilot Cockpit                                     [⚙ Settings]
├─────────────┬──────────────────┬────────────────────────────────┤
│  INBOX      │  AGENT-QUEUE     │  PLANNING                      │
│             │                  │                                │
│ ● 3 Mails  │ ● Research X     │  FOCUS:                        │
│   (2 Quick, │   [running ▓▓░]  │   □ Offerte Smith    [Agent]   │
│    1 Task)  │   Claude · 1.2k  │   □ SIGNA-Update     [Ich]     │
│             │     tokens       │                                │
│ ● SIGNA     │ ● Mail-Draft Y   │  THIS WEEK:                    │
│   Score 8   │   [awaiting      │   □ Monatsabschluss  [Agent]   │
│             │    approval] →   │   □ Workshop-Vorb.   [Ich]     │
│ ● Invoice   │                  │                                │
│   Renewal   │ ● Toggl-Report   │  LATER:                        │
│   30 Tage   │   [queued]       │   □ InvoiceInsight   [Gemeins.]│
│             │                  │   □ Schulung planen  [Agent]   │
├─────────────┴──────────────────┤                                │
│  APPROVAL REVIEW               │  MEMORY                        │
│  ┌─────────────────────────┐   │  ● 12 Fakten gelernt (Woche)  │
│  │ Re: Anfrage Kunde X     │   │  ● 2 Korrekturen offen        │
│  │ ...Agent-Entwurf...     │   │  ● Kosten: CHF 4.20 (Woche)   │
│  │ [Memory: "Kunde X       │   │                                │
│  │  bevorzugt Du-Form"]    │   │  SKILLS                        │
│  └─────────────────────────┘   │  ● Mail-Triage: 94% korrekt   │
│  [✓Senden] [✎Edit] [✗Ablehnen]│  ● Research: 78% ohne Korrektur│
└────────────────────────────────┴────────────────────────────────┘
```

**Sechs Kernbereiche:**
1. **Unified Inbox:** Alle eingehenden Signale (Mail, SIGNA, InvoiceInsight, Agent-Vorschläge)
2. **Agent-Queue:** Live-Status mit Fortschritt, Modell, Token-Verbrauch
3. **Planning-View:** Cross-Project-Pipeline (Focus → This Week → Later) mit Assignee (Ich/Agent/Gemeinsam)
4. **Approval-Review:** Rich Review mit Inline-Memory-Badges, Edit-Möglichkeit, Korrektur-Feedback
5. **Memory-Dashboard:** Lern-KPIs, offene Korrekturen, Kosten-Zusammenfassung
6. **Skills-Overview:** Trefferquoten pro Skill, Verbesserungstrends

### 5.3 Wie minimal kann "minimal" sein?

Ein MVP-Cockpit für Phase 1 braucht nur drei Dinge:
1. **Agent-Queue + Status** (was läuft, was wartet auf Approval)
2. **Approval-Review** (Agent-Output anzeigen + Ja/Nein/Edit)
3. **Basis-Planung** (Task-Liste mit Drag-and-Drop-Priorisierung)

Das ist mit Next.js/React + PostgreSQL + Tailwind in **wenigen Tagen** baubar — besonders mit Agentic Engineering. Der Trello-Klon-in-Minuten-Vergleich ist berechtigt: Die Board-Oberfläche ist trivial, das agentische Backend (Agent-Lifecycle, Approval-State-Machine, Memory-Integration) ist die eigentliche Arbeit, und die liegt ohnehin in nanobot + PostgreSQL.

---

## 6. Use Cases, die im heutigen Pflichtenheft noch nicht adressiert sind

### 6.1 Agent-State-Übersicht
Berater öffnet morgens das System: Was hat der Agent über Nacht gemacht? Was wartet auf Freigabe? Was ist fehlgeschlagen?
**Heute:** Telegram-History-Scrolling. **Nötig:** Dashboard.

### 6.2 Rich Approval Review
Agent erstellt 2-seitigen Mail-Entwurf. Berater will in Ruhe lesen, editieren, Korrektur-Grund angeben.
**Heute:** FA-25 sagt "Inline-Buttons" — aber *wo* wird editiert? **Nötig:** Review-Oberfläche im Cockpit.

### 6.3 Task-Erstellung mit Agent-Parametern
Berater erstellt Task mit: Assignee (Agent), LLM (Claude), Datenklasse (internal), Autonomie (L1), Output-Ziel, Deadline.
**Heute:** Nur per Telegram-Freitext denkbar. **Nötig:** Strukturiertes Task-Creation-Formular.

### 6.4 Wochenplanung als Co-Pilot-Dialog
Montagmorgen: Agent zeigt neue, überfällige, wiederkehrende Tasks + SIGNA-Signale. Berater priorisiert. Agent schlägt vor.
**Heute:** Szenario A im Pflichtenheft beschreibt das "Was", aber nicht das "Wo". **Nötig:** Planning-View im Cockpit.

### 6.5 Konversations-Kontext auf Tasks
Telegram-Diskussion soll als Task mit Kontext gespeichert werden.
**Heute:** Telegram-History und Tasks sind getrennte Welten. **Nötig:** Task-Erstellung aus Conversation (nanobot → PostgreSQL → Cockpit).

### 6.6 Memory-Inspektion und -Korrektur
Berater prüft, was Agent über Kunde X weiss. Korrigiert falsche Annahme.
**Heute:** "MEMORY.md in Obsidian öffnen". **Nötig:** Memory-Browser im Cockpit mit Edit-Funktion.

---

## 7. Perspektive: Wohin entwickelt sich das Feld?

### Protokoll-Konvergenz

| Protokoll | Fokus | Prognose 2028 |
|-----------|-------|-------------|
| **MCP** (Anthropic → Linux Foundation) | Agent ↔ Tool/Context | De-facto-Standard. 110M+ SDK-Downloads/Monat. Roadmap: Long-Running Tasks + Agentic Communication |
| **A2A** (Google) | Agent ↔ Agent (Cross-Platform) | Hoch — Google-Ökosystem zieht |
| **ACP** (IBM/BeeAI) | Enterprise-Messaging, Async | Mittel — Enterprise-Nische |

**Für TaskPilot relevant:** MCP bleibt der richtige Standard für Tool-Integration. A2A wird erst relevant, wenn TaskPilot mit externen Agent-Systemen kommunizieren muss.

### Konvergenz Chat ↔ Task-Board

Beide Research-Berichte sagen: **Die Grenze zwischen Chat und Task-Board wird verschwinden.** Slack's agentic-first-Repositionierung (März 2026) zeigt das Zielbild: Agents als @-Teammates in Channels, die Tasks erstellen, Approvals einholen und Workflows auslösen.

Für TaskPilot: Telegram bleibt das mobile Interface, aber das Cockpit wird die primäre Steueroberfläche. Beide sind Fenster in denselben State (PostgreSQL).

### Von Coding-Agents zu General-Purpose-Agents (2027+)

Die aktuelle Welle (Multica, Vibe Kanban, Cline Kanban) fokussiert auf Coding. Die nächste Welle bringt Agents in **nicht-Code-Aufgaben**: Research, Dokumente, Mail, Admin. **Das ist genau TaskPilots Spielfeld.** Ein eigenes Cockpit positioniert TaskPilot als Early Mover in dieser Kategorie.

---

## 8. Empfehlung

### Die alten Zöpfe abschneiden

**Der Backend-Bake-Off (MeisterTask vs. Plane vs. Vikunja) wird ersatzlos gestrichen.** Keines dieser Systeme löst das richtige Problem. Stattdessen:

### Neuer Ansatz: Eigenes agentisches Cockpit + nanobot

```
[Telegram]              ← Mobile HITL, Quick-Capture, Notifications
     ↕
[nanobot AgentLoop]     ← Agent-Runtime, Skill-Execution, MCP-Client
     ↕
[PostgreSQL + pgvector] ← Task-State, Memory, Audit-Log, Embeddings
     ↕
[TaskPilot Cockpit]     ← Web-UI: Inbox, Agent-Queue, Planning, Approval-Review, Memory
     ↕
[LiteLLM Proxy]         ← LLM-Routing (Ollama lokal / Cloud)
     ↕
[MCP-Server-Layer]      ← Mail, Filesystem, SIGNA, bestehende Python-Scripts
```

### Warum das der richtige Weg ist

1. **PostgreSQL ist ohnehin im Stack.** Task-State, Agent-Jobs, Audit-Log, Memory — alles soll dort landen. Ein eigenes Cockpit liest direkt daraus. Kein Adapter-Pattern, kein Sync-Problem.

2. **Die Board-Oberfläche ist trivial.** Ein Kanban-Board mit Drag-and-Drop, Task-Karten mit Agent-Status, eine Inbox-Liste — das ist mit Next.js + Tailwind + Claude Code/Cursor in Tagen baubar. Der Komplexitätskern liegt im Agent-Backend, nicht im UI.

3. **Alles passt von Anfang an.** Agent-Lifecycle (created → running → awaiting-approval → completed/failed), LLM-Override, Autonomie-Stufen (L0–L3), Memory-Badges, Kosten-Tracking — alles nativ, weil es kein adaptiertes Fremd-System ist.

4. **Kein Vendor-Lock-in, keine API-Limitierungen.** PostgreSQL + nanobot + eigenes UI = 100% Kontrolle.

5. **Lernprojekt-Charakter.** Ein agentisches Cockpit zu bauen = "Agentic UI" zu lernen. Das ist genau der Knowledge-Gewinn, den das Projekt bringen soll. Und es ist ein deutlich stärkeres Demo-Asset für Kunden als "ich habe MeisterTask an einen Bot angeschlossen".

6. **MeisterTask bleibt als Safety Net.** Bis das Cockpit die Cross-Project-Planung vollständig abdeckt, läuft MeisterTask parallel weiter. Kein harter Bruch.

### Phase-0-Auswirkung (vorläufig)

| Alt (Pflichtenheft v0.8) | Neu (Empfehlung) |
|--------------------------|-------------------|
| AP-0.4: Backend-Bake-Off (MeisterTask/Plane/Vikunja, ~7.5h) | **Ersetzt durch:** AP-0.4-neu: Cockpit-Skeleton-Spike (Next.js + PostgreSQL + Task-Schema, ~4h) |
| FA-5: Backend-Adapter-Pattern | **Entfällt:** Kein Adapter nötig, direkter DB-Zugriff |
| FA-1 bis FA-6: Kanban-Kern-Anforderungen (abhängig vom Backend) | **Vereinfacht:** Eigene Implementierung, genau passend, kein Kompromiss |

### Inspirationsquellen (nicht als Basis, sondern als Design-Referenz)

| Quelle | Was wir daraus mitnehmen |
|--------|------------------------|
| **Mission Control** | Agent Crew Pattern, Inbox/Decisions-Queue, `/daily-plan`-Workflow, Spend-Limits, Loop-Detection |
| **Multica** | Agent-als-Teammate-UI, Task-Lifecycle-States, Skills-System, WebSocket-Streaming |
| **Veritas Kanban** | YAML-Workflow-Pipelines mit Gates, Approval-Stufen |
| **AgentBoard** | 6-Status-Lifecycle (draft → review → approved → in_progress → done → accepted) |
| **Fuselab Agent UX** | 5 Pflicht-UI-Elemente: Planning Visibility, Tool-Use Disclosure, Memory Surfacing, Multi-Step Tracking, Recovery Routing |
| **Cordum HITL Patterns** | 5 Approval-Patterns: Pre-execution Gate, Exception Escalation, Graduated Autonomy, Sampled Audit, Checkpoint |

---

## 9. Deep Research Prompt (aktualisiert)

Für eine vertiefte Recherche zu spezifischen Aspekten des Cockpit-Baus:

```
Kontext: Ich baue ein "TaskPilot Cockpit" — eine purpose-built Web-UI für
die Zusammenarbeit eines Solo-IT-Beraters mit seinem AI-Agenten (nanobot).
Das Cockpit ist KEIN klassisches Kanban-Board, sondern ein agentisches
Command Center mit: Unified Inbox, Agent-Queue mit Live-Status, 
Cross-Project-Planung, Rich Approval Review, Memory-Dashboard.

Stack: Next.js (oder Svelte) + PostgreSQL + pgvector + Tailwind.
Der Agent (nanobot) kommuniziert via MCP und schreibt in PostgreSQL.
Das Cockpit liest aus PostgreSQL und bietet die UI.

Bitte recherchiere:

1. **Datenmodell:** Wie sieht ein gutes PostgreSQL-Schema für einen
   agentischen Task-Lifecycle aus? (Tasks, Agent-Jobs, Approvals, 
   Memory-Entries, Cost-Log). Gibt es Open-Source-Referenzen?

2. **Real-Time-UI:** Wie implementiert man effizient Live-Updates
   (Agent-Fortschritt, neue Tasks, Status-Änderungen) in Next.js?
   WebSocket vs. SSE vs. Polling. Welche Libraries sind 2026 Standard?

3. **Approval-Review-Patterns:** Wie gestaltet man eine Review-Oberfläche
   für unterschiedliche Content-Typen (Mail-Entwurf, Markdown-Dokument,
   Checkliste, Code)? Best Practices aus Code-Review-Tools (GitHub PR
   Review, Linear) übertragbar auf Agent-Output-Review?

4. **Memory-UI:** Wie visualisiert man Agent-Memory für den Benutzer?
   Beispiele für "Memory Browser" / "Knowledge Inspector" in existierenden
   Agent-Systemen? Inline-Memory-Badges als UI-Pattern?

5. **Mission Control Deep-Dive:** Details zur Architektur von 
   github.com/MeisnerDan/mission-control — wie funktioniert der Agent-Loop,
   das Decisions-Queue-Pattern, die Spend-Limits-Implementierung?
   Was ist übertragbar auf einen PostgreSQL-basierten Stack?
```

---

## Anhang: Referenzen

### Verifizierte Projekte (mindestens eine Research-Quelle bestätigt)

| Projekt | URL | Relevanz | Verifiziert durch |
|---------|-----|----------|-------------------|
| Mission Control | github.com/MeisnerDan/mission-control | Design-Referenz #1: Agent-First, Solo-Operator | Perplexity |
| Multica | github.com/multica-ai/multica | Design-Referenz: Agents-als-Teammates-UI | Gemini (Perplexity: nicht verifizierbar) |
| Vibe Kanban (BloopAI) | — | Architektur-Referenz: Git-Worktree-Isolation | Perplexity |
| Cline Kanban | — | Architektur-Referenz: Dependency-Chaining | Perplexity |
| Veritas Kanban | github.com/BradGroux/veritas-kanban | Design-Referenz: YAML-Pipelines, Gates | Gemini |
| Huly | github.com/hcengineering/platform | Referenz: Unified Inbox (Mail + Chat + Docs) | Beide |
| Plane CE | github.com/makeplane/plane | Referenz: MCP-Server-Pattern | Perplexity |
| nanobot (HKUDS) | github.com/HKUDS/nanobot | Gewählte Agent-Runtime | Eigene Verifikation |
| Langfuse | github.com/langfuse/langfuse | Observability (Cost, Latency, State) | Perplexity |
| Mem0 | github.com/mem0ai/mem0 | Memory-Layer (~48K Stars, pgvector-kompatibel) | Perplexity |

### Nicht verifizierbare Projekte (Vorsicht)

| Projekt | Quelle | Status |
|---------|--------|--------|
| Symio | Eigene Recherche + Gemini | Perplexity kann nicht bestätigen |
| AgentBoard | Eigene Recherche | Perplexity kann nicht bestätigen |
| kandev | Eigene Recherche | Perplexity kann nicht bestätigen |
| nanobot.ai | Perplexity | Nicht dasselbe wie HKUDS/nanobot — separat zu prüfen |
