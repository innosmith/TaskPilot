# Research-Prompts für TaskPilot (Deep Research)

> **Ausgelagert aus Pflichtenheft v0.3.1 → v0.4 (24. April 2026)**
> Diese Prompts wurden aus dem Pflichtenheft entfernt, um es auf den Kern zu fokussieren. Die meisten Recherchen sind bereits durchgeführt — die Prompts dienen als Referenz für künftige Vertiefungen.
> 
> **Status:** Grösstenteils abgearbeitet. Ergebnisse: siehe `docs/research/research-erkenntnisse.md` und die Gemini-/Perplexity-Drittmeinungen (extern zugestellt, nicht im Repo).

---

## 17. Research-Prompts für Perplexity / Gemini

Diese Sektion enthält **Deep-Research-Prompts**, die für ergiebige Antworten auf Tools wie [Perplexity Pro / Deep Research](https://www.perplexity.ai/), [Google Gemini Deep Research](https://gemini.google.com/), [ChatGPT Deep Research](https://openai.com/index/introducing-deep-research/), Claude (mit Web-Search) oder vergleichbare Recherche-Agenten optimiert sind.

### 17.0 Verwendungs-Hinweise & gemeinsame Vorlage

#### Vorgehen

1. **Vor jedem Prompt prüfen:** Datum (aktuell `April 2026`), eigene InnoSmith-Constraints (Hardware, Stack, Budget) sowie evtl. zwischenzeitlich aktualisierte Annahmen.
2. **Tool-Wahl pro Prompt:**
   - **Perplexity Deep Research** für Marktvergleiche, Tool-Landscapes, Reife-Einschätzungen.
   - **Gemini Deep Research** für lange, mehrstufige Berichte mit vielen Quellen.
   - **ChatGPT Deep Research** für tiefe technische Synthesen (gut bei Code-Patterns).
   - **Claude (Sonnet 4.6 / Opus 4.7) mit Web-Search** für nuancierte Architektur-Empfehlungen.
3. **Cross-Validation:** Mindestens zwei Tools pro Prompt, Ergebnisse triangulieren.
4. **Iterations-Pattern:** Erst breite Antwort einholen, dann gezielt nachhaken (Follow-up-Prompts in jeder Sektion vorgeschlagen).
5. **Resultat ins Pflichtenheft zurückführen:** ADR (Architecture Decision Record) pro getroffener Entscheidung im neuen Verzeichnis `docs/adr/`.

#### Master-Template (Bausteine, die jeder Prompt verwendet)

```text
# ROLLE
Du bist [Senior Solutions Architect / Privacy Engineer / ML Infrastructure Lead]
mit X+ Jahren Erfahrung in [Domäne]. Du arbeitest evidenzbasiert, zitierst
Primärquellen, kennzeichnest Spekulation klar und vermeidest Vendor-Bias.

# MISSION
[Ein Satz: Was soll am Ende dieser Recherche entschieden werden können?]

# STRATEGISCHER KONTEXT
- Projekt: InnoSmith TaskPilot — siehe Pflichtenheft v0.1
- Nutzungsprofil, Hardware, Datenschutz-Constraints, Phase, Budget

# RECHERCHE-FRAGEN (gewichtet)
1. [Hauptfrage 1] (Gewicht: 25%)
   1.1 Sub-Frage
   1.2 Sub-Frage
2. [Hauptfrage 2] (Gewicht: 20%)
...

# BEWERTUNGSKRITERIEN
[Liste mit Gewichtung in %]

# ANTI-ANFORDERUNGEN (NICHT relevant)
[Liste, was bewusst ausgeklammert ist]

# QUELLEN-ANFORDERUNGEN
- Primärquellen bevorzugt (Doku, Repos, Specs, Studien)
- Aktualität: Veröffentlichungen ab Q4 2024, idealerweise 2025/2026
- Versions-Aktualität explizit nennen
- Bei widersprüchlichen Quellen: Diskrepanz benennen
- Vendor-Pages mit Bias-Disclaimer behandeln

# OUTPUT-FORMAT
- Sprache: Deutsch (technische Fachbegriffe Englisch belassen)
- Länge: ca. X Wörter
- Pflicht-Sektionen: [Liste]
- Tabellen wo Vergleich, Mermaid-Diagramme wo Architektur
- Pro Empfehlung: Pro/Contra, Risiken, Reversibilität, Migrationskosten

# VALIDIERUNG
- Self-Check am Ende: Was ist unsicher? Was sollte nochmals verifiziert werden?
- Liste der Quellen mit Zugriffsdatum

# FOLLOW-UP-VORSCHLAG
- 2-3 weiterführende Recherche-Fragen, die sich aus dem Ergebnis ergeben würden
```

---

### 17.1 OSS-Kanban-Stack als UI-Basis (V4-Hybrid-Architektur)

```text
# ROLLE
Du bist Senior Solutions Architect mit 10+ Jahren Erfahrung in Self-Hosted-
Productivity-Tools, Kanban-Systemen und Open-Source-Bewertung. Du hast bereits
mehrere Migrationen von SaaS-PM-Tools auf self-hosted Lösungen begleitet.
Du argumentierst evidenzbasiert mit GitHub-Aktivität, Release-Cadenz, Issue-
Halbwertszeit und produktiven Deployments.

# MISSION
Empfehle EINE primäre und EINE Backup-OSS-Kanban-/Task-Management-Lösung als
UI-Basis für InnoSmith TaskPilot, die ich in den nächsten 4 Wochen produktiv
self-hosten und um eine eigene Agent-Schicht plus Cross-Project-Cockpit
erweitern kann.

# STRATEGISCHER KONTEXT
- Projekt: InnoSmith TaskPilot, V4-Hybrid-Architektur (siehe Pflichtenheft Sektion 9.5):
  OSS-Kanban-UI + entkoppelter Agent-Layer + Custom-Cockpit für Cross-Project-Sicht.
- Ablöse-Ziel: MeisterTask (gehostet in DE, langjähriger Einsatz) für einen
  Berater mit 10–14 parallel laufenden Projekten und teilweise kundenseitigem
  Board-Zugriff.
- Heutige Kern-Workflows: Wöchentliche Planung über alle Projekte hinweg in einer
  Cross-Project-Pipeline mit Spalten "Focus / This Week / Next Week / Waiting /
  This Month / Next Month / Beyond"; Recurring-Tasks mit Vorlagen-Checklisten;
  E-Mail-zu-Task-Capture aktuell manuell; Mobile primär per Self-Mail.
- Hosting: Single-Host (Linux), Docker Compose. Phase 4 später Mandantenfähigkeit
  bei Kundeninstanzen (PostgreSQL Row-Level-Security oder Schema-per-Tenant).
- Erweiterungsstrategie: Wir bauen kein UI-Fork, sondern (a) konsumieren die OSS-
  Kanban-Lösung über REST/GraphQL/Webhooks und (b) bauen ein eigenes Next.js-
  Cockpit daneben für Cross-Project-Sicht, Daily Briefing, Agent-Console.
- Datenschutz: revDSG/DSGVO, EU-Hosting Pflicht, eigene PostgreSQL-Instanz.

# RECHERCHE-FRAGEN (gewichtet)
1. (25%) **Reife & Lebendigkeit der Kandidaten** im Zeitraum Q4 2024 – Q2 2026:
   1.1 Release-Cadenz, letzte Major-Versionen, Breaking-Change-Frequenz.
   1.2 GitHub-Metriken: Contributors/Monat, Issue-Median-Time-to-Close, Stars-Trend.
   1.3 Kommerzielle Trägerschaft vs. Community-Only — Ausfallrisiko in 24 Monaten.
2. (20%) **API- und Integrations-Reife** für die Agent-Anbindung:
   2.1 REST-/GraphQL-Coverage (Boards, Cards, Comments, Attachments, Permissions).
   2.2 Webhook-Events (Card-Move, Comment-Created, Member-Changed) — Vollständigkeit?
   2.3 Existiert ein offizieller MCP-Server oder eine Roadmap dafür?
   2.4 Rate-Limits, Auth-Modelle (API-Token, OAuth2), Bulk-Operationen.
3. (15%) **Datenmodell- und Erweiterungs-Eignung** für Cross-Project-Cockpit:
   3.1 Wie wird "Workspace > Project > Board > Column > Card" intern modelliert?
   3.2 Cross-Board-Queries: nativ unterstützt oder per External-DB-Mirror nötig?
   3.3 Custom-Fields, Custom-Views, Plugin-/Extension-System.
4. (15%) **Recurring-Tasks**: Native Support, Cron-Expressivität, Vorlagen-Checklisten,
   Skip-Logik, Reaktion bei Scheduler-Ausfall (Backfill?).
5. (10%) **Berechtigungs- und Mandantenmodell**:
   5.1 Granularität (Workspace/Board/Card-Ebene).
   5.2 Multi-Tenant-Isolation (separate Schemas, RLS, Tenant-aware-Queries).
   5.3 SSO/OIDC-Tauglichkeit für spätere Kundeninstanzen.
6. (10%) **Self-Hosting-Realität**:
   6.1 Docker-Compose-Quickstart-Qualität, Backup/Restore-Verfahren.
   6.2 PostgreSQL- vs. SQLite-Backend, Skalierungsoptionen.
   6.3 Update-Pfad (Migrations-Sicherheit), Beobachtbarkeit (Logs, Health, Metrics).
7. (5%) **Lizenz & kommerzielle Nutzung** im InnoSmith-Whitelabel-Kontext:
   AGPL/MIT/Apache/BSL/SSPL — was bedeutet das für Kundeninstanzen mit InnoSmith-Branding?

# KANDIDATEN
Bitte mindestens diese vergleichen, gerne weitere relevante hinzufügen:
Vikunja, Plane, Planka, Kanboard, Wekan, OpenProject, AppFlowy, Focalboard,
Leantime, Taiga, NocoDB-basierte Lösungen.

# BEWERTUNGSKRITERIEN
| Kriterium | Gewicht |
|---|---|
| API-Vollständigkeit & Webhook-Reife | 25% |
| Cross-Project-Sicht (nativ oder einfach extern baubar) | 15% |
| Recurring-Tasks-Reife (vergleich MeisterTask) | 15% |
| Self-Hosting-Reife & Backup-Story | 15% |
| Community-Aktivität & 24-Monats-Stabilität | 10% |
| Multi-Tenant-Tauglichkeit (Phase 4) | 10% |
| Lizenz für Whitelabel-Kundenangebot | 10% |

# ANTI-ANFORDERUNGEN
- Keine reinen SaaS-Lösungen (Trello, Linear, Notion, Monday, ClickUp ausschliessen).
- Keine reinen Time-Tracking- oder Gantt-Tools, kein Vollwert-PM-Suite-Zwang.
- Kein Bewertungsfokus auf Mobile-Apps (geringe Priorität für TaskPilot).
- Keine Tools, die nur als Cloud verfügbar sind, auch wenn "Self-Hosted Enterprise" beworben wird, ohne dass dies offen verfügbar ist.

# QUELLEN-ANFORDERUNGEN
- Primär: Offizielle Repos, Release-Notes, API-Dokus, Architektur-Pages.
- Sekundär: Awesome-Lists (z.B. awesome-selfhosted), Reddit r/selfhosted (mit Bias-Filter).
- Vergleichs-Reviews 2025/2026 (Heise, c't, LWN, t3n, alternativeto.net mit Vorbehalt).
- GitHub-Metriken über offizielle GitHub-API, nicht aus Drittquellen.
- Falls eine Quelle vor Q4 2024 ist, explizit kennzeichnen und Aktualität verifizieren.

# OUTPUT-FORMAT
- Sprache: Deutsch, Tooling-Begriffe auf Englisch.
- Länge: 2'500–4'000 Wörter.
- Pflicht-Sektionen:
  1. Executive Summary (Top-Empfehlung + Backup, je 3 Sätze Begründung).
  2. Methodik & Quellenlage.
  3. Vergleichstabelle aller Kandidaten (alle 7 Kriterien als Spalten, 1–5 Sterne).
  4. Tiefenprofil pro Top-3-Kandidat (je ca. 400 Wörter): Stärken, Schwächen, Risiken, konkrete Versionen, kritische Issues der letzten 12 Monate.
  5. Empfehlung mit Migrations-/Erweiterungsplan (4-Wochen-Setup-Skizze).
  6. Risiko-Register (mit Eintrittswahrscheinlichkeit & Mitigations-Vorschlag).
  7. Quellenliste mit Zugriffsdatum.
  8. Self-Check (Was sollte ich noch verifizieren?).

# VALIDIERUNG
- Pro Tool: Jüngste stabile Version + Release-Datum nennen.
- Bei Aussagen zu API-Coverage konkrete Doku-URLs.
- Wenn ein Tool als "tot/stagnierend" eingestuft wird: Beleg über Commit-Aktivität.

# FOLLOW-UP-VORSCHLAG
Schlage 2–3 vertiefende Recherche-Fragen vor, z.B. zu Migrations-Tooling von
MeisterTask zur empfohlenen Lösung oder zu Real-User-Reports der Top-Wahl in
Beratungs-/Multi-Projekt-Settings.
```

---

### 17.2 Agent-Frameworks & Orchestrierung 2026 (Stack für Agent-Layer)

```text
# ROLLE
Du bist Senior AI/ML Engineering Lead mit Schwerpunkt agentic systems,
Multi-LLM-Orchestrierung und produktiven Personal-Assistant-Architekturen.
Du hast LangGraph, CrewAI, AutoGen und vergleichbare Frameworks bereits in
produktiven Systemen verglichen und kennst typische Failure-Modes.

# MISSION
Empfehle einen konkreten Agent-Framework-Stack (Orchestrator + Memory-Backbone +
Tool-Layer) für TaskPilots Agent-Engine, der lokal auf Asus GX10 sowie hybrid
mit Cloud-LLMs lauffähig ist und unsere Lernfähigkeits-Anforderungen aus
Pflichtenheft-Sektion 7 erfüllt.

# STRATEGISCHER KONTEXT
- Personal-Productivity-Agent für einen Berater (siehe Pflichtenheft).
- Stack-Constraints:
  - Python bevorzugt (Berater hat starke Python-Erfahrung, InnoSmith-AI-Lösungen
    laufen primär in Python).
  - LLM-Routing zwingend Multi-Provider: lokal vLLM/Ollama auf Asus GX10
    (Llama 3.3, Qwen 2.5), Hostinger als Mittelweg, Cloud (Anthropic Opus 4.7,
    Google Gemini 2.5, OpenAI GPT-5).
  - Datenschutz: Mandantendaten dürfen niemals in Cloud-LLMs für Lernen einfliessen.
  - MCP-Server-Pattern als zentrale Tool-Integration (TaskPilot ist MCP-Client UND -Server).
- Lernfähigkeits-Anforderungen (siehe Pflichtenheft Sektion 7):
  Episodic + Semantic + Procedural Memory, Reflection-Loops (daily/weekly/monthly),
  Few-Shot-Library mit Kuration, User-Feedback-Loop, Anti-Pattern-Detector,
  optional LoRA-Fine-Tuning lokaler Modelle Phase 5.
- Workflow-Charakteristik: viele kurze Agent-Jobs (Mail-Triage, Klassifikation,
  Vorschläge) plus seltene lange Workflows (Recherche, Wochen-Review).
- Production-Reife wichtig: lange-laufender Single-User-Service mit Aussicht auf
  Multi-Tenant Phase 4.

# RECHERCHE-FRAGEN (gewichtet)
1. (25%) **Orchestrator-Vergleich** (LangGraph, CrewAI, AutoGen v0.4+, Pydantic AI,
   Inngest Agent Kit, Restack, Temporal-basierte Eigenbau, Claude Code SDK):
   1.1 Stateful-Workflow-Modelle, Recovery nach Crash, Persistenz von Zwischenständen.
   1.2 Multi-LLM-Routing nativ vs. Wrapper nötig.
   1.3 Tool-Use- und MCP-Integration (Client/Host).
   1.4 Observability/Tracing (LangSmith, Langfuse, eigene OTel-Hooks).
   1.5 Production-Reife: Versionsstabilität, Breaking Changes, Enterprise-Adoption.
2. (20%) **Memory-Layer-Vergleich** (Letta/MemGPT, Mem0, Zep, Cognee,
   pgvector + eigene Reflexion-Implementierung, Graphiti):
   2.1 Episodic vs. Semantic vs. Procedural Memory — Out-of-the-Box-Modellierung.
   2.2 Memory-Compaction & Forgetting-Strategien.
   2.3 Privacy-Hooks (Per-User-Forget, Multi-Tenant-Isolation).
   2.4 Skalierung bei tausenden Memory-Items über 12+ Monate.
3. (15%) **Optimaler kombinierter Stack** für TaskPilots Phase-1-Anforderungen:
   konkrete Empfehlung mit Begründung warum diese Kombination, was mit was kommuniziert,
   wo Anti-Pattern lauern.
4. (10%) **Reflection-/Self-Improvement-Patterns** in den Frameworks:
   Welche unterstützen native Reflexion (z.B. Reflexion-Paper-Pattern), welche
   erfordern Eigenimplementierung?
5. (10%) **Lokale-LLM-Tauglichkeit**: Welche Frameworks haben First-Class-Support
   für OpenAI-kompatible lokale Endpoints (vLLM, Ollama)? Wo gibt es Bugs/Friction?
6. (10%) **MCP-Reife im Framework**: Native MCP-Client-Implementation, MCP-Server-
   Bauen aus Skills heraus, Auth-Patterns.
7. (10%) **Langzeit-Risiken**: Welche Frameworks haben Anzeichen von Stagnation oder
   Re-Architecture? Welche haben starke 24-Monats-Wetten (Anthropic-, Google-,
   Microsoft-, Community-getragen)?

# BEWERTUNGSKRITERIEN
| Kriterium | Gewicht |
|---|---|
| Production-Readiness & Stabilität (12-Monats-Track-Record) | 20% |
| Multi-LLM-Routing-Tauglichkeit (lokal + Cloud nahtlos) | 20% |
| Memory-Architektur-Qualität für Lernfähigkeit | 20% |
| MCP-Integration (Client + Server) | 10% |
| Observability & Debugging | 10% |
| Lernkurve & Dokumentationsqualität | 10% |
| Lizenz & Vendor-Lock-in-Risiko | 10% |

# ANTI-ANFORDERUNGEN
- Keine reinen LLM-Wrapper ohne Workflow-/Memory-Schicht (z.B. nicht reines
  litellm-only).
- Keine No-Code-Agent-Builder (Flowise, Langflow, Dify) — wir wollen Code.
- Keine Frameworks ohne Python-First-Support (also kein primär-Java/Go-only).
- Keine reinen Multi-Agent-Conversation-Spielwiesen ohne Production-Story.

# QUELLEN-ANFORDERUNGEN
- Offizielle Doku, GitHub-Repos, Release-Notes, ADRs der Frameworks.
- Vergleichs-Posts der Hersteller (mit Bias-Filter), unabhängige Benchmarks.
- Veröffentlichte Erfahrungsberichte (Talks, Blog-Posts, Case-Studies) ab Q3 2025.
- Akademische Quellen für Reflexion-/Memory-Patterns: arxiv.org Papers
  (Reflexion 2303.11366, Generative Agents 2304.03442, MemGPT 2310.08560 u.a.).

# OUTPUT-FORMAT
- Sprache: Deutsch.
- Länge: 3'000–4'500 Wörter.
- Pflicht-Sektionen:
  1. Executive Summary (1 empfohlener Stack mit Bullet-Begründung, Alternativen).
  2. Vergleichstabelle Orchestratoren (alle Kriterien als Spalten).
  3. Vergleichstabelle Memory-Layer.
  4. Tiefenprofile (je 300–500 Wörter) für Top-2 Orchestratoren und Top-2 Memory-Layer.
  5. Empfohlene Stack-Kombination als Mermaid-Diagramm + Code-Skeleton-Pseudocode.
  6. Failure-Modes & Mitigation (typische Probleme + Gegenmaßnahmen).
  7. Migrationspfad falls wir später wechseln müssen (Lock-in-Analyse).
  8. Quellenliste + Self-Check.

# VALIDIERUNG
- Aktuelle Versionen aller Frameworks mit Release-Datum.
- Pro Stack-Empfehlung: konkretes Beispiel-Repo oder Case-Study aus 2025/2026.
- Bei strittigen Aussagen: zwei unabhängige Quellen.

# FOLLOW-UP-VORSCHLAG
- Vertiefung "Bewertung LangSmith vs. Langfuse als Tracing-Backend".
- Vertiefung "Code-Patterns für Reflection-Loops in [empfohlener Stack]".
```

---

### 17.3 Microsoft 365 Copilot vs. Custom Agent — Strategische Aufteilung

```text
# ROLLE
Du bist Senior Microsoft-365-Architekt mit tiefer Kenntnis von Microsoft Graph,
Copilot Studio, Power Platform, sowie konkreter Erfahrung in Custom-Agent-
Integrationen für KMU mit Datenschutzfokus DACH.

# MISSION
Liefere eine klare, evidenzbasierte Aufteilung "Was übernehmen wir mit
M365-Copilot / Microsoft-Stack, was bauen wir custom mit TaskPilot?" für
Mail-Triage, Task-Extraktion (Phase 1) und Mail-Verfassen mit Approval-Gates
(Phase 3).

# STRATEGISCHER KONTEXT
- M365 ist im produktiven Einsatz (E3 oder E5 — bitte beide Szenarien betrachten),
  Copilot-Lizenz vorhanden.
- TaskPilot ist Custom-Agent (Python, lokal/hybrid LLM-Routing). Wir wollen
  nicht doppelt bauen, was Microsoft besser macht — und wir wollen nicht in
  Copilot-Limits laufen, wo Custom-Lösung überlegen ist.
- Ziel ist InnoSmith-Berater-Setup; relevant aber auch das Wissen für Kunden,
  die in vergleichbarer M365-Welt leben.
- Datenschutz: revDSG/DSGVO, Mandantendaten möglichst lokal (Routing-Policy),
  M365 Tenant-Region EU/CH bevorzugt.
- Wir wollen langfristig nicht abhängig vom Microsoft-Stack sein — TaskPilot
  muss auch ohne M365-Copilot lauffähig bleiben.

# RECHERCHE-FRAGEN (gewichtet)
1. (25%) **Was leistet M365-Copilot für Mail-Workflows (Stand April 2026)?**
   1.1 Outlook-Copilot-Funktionen (Zusammenfassen, Entwürfe, Antworten,
       Aktionspunkte-Extraktion) — konkret und limitierbar.
   1.2 Copilot-Agent-Möglichkeiten (Copilot Studio, Custom Agents, Connectors).
   1.3 Lizenzpflichten & Kostenmodelle 2026 (Copilot for M365, Copilot Pro,
       Copilot Studio Capacity-Pricing, MCS-Capacity).
2. (20%) **Microsoft Graph als Schnittstelle für Custom-Agents:**
   2.1 Mail-API (Lesen, Filter, Webhooks/Subscriptions, Change-Notifications).
   2.2 Calendar-API (für RAG-Kontext).
   2.3 OneDrive/SharePoint-API (Dokumente als Wissensquelle).
   2.4 Throttling, App-Registration, OAuth2-Flows, Berechtigungs-Scopes
       (Delegated vs. Application).
   2.5 Webhook-/Subscription-Lifetimes und Renewal-Patterns.
3. (15%) **Datenschutz-Implikationen Copilot vs. Custom-Agent:**
   3.1 Wo werden Daten verarbeitet? Microsoft Cloud Region, EU Data Boundary,
       Sovereign Cloud Optionen.
   3.2 Welche Daten werden für Modell-Training genutzt? (M365-Tenant-Daten
       vs. allgemein).
   3.3 Audit-Logs, eDiscovery, Purview-Integration.
   3.4 Risiken bei sensitiven Mandantendaten in Copilot-Verarbeitung.
4. (15%) **Integrations-Patterns Custom-Agent in Outlook/Teams:**
   4.1 Outlook Add-Ins (Web-Add-Ins, Manifest 1.x, Smart-Alerts, Sender-Override).
   4.2 Teams-Apps und Bots, Adaptive Cards für Approval-Anfragen.
   4.3 Copilot Studio Connectors zur Anbindung eines TaskPilot-Backends.
   4.4 Power Automate als Orchestrierungs-Glue (lohnt sich das vs. eigener Service?).
5. (15%) **Konkrete Hybrid-Architektur-Empfehlung** für unseren Use-Case:
   5.1 Welche Layer komplett selbst bauen (Custom-Agent mit eigenem LLM-Routing)?
   5.2 Welche Layer von M365-Copilot konsumieren (z.B. Outlook-Mail-Summary)?
   5.3 Welche Bereiche bewusst doppelt halten (Fallback bei Microsoft-Ausfall)?
6. (10%) **Praxisbeispiele 2025/2026** im DACH-Beratungs-/KMU-Kontext, Lessons
   Learned, dokumentierte Failure-Modes, Compliance-Hinweise.

# BEWERTUNGSKRITERIEN
| Kriterium | Gewicht |
|---|---|
| Datenschutz-Implikationen (revDSG/DSGVO, Daten-Lokation) | 25% |
| Funktionsabdeckung Copilot für unsere konkreten Use-Cases | 20% |
| Langfristige Strategische Lock-in-Risiken | 15% |
| Lizenzkosten & TCO über 24 Monate | 15% |
| Custom-Integration-Aufwand für die jeweilige Schicht | 15% |
| Audit-/Compliance-Tauglichkeit (Phase 4 Mandantenfähigkeit) | 10% |

# ANTI-ANFORDERUNGEN
- Keine generischen Marketing-Aussagen zu Copilot — bitte konkrete API-Endpoints,
  Quotas, Preise.
- Keine Empfehlungen, die ohne Custom-Code auskommen sollen (No-Code Power
  Automate Only) — wir bauen Custom-Code.
- Keine reinen Microsoft-internen Tools (z.B. nur Sales Copilot ohne Bezug zu
  unserem Use-Case).

# QUELLEN-ANFORDERUNGEN
- Microsoft Learn (learn.microsoft.com) als Primärquelle.
- Microsoft Tech Community Posts ab Q3 2025.
- Roadmap-Items im Microsoft 365 Roadmap-Tool (mit Stand-Datum).
- Unabhängige Reviews (Tony Redmond, Practical 365, Computer Weekly, c't).
- DACH-Datenschutzanalysen (z.B. Bundesbeauftragter, EDÖB-Stellungnahmen).

# OUTPUT-FORMAT
- Sprache: Deutsch.
- Länge: 2'500–3'500 Wörter.
- Pflicht-Sektionen:
  1. Executive Summary (Hybrid-Empfehlung in 5 Bullets).
  2. Was Copilot heute (April 2026) konkret leistet (mit Versions-/Plan-Zuordnung).
  3. Was Microsoft Graph für Custom-Agents bietet (API-Tabelle).
  4. Datenschutz-Matrix (welche Verarbeitung wo).
  5. Empfohlene Schichtung (welche Layer Microsoft, welche Custom).
  6. Lizenz-/TCO-Vergleich für 24 Monate (typischer Berater-Fall).
  7. Risiken & Mitigations.
  8. Quellenliste + Self-Check.

# VALIDIERUNG
- Pro Funktion: Verfügbar in welchem Lizenzplan ab welchem Datum?
- Pro API: Aktueller Endpoint-Stand, Throttling-Limits, Auth-Mode.
- Datenschutz-Aussagen mit Microsoft-EU-Data-Boundary-Doku-Verweis.

# FOLLOW-UP-VORSCHLAG
- Vertiefung "Outlook Add-In als TaskPilot-Frontend für Approval-UI".
- Vertiefung "Microsoft Graph Webhook-Stabilität — Workarounds für Subscription-Renewals".
```

---

### 17.4 Lokales LLM-Hosting Asus GX10 — Inferenz-Stack & Modellwahl

```text
# ROLLE
Du bist Senior ML Infrastructure Engineer mit Tiefenexpertise in NVIDIA-basiertem
LLM-Serving (vLLM, TensorRT-LLM, SGLang), Quantisierung (AWQ, GPTQ, GGUF) und
deutschsprachigen Open-Source-Modellen. Du kennst die typischen Throughput-/
Latenz-/Qualitäts-Trade-offs und gängige Failure-Modes im Single-Host-Betrieb.

# MISSION
Empfehle einen konkreten Inferenz-Server-Stack PLUS 2–3 lokale LLM-Modelle für
TaskPilots Agent-Layer auf einem Asus GX10 (NVIDIA-basiert, Hardware-Spezifikation
bitte recherchieren und im Antwortteil bestätigen) im Single-User-Setup mit
gelegentlichen Spikes durch Recherche-/Wochen-Review-Tasks.

# STRATEGISCHER KONTEXT
- Hardware: Asus GX10 — bitte exakte aktuelle Spezifikation (GPU-Modell, VRAM,
  RAM, Storage) im Antwortteil zuerst klären; falls mehrere Modellvarianten
  existieren, plausible Annahme machen und kennzeichnen.
- Use-Case-Mix:
  - **Hochfrequent** (mehrmals pro Stunde): Mail-Klassifikation, Intent-Erkennung,
    Task-Extraktion — kurze Inputs, kurze Outputs, Tool-Use-fähig.
  - **Mittelfrequent** (mehrmals pro Tag): Antwort-/Entwurfs-Generation, Vorschläge.
  - **Niederfrequent** (1–3x pro Woche): Wochen-Review mit längeren Synthesen,
    Recherche-Synthese.
- Sprache: primär Deutsch (Geschäftskommunikation Schweiz/DACH), gelegentlich
  Englisch (Tech-Recherche).
- Tool-Use: Modell muss strukturierte Outputs (JSON, Function-Calls) zuverlässig
  liefern.
- Kontextlänge: typisch 8–32k Token, gelegentlich >100k (für Wochen-Review).
- Datenschutz: 100% lokal, kein Outbound für sensitive Mandantendaten.
- Skalierung: vorerst 1 User, Phase 4 evtl. mehrere Mandantenmodelle parallel.

# RECHERCHE-FRAGEN (gewichtet)
1. (10%) **Hardware-Bestätigung Asus GX10**:
   1.1 Welche GPU(s), wie viel VRAM, RAM, Storage? Welche aktuellen Varianten?
   1.2 Energieverbrauch im Inferenz-Betrieb, Geräuschpegel, Treiber-Anforderungen.
2. (20%) **Inferenz-Server-Vergleich** für die identifizierte Hardware:
   2.1 vLLM (PagedAttention, Continuous Batching) — Versionsstand 2026.
   2.2 SGLang (RadixAttention, Structured Outputs) — Reife für Production?
   2.3 TensorRT-LLM (NVIDIA-optimiert) — Wartungsaufwand vs. Performance-Gewinn?
   2.4 Ollama (Convenience, ggml/gguf) — Production-tauglich?
   2.5 llama.cpp / LM Studio — Eignung als Fallback?
   2.6 NIM (NVIDIA Inference Microservices) — Lizenz, Lock-in?
   2.7 Aktuelle Throughput-/Latenz-Benchmarks für Modelle 14B–70B auf vergleichbarer Hardware.
3. (25%) **Modellempfehlung** (April 2026 State-of-the-Art) für deutschsprachigen
   Productivity-Use-Case:
   3.1 Llama 3.3 70B / Llama 4 Familie.
   3.2 Qwen 2.5 / Qwen 3 Familie.
   3.3 Mistral Large 2 / Mistral 3.
   3.4 Gemma 3 / Gemma 4.
   3.5 Spezialisierte deutsche Modelle (DiscoLM, EM German Nachfolger,
       SauerkrautLM-Familie, weitere).
   3.6 Reasoning-Spezialisten (DeepSeek R-Serie, Qwen-QwQ, weitere) — wann sinnvoll
       und mit welchen Trade-offs?
   3.7 Quantisierungs-Empfehlung (AWQ, GPTQ, FP8, INT4) je Modell — Qualitätsverlust messbar?
4. (15%) **Tool-Use-Reliability**:
   4.1 Welches Modell hat die zuverlässigste Function-Call/JSON-Mode-Implementation?
   4.2 Vergleich mit Cloud-Modellen für Tool-Use-Genauigkeit.
   4.3 Mitigation-Patterns wenn lokales Modell schwächer ist (Retry, Schema-Validation, Reasoning-Step).
5. (10%) **Memory-Footprint und Multi-Model-Serving**:
   5.1 Können wir gleichzeitig ein 70B-Hauptmodell und ein 7B-Klassifikationsmodell
       laden? Hot-Swap-Patterns?
   5.2 KV-Cache-Strategien für lange Kontexte.
6. (10%) **Operational Concerns**:
   6.1 Update-Frequenz Modelle/Inferenz-Server, Breaking-Change-Frequenz.
   6.2 Health-Endpoints, Prometheus-Metriken.
   6.3 Restart-Verhalten, Graceful-Shutdown bei Power-Issue.
7. (10%) **Pfad zu LoRA-Fine-Tuning** (Phase 5):
   7.1 Welches Inferenz-Setup unterstützt LoRA-Adapter ohne Server-Restart?
   7.2 Trainings-Tooling-Empfehlung (Axolotl, Unsloth, TRL) für die identifizierte Hardware.

# BEWERTUNGSKRITERIEN
| Kriterium | Gewicht |
|---|---|
| Deutsche Sprachqualität | 20% |
| Tool-Use-Zuverlässigkeit | 20% |
| Throughput für hochfrequente Klassifikations-Tasks | 15% |
| Latenz für interaktive UI-Antworten (<5s) | 15% |
| Operational Robustheit (Updates, Crashes, Monitoring) | 15% |
| LoRA-Tauglichkeit für Phase 5 | 10% |
| Lizenz für kommerziellen Beratungs-Einsatz | 5% |

# ANTI-ANFORDERUNGEN
- Keine reinen Cloud-LLM-Empfehlungen (Use-Case ist explizit lokal).
- Keine experimentellen Modelle ohne Production-Reports.
- Keine Empfehlungen ohne Quantisierungs-Optionen für die Hardware.

# QUELLEN-ANFORDERUNGEN
- HuggingFace Model Cards mit aktuellen Daten.
- Inference-Server-Repos mit Release-Notes.
- Benchmark-Veröffentlichungen (z.B. von Anyscale, Together AI, Artificial Analysis,
  LMSYS, ChatBot Arena, EQ-Bench, German-Benchmarks wie SuperGLEBer, LeoLM-Eval).
- NVIDIA-Developer-Blog für TensorRT-LLM und NIM.
- Reddit r/LocalLLaMA mit Bias-Filter (Diskussionen, aber Quellen prüfen).

# OUTPUT-FORMAT
- Sprache: Deutsch.
- Länge: 3'000–4'000 Wörter.
- Pflicht-Sektionen:
  1. Hardware-Klärung Asus GX10 (mit Annahme-Markern).
  2. Inferenz-Server-Vergleichstabelle inkl. Empfehlung.
  3. Modell-Vergleichstabelle (5–8 Modelle, alle Bewertungskriterien).
  4. Top-3-Modell-Profile mit Konfigurationshinweisen (Quantisierung, Context, Sampling).
  5. Konkrete Stack-Empfehlung mit Docker-Compose-Beispiel-Snippet.
  6. Operational-Runbook-Skizze (Backup Models, Restart-Patterns).
  7. Roadmap LoRA-Fine-Tuning Phase 5.
  8. Quellen + Self-Check.

# VALIDIERUNG
- Konkrete Versionsnummern aller empfohlenen Komponenten.
- Pro Modell: HuggingFace-Repo-Link + Quantisierungs-Variante.
- Wenn Benchmarks zitiert werden: Datum + Konfiguration nennen.

# FOLLOW-UP-VORSCHLAG
- Vertiefung "Latenz-Optimierung für Function-Calling auf [empfohlenem Modell]".
- Vertiefung "LoRA-Trainings-Pipeline für deutsche Productivity-Daten".
```

---

### 17.5 RAG- & Memory-Architektur 2026 für Productivity-Agenten

```text
# ROLLE
Du bist Senior AI Architect mit Fokus auf Retrieval-Systeme und stateful Agents.
Du kennst die Diskussion "klassisches RAG vs. Long-Context", die neuen Memory-
Frameworks (Letta, Mem0, Zep, Cognee, Graphiti) und hast in 2025/2026 mehrere
produktive Personal-Agent-Memory-Stacks gebaut.

# MISSION
Empfehle eine konkrete RAG-/Memory-Architektur für TaskPilot, die Mails, Tasks,
Kommentare, Notizen, eine externe News-DB und perspektivisch OneDrive-/SharePoint-
Dokumente integriert, in 24+ Monaten nicht obsolet wird und unsere Lernfähigkeits-
Anforderungen (siehe Pflichtenheft Sektion 7) erfüllt.

# STRATEGISCHER KONTEXT
- Datenquellen Phase 1: Tasks (PostgreSQL), Kommentare, Mails (über M365 Graph).
- Phase 2: Notizen, M365 Calendar.
- Phase 3: InnoSmith News-DB (PostgreSQL bei Hostinger), OneDrive/SharePoint-Docs.
- Datenmenge initial: tausende Items, in 12 Monaten zehntausende.
- Sprachen: ca. 80% Deutsch, 20% Englisch.
- LLM-Mix: lokal (Asus GX10) + Cloud (Opus 4.7, Gemini 2.5 Pro mit 1M Context, GPT-5).
- Datenschutz: Vektor-Index möglichst lokal (pgvector bevorzugt vs. eigene Service-DBs).
- Memory-Anforderung: Episodic + Semantic + Procedural (siehe Pflichtenheft 7.1).
- Kontinuierliches Lernen: Memory-Items werden über Wochen/Monate verändert,
  konsolidiert, gelöscht.
- Anti-Pattern-Detector: System soll wiederkehrende Fragen erkennen und automatisch
  in stabiles Memory überführen.

# RECHERCHE-FRAGEN (gewichtet)
1. (20%) **Klassisches RAG vs. Long-Context vs. Hybrid** — Stand 2026:
   1.1 Welche Use-Cases profitieren von 1M-Token-Long-Context (Gemini, Claude)?
   1.2 Wo bleibt klassisches RAG überlegen (Latenz, Kosten, Datenfrische, Privacy)?
   1.3 Hybrid-Pattern: Pre-Filter mit RAG, Reasoning mit Long-Context.
   1.4 Aktuelle Studien zu "Lost in the Middle"-Effekt 2025/2026.
2. (20%) **Memory-Frameworks** im direkten Vergleich:
   2.1 Letta (ehem. MemGPT) — Reife, API-Stabilität, Production-Adoption.
   2.2 Mem0 — Lizenzmodell, Self-Hosted-Tauglichkeit, Performance.
   2.3 Zep — Open-Source vs. Enterprise, GraphRAG-Features.
   2.4 Cognee — Knowledge-Graph-First-Ansatz.
   2.5 Graphiti — Bi-temporal Knowledge Graph.
   2.6 Eigene Implementation (pgvector + selbstgebautes Reflexion-Pattern).
3. (15%) **Vektor-DB-Wahl**:
   3.1 pgvector (HNSW, Quantisierung, Performance bei 100k–1M Vektoren).
   3.2 Qdrant, Weaviate, Milvus — wann Wechsel von pgvector lohnt.
   3.3 Embedding-Modelle 2026 für Deutsch (E5-Multilingual, BGE-Multilingual,
       Cohere-Embed-v3-multilingual, jina-embeddings-v3, etc.).
   3.4 Hybrid Search (Sparse + Dense + Re-Ranking) — welche Re-Ranker (Cohere,
       BGE-Reranker, ColBERT)?
4. (15%) **Memory-Compaction & Forgetting** — bewährte Strategien:
   4.1 Importance-Scoring-Modelle (recency, frequency, manual flags).
   4.2 Konsolidierungs-Patterns (Episodic → Semantic-Verdichtung).
   4.3 Forgetting-Policies (zeitbasiert, importance-basiert, expliziter User-Wille).
   4.4 Privacy: DSGVO-Forget-Implementation in Vektor-Indizes (Re-Indexing-Kosten).
5. (10%) **Reflection-Loops** — produktionstaugliche Implementierungen:
   5.1 Welche Frameworks haben out-of-the-box Reflection?
   5.2 Self-Critique / Generator-Critic-Patterns.
   5.3 Evaluations-Tooling für Reflection-Qualität (LangSmith, Langfuse, RAGAS, Phoenix).
6. (10%) **Agentic RAG** (Agent entscheidet, was zu retriven ist):
   6.1 Tool-Use-basiertes Retrieval (Search-Tool, Filter-Tool, Re-Rank-Tool).
   6.2 Multi-Hop-Retrieval-Patterns.
   6.3 Performance-/Kosten-Trade-offs.
7. (10%) **Multi-Tenant-Isolation** für Phase 4:
   7.1 Per-Tenant-Embeddings und -Indizes.
   7.2 Cross-Tenant-Leakage-Vermeidung in Reflection-Loops.

# BEWERTUNGSKRITERIEN
| Kriterium | Gewicht |
|---|---|
| Lernfähigkeits-Tauglichkeit (Episodic + Semantic + Procedural) | 25% |
| Privacy & Lokal-Tauglichkeit | 20% |
| Skalierbarkeit für 12+ Monate Wachstum | 15% |
| Ökosystem-Integration (LangGraph/anderer Orchestrator) | 15% |
| Production-Reife & Wartbarkeit | 15% |
| Kosten (Self-Hosting + Embeddings + ggf. Cloud-Komponenten) | 10% |

# ANTI-ANFORDERUNGEN
- Keine reinen "Vector-DB-only"-Empfehlungen — Memory-Layer ist mehr als Vektoren.
- Keine Empfehlungen, die ausschliesslich auf Cloud-APIs basieren (Privacy!).
- Keine Knowledge-Graph-Empfehlungen ohne klaren Productivity-Personal-Agent-Bezug.

# QUELLEN-ANFORDERUNGEN
- Offizielle Frameworks-Dokus, GitHub-Issues mit Production-Reports.
- arxiv-Papers zu Memory-Architekturen, Reflexion, Generative Agents,
  Self-RAG, Corrective RAG.
- Benchmarks: BEIR, MTEB (insb. multilingual), German Benchmarks.
- Talks von 2025/2026 (NeurIPS, EMNLP, AI Engineer Summit, LangChain DevDay).

# OUTPUT-FORMAT
- Sprache: Deutsch.
- Länge: 3'000–4'500 Wörter.
- Pflicht-Sektionen:
  1. Executive Summary mit konkreter Empfehlung (Stack-Bausteine + Begründung).
  2. Architektur-Diagramm (Mermaid) der empfohlenen Lösung.
  3. Vergleichstabelle Memory-Frameworks.
  4. Vergleichstabelle Vektor-DBs + Embedding-Modelle.
  5. Konkrete Memory-Compaction-Strategie für TaskPilot.
  6. Reflection-Loop-Patterns (Daily/Weekly/Monthly) als Pseudocode.
  7. Migrationspfad falls Long-Context später RAG ersetzt.
  8. Multi-Tenant-Isolation-Plan Phase 4.
  9. Quellen + Self-Check.

# VALIDIERUNG
- Versionen aller empfohlenen Frameworks/DBs.
- Pro Empfehlung: konkretes Github-Repo / Production-Report.
- Bei Benchmarks: Konfiguration und Datum.

# FOLLOW-UP-VORSCHLAG
- Vertiefung "Embedding-Modell-Vergleich speziell für deutsche Geschäftskommunikation".
- Vertiefung "Implementierung Anti-Pattern-Detector mit [empfohlenem Memory-Framework]".
```

---

### 17.6 Datenschutzkonforme Messenger-Integration Schweiz/EU

```text
# ROLLE
Du bist Senior Architekt für sichere Messaging-Integrationen mit Fokus DACH-Markt
und Erfahrung in revDSG/DSGVO-konformen Bot-Implementationen für KMU und
Beratungsfirmen.

# MISSION
Empfehle EINEN Messenger als primären Mobile-Quick-Capture- und Approval-Kanal
für TaskPilot (persönlicher Use, InnoSmith-CH-Geschäftsleitung) UND eine
Whitelabel-taugliche Empfehlung für Kunden-Phase-4 — falls dies dasselbe Tool
ist, ausdrücklich begründen.

# STRATEGISCHER KONTEXT
- Persönliches Setup: 1 Nutzer, kein Team, keine Massensendung. Erwartete Last:
  10–50 Messages/Tag bidirektional.
- Phase 4 Kunden-Setup: pro Mandant 1–10 Nutzer mit potentiell strikteren
  Datenschutz-Anforderungen (Schweizer Anwälte, Behörden, Health-Care).
- Anwendungsfall:
  1. Mobile Quick-Capture: "Erinnere mich an Smith-Offerte" -> Task-Erstellung.
  2. Approval-Anfragen: "Soll ich diese Mail an Müller senden? [Ja] [Nein] [Anpassen]".
  3. Statusmeldungen: "Task X ist erledigt" / "Benötige Klärung zu Y".
- Datenschutz: revDSG/DSGVO, Server-Standort vorzugsweise CH/EU, E2E-Verschlüsselung
  als Plus, Datenminimierung als Default.
- Reichweite: Berater hat Geschäftskontakte, die Messenger sind Teil der Außendarstellung.
- UX-Anforderung: Inline-Buttons / Adaptive Cards für 1-Klick-Approvals.

# RECHERCHE-FRAGEN (gewichtet)
1. (25%) **Plattform-Vergleich** im Detail:
   1.1 Telegram Bot API — Server-Standort, Datenschutz-Pakt, E2E nur in Secret-Chats
       (gilt für Bots nicht), Inline-Keyboards, Webhook-Reife, Geschäftliche Akzeptanz CH.
   1.2 WhatsApp Business API (Cloud/On-Premises) — Meta-Datenflüsse, Pflicht zu BSP
       (Business Solution Providers), Kosten-Modell 2026 (Conversation Pricing),
       Template-Message-Pflicht ausserhalb 24h-Fenster.
   1.3 Signal — offizielle Bot-Möglichkeiten 2026, signal-cli, Privacy-Vorteile,
       UX-Limitationen.
   1.4 Threema (Threema Work, Threema Broadcast, Threema Gateway) — Schweiz-Hosting,
       revDSG-perfect-fit, Bot-Möglichkeiten und Kosten.
   1.5 SimpleX — Reife der Bot-Layer, Akzeptanz, Backup-/Account-Recovery-Fragen.
   1.6 Matrix (Element + Bot SDKs) — Self-Hosting, Federation-Implikationen.
   1.7 Microsoft Teams (als Alternative über bestehende M365-Lizenz) — wäre hier
       sinnvoller als Pure-Messenger?
2. (15%) **Datenschutz-Implikationen pro Plattform**:
   2.1 Server-Standort, Auftragsdatenverarbeitungs-Vertrag verfügbar.
   2.2 Welche Metadaten sieht der Anbieter (Kontakte, Zeitstempel, Inhaltsgrößen)?
   2.3 Verhalten in Behörden-/Kunden-Hochsicherheits-Settings (z.B. Anwaltskanzleien CH).
3. (15%) **Bot-API-Reife & Developer-Experience**:
   3.1 SDK-Qualität (Python bevorzugt), Webhook vs. Polling.
   3.2 Inline-/Rich-Interactions: Buttons, Quick-Replies, Cards mit Media.
   3.3 Rate-Limits, Reliability, Reconnect-Patterns.
   3.4 Fehlerhandling bei Mobile-Offline, Message-Delivery-Garantien.
4. (15%) **Praxis-Akzeptanz im DACH-Geschäftsumfeld 2026**:
   4.1 Welche Plattform nutzen Geschäftspartner faktisch?
   4.2 Erwartungshaltungen Kunde / Behörde / Anwalt / Arzt / Schweizer KMU.
   4.3 Friction für InnoSmith-Kunden (z.B. App-Installation Pflicht ja/nein).
5. (10%) **Kosten 2026** über 24-Monats-Horizont:
   5.1 Persönlicher Use (kostenfrei vs. Pro-Tier vs. API-Kosten).
   5.2 Whitelabel-Kunden-Setup (pro Tenant, pro Conversation, pro Message).
6. (10%) **UX-Integration Approval-Flow**:
   6.1 Beste Plattform für 1-Klick-Approval mit Begründungs-Eingabe.
   6.2 Multi-Choice-Antworten (Ja / Anpassen / Verwerfen / Snooze).
7. (10%) **Whitelabel-Tauglichkeit Phase 4**:
   7.1 Welche Plattform erlaubt Branding pro Tenant (eigener Bot, eigene Bot-Farbe)?
   7.2 Onboarding-Friction für End-User in Kundeninstanzen.

# BEWERTUNGSKRITERIEN
| Kriterium | Gewicht |
|---|---|
| revDSG/DSGVO-Konformität & Datenminimierung | 25% |
| Bot-API-Reife & UX-Möglichkeiten | 20% |
| DACH-Geschäftsakzeptanz | 15% |
| Kosten über 24 Monate (persönlich + Whitelabel) | 15% |
| Reliability & Delivery-Garantien | 15% |
| Whitelabel-Tauglichkeit Phase 4 | 10% |

# ANTI-ANFORDERUNGEN
- Keine SMS-basierten Lösungen.
- Keine reinen Webhook-Dashboards ohne Native-Mobile-App.
- Keine Empfehlung "WhatsApp privat" — wir brauchen offiziell genutzte Business-API.

# QUELLEN-ANFORDERUNGEN
- Offizielle Plattform-Dokus & ToS.
- DACH-Datenschutzanalysen (EDÖB Schweiz, BfDI Deutschland) zu jeweiliger Plattform.
- Threema-Datenschutz-Erklärung & SOC-Reports.
- Praxisberichte aus Anwalts-/KMU-Settings 2025/2026.

# OUTPUT-FORMAT
- Sprache: Deutsch.
- Länge: 2'500–3'500 Wörter.
- Pflicht-Sektionen:
  1. Executive Summary (Empfehlung persönlich + Empfehlung Whitelabel).
  2. Vergleichstabelle aller Plattformen.
  3. Datenschutz-Tiefenprofil pro Top-3.
  4. UX-Mockup-Beschreibung Approval-Flow auf Top-Plattform.
  5. Kosten-Modell 24 Monate (zwei Szenarien).
  6. Implementierungs-Skizze Bot-Setup (Auth, Webhook, Hosting).
  7. Quellen + Self-Check.

# VALIDIERUNG
- Pro Plattform: aktueller Stand der Bot-API (Versionierung, Datum).
- Datenschutz-Aussagen mit Doku-Verweis.
- Kosten mit Datum und Plan-Variante.

# FOLLOW-UP-VORSCHLAG
- Vertiefung "Threema Gateway Setup für Bot-Use-Case".
- Vertiefung "Kombination Telegram (persönlich) + Threema (Whitelabel) — Architektur-Auswirkungen".
```

---

### 17.7 Lernende Agenten — Mechanismen, Patterns, Evaluation 2026

```text
# ROLLE
Du bist Forscher und Praktiker für stateful, kontinuierlich-lernende Personal-
Agent-Systeme. Du kennst die akademische Diskussion (Reflexion, Generative Agents,
Voyager, AutoGPT-Lessons-Learned) und die produktiven Frameworks 2025/2026.

# MISSION
Liefere eine konkrete, implementierbare Blaupause für die Lernschleife in
TaskPilot, die Woche für Woche messbare Verbesserung erzeugt, ohne in typische
Failure-Modes (Memory-Bloat, Concept-Drift, Hallucinated-Memories, Catastrophic-
Forgetting bei Fine-Tuning) zu laufen.

# STRATEGISCHER KONTEXT
- Lernfähigkeit ist gemäss Pflichtenheft das zentrale Differentiator-Feature
  (siehe Sektion 7).
- Mechanismen-Kanon: Episodic Memory, Semantic Memory, Procedural Memory
  (Few-Shot-Library), Reflection-Loops, Feedback-Loop, Anti-Pattern-Detector,
  optional LoRA-Fine-Tuning Phase 5.
- Anforderungen an Messbarkeit: Klassifizierungs-Trefferquote steigt, Anti-Pattern
  "wiederkehrend dumme Fragen" sinkt gegen 0, Time-to-Approval sinkt, etc.
- Privacy: Lernen darf NIE über Mandantengrenzen leaken; User kann jederzeit
  "vergessen lassen".
- Stack-Annahme: Python + LangGraph oder vergleichbar + lokales LLM (siehe 17.4)
  + Memory-Framework (siehe 17.5).

# RECHERCHE-FRAGEN (gewichtet)
1. (20%) **Reflection-Loop-Patterns** im Detail:
   1.1 Was genau passiert in einer "Daily Reflection" eines Personal-Agenten?
   1.2 Welche Prompts haben sich in 2025/2026 produktiv bewährt? (Beispiel-Prompts liefern.)
   1.3 Tagged-Insight-Pattern (Reflection generiert getypte Insights, die ins Memory wandern).
   1.4 Reflection-Frequenzen: Daily / Weekly / Monthly / Event-Triggered.
   1.5 Wie verhindert man "self-confirming" Reflexion (Agent bestätigt eigene falsche Annahmen)?
2. (20%) **Anti-Pattern-Detection** (TaskPilot-Spezifikum, siehe Pflichtenheft 7.7):
   2.1 Wie erkennt man algorithmisch wiederkehrende User-Fragen-Pattern?
   2.2 Wann ist "auf Nachfrage merken" sinnvoll vs. Default-Verhalten ableiten?
   2.3 Bekannte Implementierungsmuster aus Letta/Mem0/Zep/eigene Kombinationen.
3. (15%) **Few-Shot-Library-Kuration**:
   3.1 Voll-automatisch vs. Hybrid-Kuration vs. manueller Wochen-Review.
   3.2 Konsolidierung redundanter Examples, Detection veralteter Examples.
   3.3 Retrieval von Few-Shots zur Inference-Zeit (semantische Suche, Skill-spezifische Filter).
4. (15%) **Tone-of-Voice-Lernen** für E-Mail-Verfassen Phase 3:
   4.1 Style-Embeddings vs. Few-Shot vs. Lightweight-Fine-Tune.
   4.2 Cluster-basierte Stilprofile (pro Empfänger-Typ Cluster).
   4.3 Wann lohnt sich ein dedizierter LoRA-Adapter für Tone-of-Voice?
5. (10%) **LoRA-Fine-Tuning** (Phase 5) — wann sinnvoll, wie absichern:
   5.1 Indikatoren wann Fine-Tune lohnt vs. weiter mit RAG/Few-Shot reicht.
   5.2 Datensatz-Größe (typisch 200/500/1000+ Samples) und Sample-Qualitäts-Metriken.
   5.3 Catastrophic-Forgetting-Vermeidung (Mix mit allgemeinen Daten, Adapter-Stacking).
   5.4 Eval vor/nach Training (z.B. Hold-out-Set, Goldstandard-Antworten).
6. (10%) **Evaluation & KPIs** (siehe Pflichtenheft 7.8):
   6.1 Welche Metriken sind in 2025/2026 produktiv im Einsatz?
   6.2 Tooling: LangSmith, Langfuse, Phoenix, Patronus, eigenbau-Eval.
   6.3 LLM-as-Judge-Patterns für Lernfortschritt-Messung.
7. (10%) **Failure-Modes lernender Agenten** und Gegenmaßnahmen:
   7.1 Memory-Bloat (Memory wird so groß, dass Retrieval verschlechtert).
   7.2 Concept-Drift (User-Verhalten ändert sich, Agent klebt an alten Patterns).
   7.3 Hallucinated Memories (Reflection erfindet Episoden, die nie passierten).
   7.4 Privacy-Leaks via Reflection (Mandant A wird in Reflection für Mandant B sichtbar).

# BEWERTUNGSKRITERIEN
| Kriterium | Gewicht |
|---|---|
| Praktische Umsetzbarkeit (mit Code-Skeletten) | 25% |
| Failure-Mode-Robustheit | 20% |
| Messbarkeit / Eval-Tauglichkeit | 20% |
| Privacy & Multi-Tenant-Tauglichkeit | 15% |
| Geringe Lock-in zu spezifischem Framework | 10% |
| Kostenkontrolle (LLM-Calls für Reflection-Loops) | 10% |

# ANTI-ANFORDERUNGEN
- Keine rein-akademischen Antworten ohne Bezug zu produktiver Implementierung.
- Keine Empfehlungen, die OpenAI Assistants API als Lock-in voraussetzen.
- Keine Reinforcement-Learning-from-Human-Feedback-Schwergewichts-Pipelines —
  wir wollen leichtgewichtige Mechanismen.

# QUELLEN-ANFORDERUNGEN
- Reflexion-Paper (arxiv 2303.11366), Generative Agents (arxiv 2304.03442),
  MemGPT (arxiv 2310.08560), Voyager (arxiv 2305.16291), Self-RAG (arxiv 2310.11511),
  jüngere Memory-Architektur-Papers 2024/2025.
- Production-Reports (Letta-Blog, Mem0-Blog, LangChain Memory-Posts, Personal-Agent-Builder Blogs).
- Talks 2025/2026 von AI Engineer Summit, NeurIPS, EMNLP.

# OUTPUT-FORMAT
- Sprache: Deutsch.
- Länge: 3'500–5'000 Wörter.
- Pflicht-Sektionen:
  1. Executive Summary mit empfohlenem Mechanismen-Kanon.
  2. Architektur-Diagramm Lernschleifen (Mermaid).
  3. Pro Mechanismus: Beschreibung, Pseudocode/Beispiel-Prompt, Failure-Modes, Mitigation.
  4. Eval-Plan mit konkreten KPIs und Tooling-Empfehlung.
  5. Roadmap "Lernfähigkeit-Reife" über 12 Monate (was wann implementieren).
  6. LoRA-Trainings-Vorgehen Phase 5 als Skizze.
  7. Privacy-Schutz-Patterns für Multi-Tenant.
  8. Quellen + Self-Check.

# VALIDIERUNG
- Pro Pattern: konkretes Open-Source-Beispiel (Repo + Datei) referenzieren.
- Pro Eval-Tool: Aktualität & Lizenz nennen.
- Pseudocode in Python, ablauffähig genug zum Verständnis.

# FOLLOW-UP-VORSCHLAG
- Vertiefung "Reflection-Prompt-Templates für deutschsprachige Productivity-Agenten".
- Vertiefung "LangSmith vs. Langfuse für lange-laufende Personal-Agenten".
```

---

### 17.8 Demo- & Showcase-Architekturen für Agentic AI im B2B-Pitch

```text
# ROLLE
Du bist Senior Product- und Pre-Sales-Architekt mit Erfahrung in Agentic-AI-
Demonstrationen für B2B-Kundengespräche im DACH-Mittelstand und in der
öffentlichen Verwaltung. Du weißt, was im Pitch wirkt, was billig wirkt, und
welche Architektur-Entscheidungen nötig sind, um eine Demo nicht zu einer
Code-Bombe zu machen.

# MISSION
Liefere eine konkrete Demo-/Showcase-Architektur und Storyboard-Empfehlung für
TaskPilot als InnoSmith-Vertriebs-Asset, die im 5–20-minütigen Live-Pitch ohne
Risiko (Datenschutz, Stabilität) das wirkungsvoll vermittelt, was TaskPilot
differenziert: Hybrid-LLM-Routing mit Datenklassifikation, Lernfähigkeit über
Wochen, Human-in-the-Loop, offene MCP-Integration.

# STRATEGISCHER KONTEXT
- Zielgruppe Demo: CEOs, CIOs, PMOs, Innovations-/Strategie-Teams, öffentliche
  Verwaltung in DACH.
- Demo-Settings:
  - Live im Workshop (vor Ort, Beamer).
  - Hybrid-Setup (Teams/Zoom mit Screen-Share).
  - Self-Service (Demo-Link an Interessent vor/nach Gespräch).
- Datenschutz-Anforderung: synthetische Demo-Daten, keine echten Mandanten.
- Demo-Modus muss vom Berater in <5 Minuten zurückgesetzt/initialisiert werden können.
- Der "Wow-Moment" muss klar identifiziert sein (z.B. Live-Routing sichtbar,
  Vor-/Nach-Lerneffekt-Demo).
- Existierendes InnoSmith-Branding (siehe https://innosmith.ch/ai-solutions/).
- Architektur-Entscheidungen aus Pflichtenheft Sektion 13 sind bindender Rahmen.

# RECHERCHE-FRAGEN (gewichtet)
1. (20%) **State-of-the-Art Demo-Patterns** für Agentic AI 2025/2026:
   1.1 Welche Vendoren machen das gut (Anthropic-Demos, Cognition-Devin-Pitches,
       Microsoft-Copilot-Studio-Demos, OpenAI-Operator-Demos)?
   1.2 Was sind die wiederkehrenden "Wow-Mechanismen" und warum funktionieren sie?
   1.3 Welche Anti-Pattern (z.B. zu schnelle Animationen, Talking-Heads ohne UX-Bezug)?
2. (20%) **Visualisierung von LLM-Routing in Echtzeit**:
   2.1 UI-Patterns (persistente Banner, Inline-Badges, Dashboard-Sidebar).
   2.2 Welche Daten zeigen (Modell-Name, Datenklasse, Tokens, Kosten, Latenz)?
   2.3 Animation/Polish-Niveau ohne kitschig zu wirken.
3. (15%) **"Lernender Agent über Wochen" als Demo**:
   3.1 Wie macht man Lernfortschritt in 5 Minuten sichtbar?
   3.2 Vor-/Nach-Vergleich-Patterns ("Vor 4 Wochen wurde diese Mail noch
       falsch klassifiziert — heute richtig, weil ...").
   3.3 Reproduzierbarkeit der Demo (gleicher Lerneffekt jeder Session).
4. (15%) **Synthetic-Data-Generation** für realistische Demo-Mandanten:
   4.1 LLM-generierte Templates (Kunden-Profile, Mails, Tasks, Konversationsverläufe).
   4.2 Konsistenz über mehrere Demo-Mandanten (Personas mit Kontinuität).
   4.3 Vermeidung "uncanny" — wie wirkt synthetisches Material echt?
5. (10%) **Demo-Modus-Architektur** technisch:
   5.1 Sandbox-Datenbank vs. Filter im Mehr-Tenant-Modus.
   5.2 Reset-Mechanismus (DB-Snapshot-Restore, Skript-basiert).
   5.3 Klare visuelle Kennzeichnung (Banner "DEMO" wie/wo).
6. (10%) **Storyboarding / Skript-Engine**:
   6.1 Skript-Format (YAML/JSON/eigene DSL) für reproduzierbare Demos.
   6.2 Step-by-step-Auto-Play vs. Berater-getriggert.
   6.3 Failure-Modes (Demo bricht ab) und Recovery.
7. (10%) **A/B-Vergleich-Patterns** (gleiche Anfrage an mehrere LLMs):
   7.1 Side-by-side-Anzeige Local vs. Cloud, mit Latenz und Kosten.
   7.2 Bias-Awareness (Cherry-Picking vermeiden).

# BEWERTUNGSKRITERIEN
| Kriterium | Gewicht |
|---|---|
| Glaubwürdigkeit & Anti-Kitsch | 25% |
| Reproduzierbarkeit & Stabilität | 20% |
| Wirkung in 5 Minuten (Wow-Moment-Tauglichkeit) | 20% |
| Aufwand vs. Nutzen (was lohnt sich, was nicht) | 15% |
| Datenschutz-Sauberkeit (Demo-Daten klar synthetisch) | 10% |
| Self-Service-Tauglichkeit (Demo-Link für Interessenten) | 10% |

# ANTI-ANFORDERUNGEN
- Keine reinen UX-Polish-Tipps ohne Architektur-Bezug.
- Keine Marketing-Floskeln, sondern konkrete UI-/Daten-/Workflow-Patterns.
- Keine Empfehlungen, die nur in Cloud-Setups funktionieren.

# QUELLEN-ANFORDERUNGEN
- Aufzeichnungen bekannter Agentic-AI-Demos 2025/2026 (Anthropic, OpenAI,
  Cognition, Microsoft, Google).
- B2B-SaaS-Demo-Best-Practices (Reforge, ProductLed, OpenView).
- Pre-Sales-Engineering-Communities (Sales Engineer Slack, Demo Forge Konferenzen).

# OUTPUT-FORMAT
- Sprache: Deutsch.
- Länge: 2'500–3'500 Wörter.
- Pflicht-Sektionen:
  1. Executive Summary (Top-Empfehlung als 5-Bullet-Storyboard).
  2. Storyboard-Skizze für 10-Minuten-Demo (Step-by-step, mit Wow-Momenten).
  3. UI-/Architektur-Empfehlungen für Routing-Visualisierung & Lerneffekt-Demo.
  4. Synthetic-Data-Strategie inkl. Generation-Pipeline.
  5. Demo-Modus-Architektur (technische Skizze).
  6. Anti-Pattern-Liste mit Beispielen.
  7. Self-Service-Demo-Variante (asynchron).
  8. Quellen + Self-Check.

# VALIDIERUNG
- Pro Pattern: konkretes Demo-Beispiel als Referenz (Video/URL).
- Storyboard mit konkreten Zeit-Markern.
- UI-Empfehlungen mit Tool-Vorschlag (z.B. shadcn-Komponenten, Beispiel-Code-Snippet).

# FOLLOW-UP-VORSCHLAG
- Vertiefung "Self-Service-Demo-Architektur als Sandbox per Customer-ID".
- Vertiefung "Storytelling-Templates für Datenschutz-CIO-Pitches CH/DE/AT".
```

---

### 17.9 MCP-Architektur 2026 — Reife, Patterns, Build-vs-Buy

```text
# ROLLE
Du bist Senior Architect mit Schwerpunkt Agent-Tool-Interoperabilität. Du hast
seit MCP-Launch 2024 die Entwicklung verfolgt, eigene MCP-Server gebaut und
kennst typische Failure-Modes (Auth, Schema-Drift, Latenz) sowie die
Konkurrenz-Standards A2A und Agent-Cards.

# MISSION
Empfehle eine konkrete MCP-Architektur für TaskPilot (Client + eigene Server)
und liefere eine Build-vs-Buy-Matrix für die wichtigsten externen Connector-
Bedarfe (M365 Mail/Calendar, GitHub, PostgreSQL News-DB, lokale Filesysteme).

# STRATEGISCHER KONTEXT
- TaskPilot ist sowohl MCP-Client (konsumiert externe Tools) als auch -Server
  (exponiert eigene Tools für andere Agents wie Cursor).
- Stack-Sprachen: Python primär, TypeScript für Custom-Cockpit.
- Datenschutz: einige Server müssen lokal laufen (z.B. M365-Connector mit
  OAuth2-Token-Storage), andere können Cloud sein.
- Deployment: Docker Compose, Phase 4 evtl. Kubernetes pro Mandant.
- Bestehende InnoSmith-Solutions als potentielle MCP-Server-Kandidaten:
  Signa (News-Synthese), InvoiceInsight (Software-Portfolio), ImpactPilot
  (Projektportfolio), BidSmarter (Opportunity-Matching).

# RECHERCHE-FRAGEN (gewichtet)
1. (20%) **MCP-Reife & Standardisierung** Stand April 2026:
   1.1 Spec-Stand (Versionen, Breaking Changes seit Initial Release).
   1.2 SDK-Reife Python und TypeScript (offizielle vs. Community).
   1.3 Wer treibt MCP (Anthropic, andere)? Wettbewerb durch A2A (Google) und
       Agent-Cards — Konsolidierung absehbar?
2. (20%) **Build-vs-Buy für TaskPilot-Connectors**:
   2.1 M365 Mail/Calendar — gibt es produktionsreife MCP-Server (Anthropic-offiziell,
       Community)? Lizenz, Auth-Modell?
   2.2 GitHub — offizieller MCP-Server, Reife, Limitierungen.
   2.3 PostgreSQL — generischer DB-Server vs. Custom-Server für News-DB-spezifische Queries.
   2.4 Lokales Filesystem / OneDrive / SharePoint — was existiert, was fehlt?
3. (15%) **Eigenen MCP-Server bauen — Best Practices 2026**:
   3.1 Python-Skeleton (FastMCP, anthropic-sdk-python, mcp-python-sdk).
   3.2 TypeScript-Skeleton.
   3.3 Tool-Schema-Design, Resource-Modell, Prompts-Funktion.
   3.4 Logging, Tracing, Health-Endpoints.
4. (15%) **Authentifizierungs- & Berechtigungspatterns**:
   4.1 Per-User-Tokens vs. Service-Tokens, OAuth2-Flows.
   4.2 Scope-Beschränkungen pro Tool.
   4.3 Audit-Log-Patterns für MCP-Server (welche Tools wurden wann mit welchen Argumenten gerufen).
5. (10%) **Performance & Latenz**:
   5.1 Stdio vs. SSE vs. HTTP/WebSocket — Trade-offs.
   5.2 Multiplexing mehrerer Tool-Calls.
   5.3 Caching-Patterns für teure Tool-Calls.
6. (10%) **Testing & Verlässlichkeit**:
   6.1 MCP-Server-Tests (Schema-Konformität, Idempotenz, Fehler-Pfade).
   6.2 Mock-MCP-Server für Agent-Layer-Tests.
   6.3 Property-Based-Testing für Tool-Schemas.
7. (10%) **TaskPilot-spezifische MCP-Server-Skizze**:
   7.1 task-management-server (Tools: createTask, moveTask, addComment, ...).
   7.2 memory-server (Tools: searchMemory, addInsight, forgetMemory).
   7.3 routing-policy-server (Tools: classifyData, getRoutingDecision).
   7.4 Wie können diese Server intern auch von TaskPilot selbst aufgerufen werden
       (Konsistenz mit externen Konsumenten)?

# BEWERTUNGSKRITERIEN
| Kriterium | Gewicht |
|---|---|
| Spec-Stabilität & 24-Monats-Bestand | 20% |
| Reife der Server-Implementierungen für unsere Bedarfe | 20% |
| Build-vs-Buy-Klarheit (Empfehlung pro Connector) | 15% |
| Sicherheit (Auth, Audit, Berechtigung) | 15% |
| Performance & Operational | 15% |
| Test- und Wartbarkeit | 10% |
| Interop mit A2A / Agent-Cards (Zukunftssicherheit) | 5% |

# ANTI-ANFORDERUNGEN
- Keine generische MCP-Werbung — wir wollen technische Tiefe.
- Keine Empfehlungen ohne konkrete Repo-Verweise.
- Keine Patterns, die nur mit Anthropic-Cloud funktionieren — wir nutzen
  Multi-LLM-Routing.

# QUELLEN-ANFORDERUNGEN
- Offizielle MCP-Spec, Anthropic-Doku, github.com/modelcontextprotocol.
- Awesome-MCP-Servers-Listen mit Aktualitäts-Check.
- Production-Berichte 2025/2026 zu MCP-Einsatz.
- Vergleich mit A2A-Spec (Google) und Agent-Cards.

# OUTPUT-FORMAT
- Sprache: Deutsch.
- Länge: 3'000–4'000 Wörter.
- Pflicht-Sektionen:
  1. Executive Summary (Architektur-Empfehlung in 7 Bullets).
  2. MCP-Reife-Briefing (Spec-Versionen, SDK-Stand, Konkurrenz).
  3. Build-vs-Buy-Matrix für TaskPilot-Connectors.
  4. Beispiel-Skeleton eines TaskPilot-MCP-Servers (Python, kommentiertes Code-Snippet).
  5. Auth-/Audit-Pattern-Empfehlungen.
  6. Test-Strategie (mit Mock-Setup).
  7. Liste empfohlener bestehender MCP-Server (Top-15 für Productivity).
  8. Risiken & A2A/Agent-Cards-Konvergenz-Szenarien.
  9. Quellen + Self-Check.

# VALIDIERUNG
- Spec-Version mit Datum.
- Pro empfohlenem Server: GitHub-Repo, letztes Release, Lizenz.
- Code-Skeleton lauffähig genug für Verständnis.

# FOLLOW-UP-VORSCHLAG
- Vertiefung "MCP-Server für InnoSmith Signa-News-DB als Wissensquelle".
- Vertiefung "MCP-Auth über OAuth2 mit Per-Tenant-Token-Stores".
```

---

### 17.10 EU AI Act + revDSG für Agentic Productivity-Tools 2026

```text
# ROLLE
Du bist Senior Compliance- und Datenschutz-Berater mit Schwerpunkt EU AI Act,
DSGVO und Schweizer revDSG. Du arbeitest seit 2024 mit Anbietern und Betreibern
von Agentic-AI-Lösungen und kennst die deutsch- und englischsprachigen Leitfäden
der EDÖB, BfDI, EDPB sowie des EU AI Office.

# MISSION
Liefere eine handlungsfähige Compliance-Checkliste mit konkreten Implementierungs-
hinweisen für TaskPilot — sowohl für die persönliche Nutzung als auch für die
Mandantenfähigkeit Phase 4 mit InnoSmith-Kunden in der Schweiz und in der EU.

# STRATEGISCHER KONTEXT
- Anbieter: InnoSmith GmbH (Schweiz), liefert TaskPilot als Werkzeug für eigene
  Beratung UND als On-Premise-/Whitelabel-Lösung für Kunden.
- Betreiber: Selbst (Phase 1) bzw. Kunde (Phase 4).
- Use-Cases:
  - Mail-Triage und Klassifikation (Phase 1).
  - Task-Vorschläge und Workload-Balancing (Phase 2).
  - Mail-Verfassen und Versand (Phase 3) — höchstes Risiko.
- Datenschutz: revDSG-Erstanwendung Schweiz, DSGVO bei EU-Kunden, EU AI Act seit
  Q3 2025/2026 in voller Anwendung.
- LLM-Mix: lokal (Asus GX10), Hostinger (EU), Cloud (Anthropic, Google, OpenAI —
  jeweils EU-Region wo möglich).
- Personalisiertes Lernen, Memory, Reflection-Loops — was sind compliance-Implikationen?

# RECHERCHE-FRAGEN (gewichtet)
1. (20%) **EU AI Act Risiko-Klassifikation** für TaskPilot-Use-Cases:
   1.1 Mail-Triage / Klassifikation — Risiko-Klasse?
   1.2 Mail-Verfassen mit Approval — Risiko-Klasse?
   1.3 Wie verhält sich General-Purpose-AI (GPAI)-Verpflichtung beim Einsatz von
       Cloud-LLMs (Anbieter sind GPAI-Provider, wir sind Deployer/Downstream)?
   1.4 Welche Schwellen lösen welche Pflichten aus?
2. (15%) **Transparenzpflichten**:
   2.1 Kennzeichnung KI-generierter Mail-Entwürfe gegenüber Empfängern.
   2.2 Anzeige im UI, dass Klassifikationen KI-basiert sind.
   2.3 Informationsverpflichtungen beim Einsatz für InnoSmith-Kunden.
3. (15%) **Dokumentationspflichten** Anbieter und Betreiber:
   3.1 Technische Dokumentation pro Use-Case.
   3.2 Risiko-Assessment-Vorlagen.
   3.3 Gebrauchsanweisung-Pflicht (Instruction for Use).
   3.4 Welche Bestandteile eines Pflichtenhefts decken bereits Pflichten ab?
4. (15%) **Human-Oversight technisch nachweisbar**:
   4.1 Approval-Gates als Compliance-Anker.
   4.2 Audit-Log-Anforderungen (Inhalt, Aufbewahrungsdauer, Manipulationsschutz).
   4.3 Override-Möglichkeiten für menschliche Entscheidung.
5. (15%) **Datenschutz im Cloud-LLM-Einsatz**:
   5.1 Anthropic/Google/OpenAI EU-Region-Verträge — was ist nötig (DPAs, Sub-Processor-Listen)?
   5.2 Microsoft EU Data Boundary Reichweite für Copilot- und Graph-Daten.
   5.3 Transferschutz (Schrems-II-Implikationen 2026).
   5.4 Lokale LLM als Privacy-by-Design-Argument (revDSG/DSGVO).
6. (10%) **revDSG-Spezifika Schweiz**:
   6.1 Auftragsdatenverarbeitung-Vertrag CH (vs. EU AVV/DPA).
   6.2 Datenschutz-Folgenabschätzung (DSFA) — wann zwingend für TaskPilot?
   6.3 Verzeichnis der Bearbeitungstätigkeiten.
   6.4 Betroffenen-Rechte (insbesondere Auskunft + Löschung — Memory-Forget-Hooks).
7. (10%) **Mandantenfähigkeit Phase 4**:
   7.1 Welche zusätzlichen Verpflichtungen entstehen, wenn InnoSmith TaskPilot
       als SaaS-/On-Premise-Lösung an Kunden vertreibt?
   7.2 InnoSmith als "Anbieter" eines AI-Systems unter EU AI Act — Pflichten.
   7.3 Praxis-Vorlagen für AVV/DPA mit Kunden.

# BEWERTUNGSKRITERIEN
| Kriterium | Gewicht |
|---|---|
| Konkretheit der Handlungsempfehlungen | 25% |
| Aktualität der zitierten Rechts-/Behördenquellen | 20% |
| Praxis-Tauglichkeit (umsetzbar, nicht nur konform-im-Papier) | 20% |
| Schweiz-Spezifika revDSG abgedeckt | 15% |
| Multi-Tenant-Phase-4-Implikationen | 10% |
| Verständlichkeit (Berater muss damit Kunden überzeugen können) | 10% |

# ANTI-ANFORDERUNGEN
- Keine reinen Marketing-Aussagen von Anbietern.
- Keine US-zentrierten Compliance-Frameworks (NIST, SOC2) als Hauptfokus —
  diese als Sekundäres ja, aber unsere Hauptlinse ist EU/CH.
- Keine "alle Risiken vermeiden"-Empfehlungen, sondern pragmatische Risk-Acceptance-Hinweise.

# QUELLEN-ANFORDERUNGEN
- EU AI Act Volltext (artificialintelligenceact.eu, eur-lex), aktuelle delegated acts.
- EU AI Office Veröffentlichungen, EDPB-Stellungnahmen 2025/2026.
- BfDI / EDÖB Stellungnahmen zu LLM-Einsatz.
- Kommentare anerkannter Compliance-Anwaltskanzleien (CH/DE).
- Schweizer revDSG-Quellen (Bundeskanzlei, EDÖB-Leitfäden).
- Microsoft / Anthropic / Google EU Data Boundary / Sub-Processor-Listen.

# OUTPUT-FORMAT
- Sprache: Deutsch.
- Länge: 3'000–4'500 Wörter.
- Pflicht-Sektionen:
  1. Executive Summary (Top-10-Pflichten und wie sie in TaskPilot adressiert werden).
  2. EU AI Act Risiko-Klassifikation für TaskPilot-Use-Cases.
  3. Transparenzpflichten — UI-/Workflow-Implementierungs-Empfehlungen.
  4. Dokumentationspflichten — Vorlagen-Liste (was muss existieren, wo lagern).
  5. Human-Oversight-Architektur-Empfehlung mit Audit-Log-Spezifikation.
  6. Cloud-LLM-Einsatz — Vertrags- und Konfigurations-Checkliste.
  7. revDSG-Spezifika und DSFA-Trigger-Liste.
  8. Mandantenfähigkeit Phase 4 — InnoSmith als Anbieter.
  9. Praxis-Compliance-Checkliste (Kurzform für Berater-Einsatz beim Kunden).
  10. Quellen + Self-Check.

# VALIDIERUNG
- Pro Aussage: Quelle mit Datum.
- Pro Pflicht: Wer haftet (Anbieter/Betreiber/User), wann muss erfüllt sein.
- Klare Differenzierung "rechtliche Pflicht" vs. "Best-Practice".

# FOLLOW-UP-VORSCHLAG
- Vertiefung "DSFA-Vorlage für TaskPilot-Kundeninstanz".
- Vertiefung "Vertragsklauseln für InnoSmith-TaskPilot-Lizenz an Kunden".
```

---

### 17.12 nanobot Production-Hardening (Foundation-Adoption)

> **Zweck:** Validieren, ob nanobot (HKUDS, MIT, Python) als Production-Foundation für TaskPilot einsetzbar ist und welche Hardening-Schritte vor Phase 1 notwendig sind.

```text
# ROLLE
Du bist Senior Python-Architect mit 10+ Jahren Erfahrung in Production-Hardening
junger OSS-Frameworks und Multi-Tenant-Plattform-Engineering. Du arbeitest
evidenzbasiert, kennst die typischen Failure-Modes von akademisch gewarteten
Frameworks und bewertest Code-Qualität auf Basis konkreter Repository-Metriken.

# MISSION
Bewerte github.com/HKUDS/nanobot (v0.1.5.post1, ~4.000 LOC, MIT, 40K+ Stars,
240+ Contributors) als Foundation für eine Production-Personal-Productivity-
Plattform mit Compliance-Anforderungen (revDSG/DSGVO/EU AI Act). Liefere eine
konkrete Hardening-Roadmap und einen Fork/No-Fork-Empfehlung.

# STRATEGISCHER KONTEXT
- TaskPilot wird in Phase 4 mandantenfähig (Multi-Tenant). nanobot ist heute
  Single-Tenant by design.
- Markdown-Memory (HISTORY.md, MEMORY.md) ist Compliance-Vorteil, aber wie
  skaliert das bei 100+ aktiven Sessions parallel?
- Akademischer Maintainer (Hong Kong University Data Science Lab) → Risiko
  Wartungs-Stop bewerten.
- Hardware: NVIDIA GB10 (DGX Spark, 128 GB Unified Memory), Linux.

# RECHERCHE-FRAGEN (gewichtet)
1. (30 %) Code-Qualitätsbewertung: Test-Coverage, statische Analyse, typische
   Bug-Patterns in den 4K LOC. Konkrete Issues und PRs auf github.com/HKUDS/nanobot
   zitieren.
2. (20 %) Multi-Tenant-Erweiterung: Welche konkreten Code-Änderungen sind nötig,
   um Workspace-Isolation (Container-pro-Tenant + Postgres-RLS) zu erreichen?
3. (15 %) Performance-Profil: Heartbeat-Loop bei 50+ aktiven Sessions, Memory-
   Footprint pro Workspace, MCP-Client-Concurrency-Limits.
4. (15 %) Security-Audit-Checkliste: Top-10 zu prüfende Bereiche (Auth, Secrets,
   Tool-Calls, Subprocess-Aufrufe, Pickle-Deserialization, etc.).
5. (10 %) Wartungs-Risiko: Pulse-Metriken (Commits/Monat, Issue-Closure-Rate,
   Maintainer-Diversität, Sponsoring), Vergleich mit Mem0/Letta/CrewAI.
6. (10 %) Fork-Strategie: Wann lohnt sich ein eigener Fork (Code-Branch
   "innosmith-stable") vs. Upstream-only?

# BEWERTUNGSKRITERIEN
- Belastbarkeit der Quellen (eigener Code-Review > Drittquellen).
- Konkrete File:Line-Referenzen statt Allgemeinplätze.
- Vergleich zu mindestens 2 Alternativen (z.B. Mem0+LangGraph, Custom-Stack).

# ANTI-ANFORDERUNGEN
- KEINE allgemeine "nanobot ist gut/schlecht"-Aussagen.
- KEINE Empfehlung von OpenClaw, NemoClaw oder NanoClaw als Alternative
  (alle bereits geprüft, ausgeschlossen).

# QUELLEN-ANFORDERUNGEN
- nanobot-Repo, Releases, Issues, Discussions als Primärquellen.
- HKUDS-Forschungspapier (falls vorhanden).
- Vergleichbare Audits anderer Python-Agent-Frameworks (z.B. Mem0-Audit).

# OUTPUT-FORMAT
1. Executive Summary (max. 200 Wörter): Adopt / Adopt-with-Hardening / Reject + Begründung.
2. Hardening-Checkliste mit Priorität (P0/P1/P2) und Aufwand (in Personentagen).
3. Multi-Tenant-Migrationsplan (konkrete Code-Änderungen, betroffene Module).
4. Performance-Benchmark-Plan (welche Metriken bei welchen Lastprofilen messen?).
5. Wartungs-Risiko-Matrix (Risiko / Wahrscheinlichkeit / Mitigation).
6. Empfehlung Fork-Strategie + Branch-Modell.

# VALIDIERUNG
- Mindestens 5 zitierte File:Line-Referenzen auf nanobot-Repo.
- Mindestens 1 quantitative Performance-Aussage.

# FOLLOW-UP-VORSCHLAG
- Vertiefung "nanobot vs. Custom-LangGraph-Stack: TCO über 24 Monate".
```

---

### 17.13 NVIDIA NeMo Guardrails NIMs Production-Tuning auf GX10

> **Zweck:** Sicherstellen, dass die drei NeMo Guardrails NIMs (Content Safety, Topic Control, Jailbreak Detection) auf der NVIDIA GB10 (DGX Spark) production-tauglich laufen und sinnvoll in Pipelines integriert werden können.

```text
# ROLLE
Du bist NVIDIA-Inferenz-Spezialist mit konkreter Erfahrung im Deployment von
NIMs auf der DGX-Spark-Familie (GB10 Grace Blackwell, 128 GB Unified Memory).
Du kennst die typischen Latenz-/Throughput-Trade-offs und die Integration in
LangChain/LangGraph/Agent-Pipelines.

# MISSION
Liefere einen Production-Deployment-Plan für die drei NeMo Guardrails NIMs
(Content Safety, Topic Control, Jailbreak Detection) auf der NVIDIA GB10 mit
Fokus auf Latenz-Optimierung, Memory-Footprint, Pipeline-Integration und
Failover-Strategie.

# STRATEGISCHER KONTEXT
- Hardware: NVIDIA GB10 (DGX Spark), 128 GB Unified Memory, Linux.
- Co-deployment mit vLLM (Qwen3-32B-NVFP4) und SGLang (Agent-Inferenz).
- Use-Cases: Pre-Filter für MCP-Tool-Outputs (Tool-Poisoning-Schutz),
  Post-Filter für Cloud-LLM-Antworten (PII-Leak-Schutz), Topic-Control für
  Demo-Modus.
- Compliance: Output muss EU-AI-Act-konform geloggt werden (Audit-Log).

# RECHERCHE-FRAGEN (gewichtet)
1. (25 %) Memory-Budget: Wie viel der 128 GB Unified Memory verbrauchen die
   3 NIMs zusammen? Können sie parallel zu Qwen3-32B-NVFP4 laufen?
2. (25 %) Latenz-Optimierung: Welche Quantization-Optionen (FP8, INT8,
   NVFP4) sind verfügbar? Async-Pipeline-Patterns für minimale User-Wait?
3. (15 %) Failover & Skip-Logic: Wann darf ein NIM-Call übersprungen werden
   (Datenklasse `public`)? Wie verhält sich das System bei NIM-Ausfall?
4. (15 %) Integration in LangChain/LangGraph/nanobot: Bestehende Adapter,
   Code-Beispiele, Pitfalls.
5. (10 %) Modell-Updates: Update-Lifecycle der NIM-Container (NGC), Test-
   Strategie für Modell-Drift bei Updates.
6. (10 %) Lizenz & TCO: NVIDIA AI EULA-Klauseln, Kosten bei späterem
   Betrieb auf nicht-NVIDIA-Hardware (Cloud-Replikation für Multi-Tenant).

# BEWERTUNGSKRITERIEN
- Konkrete Benchmarks aus NVIDIA-Dokumentation oder verifizierten Community-
  Reports.
- Code-Beispiele in Python (FastAPI, async).
- Vergleich zu Llama Guard 3 als Alternative.

# ANTI-ANFORDERUNGEN
- KEINE Empfehlung von NemoClaw als Wrapper (bereits ausgeschlossen).
- KEINE Cloud-only-Deployment-Empfehlung (lokale Inferenz ist Pflicht).

# QUELLEN-ANFORDERUNGEN
- NVIDIA NGC, NVIDIA Developer Blog, GitHub-Issues der NIM-Repos.
- Whitepapers zu Llama Guard 3 als Vergleich.

# OUTPUT-FORMAT
1. Memory-Budget-Tabelle (NIM / Footprint / verbleibende GB für Qwen3-32B).
2. Latenz-Tabelle (Pre-Processing / Post-Processing / Skip-Logic Szenarien).
3. Pipeline-Diagramm (Mermaid) mit Async-Patterns.
4. Code-Beispiel: nanobot AgentHook für NeMo-Guardrails-Wrapper.
5. Failover-Matrix.
6. Lizenz-Risiko-Bewertung.

# VALIDIERUNG
- Memory-Aussagen mit NVIDIA-NIM-Container-Dokumentation belegt.
- Mindestens 1 Latenz-Benchmark zitiert.

# FOLLOW-UP-VORSCHLAG
- Vertiefung "Llama Guard 3 vs. NeMo Guardrails: Genauigkeit vs. Latenz auf
  deutschsprachigen Texten".
```

---

### 17.14 Plane CE Feature-Gap-Lösungen via Agent (Workflow-Engine-on-top)

> **Zweck:** Validieren, dass die fehlenden Plane-Pro-Features (Recurring Tasks, Workflow-Automations, Time Tracking) durch den TaskPilot-Agent effizient nachgebaut werden können, ohne Plane Commercial Edition zu lizenzieren.

```text
# ROLLE
Du bist Senior Solution Architect für Workflow-Automation mit konkreter
Erfahrung in Plane.so / Plane CE, Custom-Workflow-Engines und Cron-basierten
Recurring-Systemen. Du kennst die Plane API v1 vollständig und hast bereits
eigene Plane-Erweiterungen gebaut.

# MISSION
Liefere eine technische Spezifikation, wie der TaskPilot-Agent (basierend auf
nanobot mit Heartbeat/Cron) die fehlenden Plane-CE-Features (Recurring Tasks,
Workflow-Automations, Time Tracking, Custom Fields, AI Features) als
"Workflow-Engine-on-top" über die Plane API umsetzt — inklusive Architektur,
Sync-Strategie und Failure-Modes.

# STRATEGISCHER KONTEXT
- Plane CE v1.14+ (AGPL-3.0, self-hosted) ist Default-Backend in Phase 1.
- Plane Pro / Business sind closed-source und kostenpflichtig — bewusst NICHT
  gewählt.
- nanobot (Python, MIT) bringt Heartbeat-Loop und Cron-Scheduler mit.
- TaskPilot soll Plane-Backend-agnostisch bleiben (Backend-Adapter-Pattern):
  Wechsel zu Vikunja oder Eigenbau muss möglich bleiben.

# RECHERCHE-FRAGEN (gewichtet)
1. (25 %) Recurring Tasks: Wie erzeugt der Agent neue Task-Instanzen via Plane
   API? Idempotenz, Cron-Drift-Schutz, Skip-Funktion. Konkrete API-Calls und
   Datenmodell-Vorschläge.
2. (20 %) Workflow-Automations: Wie übersetzen wir die 11 MeisterTask-Pro-
   Automation-Typen (assign-on-create, status-change, send-email, etc.) in
   nanobot Skills + Plane API? Trigger-Mechanismen (Webhook vs. Polling)?
3. (15 %) Time Tracking: Eigenes Schema in Plane (Custom Fields oder
   Comment-Konvention) vs. externer Connector zu Toggl Track via MCP.
4. (15 %) Custom Fields: Plane CE limitiert Custom Fields — welche
   Workarounds (Comment-Konvention, separates Postgres-Schema) sind
   praktikabel?
5. (15 %) Sync-Strategie: Wie verhält sich der Agent bei Plane-API-Ausfall?
   Eventual-Consistency-Modell? Konflikt-Auflösung bei parallelen Edits?
6. (10 %) Performance: Polling-Intervall vs. Webhook-Trigger,
   Plane-API-Rate-Limits, Cache-Strategie.

# BEWERTUNGSKRITERIEN
- Konkrete Plane-API-Endpoints zitiert (Plane API v1 Reference).
- Code-Skeletons in Python (FastAPI + nanobot AgentHook).
- Berücksichtigung des Backend-Adapter-Patterns (gleiche Logik muss auch für
  Vikunja-Backend funktionieren).

# ANTI-ANFORDERUNGEN
- KEINE Empfehlung "Lizenziere doch einfach Plane Commercial".
- KEINE Empfehlung "Bau Plane gleich selbst" (das ist Option D, separat
  zu evaluieren).
- KEIN Workflow-Engine-Overkill (kein Temporal, kein Airflow für MVP).

# QUELLEN-ANFORDERUNGEN
- Plane API Documentation (api.plane.so).
- nanobot heartbeat/cron Module (github.com/HKUDS/nanobot).
- MeisterTask-Pro-Automation-Liste als Referenz für Funktionsumfang.
- Erfahrungsberichte von Plane-CE-Erweiterungen (GitHub-Discussions).

# OUTPUT-FORMAT
1. Architektur-Diagramm (Mermaid): Agent ↔ Plane CE über REST/Webhooks.
2. Recurring-Task-Mechanismus: Code-Skeleton + Plane-API-Calls + DB-Schema
   für `recurrence` Tabelle.
3. Workflow-Automation-Mapping-Tabelle (MeisterTask-Pro-Feature → nanobot Skill).
4. Time-Tracking-Optionen (Plane-intern vs. externer MCP-Connector zu Toggl).
5. Sync-Failure-Mode-Tabelle.
6. Performance-Empfehlung (Polling vs. Webhook).

# VALIDIERUNG
- Mindestens 5 zitierte Plane-API-Endpoints.
- 1 funktionierendes Code-Skeleton für Recurring-Task-Erzeugung.

# FOLLOW-UP-VORSCHLAG
- Vertiefung "Backend-Adapter-Pattern: Wie viel Logik bleibt agnostisch zwischen
  Plane CE und Vikunja?"
```

---

### 17.15 MCP-Security-Patterns 2026 — Defense-in-Depth in Production

> **Zweck:** Konkrete Patterns für MCP-Sicherheit in einer Production-Umgebung mit Compliance-Anforderungen — über die generischen Tipps hinaus, mit Bezug zu CVE-2025-6514, CVE-2025-49596 und Tool-Poisoning-Statistiken.

```text
# ROLLE
Du bist Security-Architect mit Spezialisierung auf Agent-Systeme, MCP, OAuth 2.1
und Zero-Trust-Architekturen. Du kennst die aktuelle MCP-CVE-Landschaft,
ATTESTMCP-Vorschläge, Cerbos PEP-Patterns und die typischen Angriffsketten gegen
MCP-basierte Agent-Systeme.

# MISSION
Liefere eine Production-Defense-in-Depth-Architektur für TaskPilot's MCP-Layer,
die (a) bekannte CVEs mitigiert, (b) gegen Tool-Poisoning schützt, (c) Compliance-
auditierbar ist und (d) für Multi-Tenant (Phase 4) skaliert. Inklusive Cerbos-
Policy-Beispielen, Tool-Description-Scanning-Patterns und Monitoring-Setup.

# STRATEGISCHER KONTEXT
- Bekannte CVEs: CVE-2025-6514 (mcp-remote RCE, CVSS 9.6), CVE-2025-49596
  (MCP Inspector RCE, CVSS 9.4).
- 5,5 % aller öffentlichen MCP-Server kompromittiert (Invariant Labs 2025).
- MCP-Architektur verstärkt Angriffe um 23–41 % vs. Non-MCP (akademisch
  belegt, arxiv 2026).
- TaskPilot ist sowohl MCP-Client als auch MCP-Server.
- Cerbos PEP ist als ABAC-Engine geplant.
- NeMo Jailbreak Detection NIM ist als Output-Filter vorgesehen.

# RECHERCHE-FRAGEN (gewichtet)
1. (25 %) Cerbos-Policy-Patterns: Konkrete Cerbos-DSL-Beispiele für
   - "Tool X darf nur User Y in Workspace Z aufrufen"
   - "Tool mit Side-Effects erfordert User-Confirmation"
   - "MCP-Server X darf maximal N Calls/Min".
2. (20 %) Tool-Description-Scanning: Welche Patterns suchen
   (`IGNORE PREVIOUS`, `read ~/.ssh`, `curl -X POST` etc.)? Tools wie
   Invariant Guardrails, Lakera Guard, eigene LLM-basierte Klassifikation?
3. (15 %) Sandboxing-Patterns: Docker-Network-Egress-Whitelist, Kubernetes
   NetworkPolicy, Firecracker-MicroVMs für besonders kritische Server?
4. (15 %) ATTESTMCP-Migration: Roadmap-Status der MCP-v2.0-Spec, Capability-
   Attestation, Origin Tagging — was kann man heute schon vorbereiten?
5. (15 %) Monitoring & Anomalie-Detection: Welche Metriken
   (Tool-Call-Frequenz, Parameter-Entropie, Response-Time-Outliers)?
   Stack-Empfehlung (Prometheus + Grafana, Falco, Wazuh, etc.)?
6. (10 %) Audit-Log-Schema: Genaue Felder pro MCP-Tool-Call für EU-AI-Act-
   Konformität (Tool, Caller, Parameter, Approval-Status, Response-Hash, ts).

# BEWERTUNGSKRITERIEN
- Konkrete CVE-Fix-Validierung (welche Pin-Versionen reichen?).
- Code-Beispiele in YAML (Cerbos), Python (Scanner) und PromQL (Monitoring).
- Berücksichtigung Multi-Tenant-Isolation (Workspace ≠ Workspace).

# ANTI-ANFORDERUNGEN
- KEINE Empfehlung von Auto-Approve-Mechanismen.
- KEINE Empfehlung von Skill-Marketplaces ohne Code-Review (OpenClaw-Anti-Pattern).
- KEINE Trust-on-First-Use-Patterns für externe MCP-Server.

# QUELLEN-ANFORDERUNGEN
- MCP-Spec (modelcontextprotocol.io), Anthropic-Security-Advisories.
- Invariant Labs / Lakera / Trail-of-Bits-Reports zu MCP-Security.
- Akademische Paper (arxiv 2025/2026) zu ATTESTMCP, Tool Poisoning.
- Cerbos-Dokumentation, NeMo-Guardrails-Dokumentation.

# OUTPUT-FORMAT
1. CVE-Mitigation-Tabelle (CVE / Komponente / Fix-Version / Validierung).
2. Cerbos-Policy-YAML mit 5 konkreten Policy-Beispielen.
3. Tool-Description-Scanner: Python-Code-Skeleton + Pattern-Liste.
4. Sandboxing-Empfehlung mit Docker-Compose-Snippet.
5. Audit-Log-Schema (PostgreSQL DDL).
6. Monitoring-Dashboard-Skizze (PromQL-Queries + Grafana-Panels).
7. ATTESTMCP-Migrationsplan (was heute, was 2027).

# VALIDIERUNG
- Mindestens 3 zitierte CVEs mit Fix-Versionen.
- Mindestens 5 Cerbos-Policy-Snippets.
- 1 quantitative Aussage zur Latenz-Auswirkung des Stacks.

# FOLLOW-UP-VORSCHLAG
- Vertiefung "MCP-Multi-Tenant-Isolation: pro-Workspace-Container vs.
  pro-Workspace-Cerbos-Policy".
```

---

### 17.16 Lösungsneutrale Architektur-Drittmeinung (Independent Architecture Review)

> **Zweck dieses Prompts:** Wir wollen die in Pflichtenheft v0.3 / Sektion 9.6 gewählte Architektur (V5: nanobot + Plane CE + LangGraph on-demand + NeMo Guardrails NIMs auf NVIDIA GB10) **kritisch von einer unabhängigen Drittmeinung** prüfen lassen. Der Prompt ist bewusst **lösungsneutral** formuliert — er beschreibt das Problem in Begriffen, die **keine Vorab-Festlegung** auf bestimmte Tools/Frameworks enthalten. Der/die Recherchierende soll auch alternative Architekturen vorschlagen können, die wir bislang nicht in Betracht gezogen haben.

```text
# ROLLE
Du bist Senior Solutions Architect mit 12+ Jahren Erfahrung in Multi-Agent-
Systemen, Self-Hosted AI-Infrastruktur und Enterprise-Integrationen. Du hast
in den letzten 18 Monaten produktive Agentic-AI-Systeme bei mehreren
Mittelstands-Kunden eingeführt (DACH-Markt) und kennst die typischen
Schmerzpunkte zwischen Hype und realer Produktion.

Du arbeitest evidenzbasiert, zitierst Primärquellen, kennzeichnest Spekulation
klar und vermeidest Vendor-Bias. Du hast keine kommerzielle Bindung an
Anbieter wie Anthropic, OpenAI, Microsoft, NVIDIA, HKUDS oder die genannten
OSS-Projekte. Du würdest mir explizit sagen, wenn ich auf dem Holzweg bin.

# MISSION
Liefere eine **unabhängige, kritische Drittmeinung** zur unten beschriebenen
Architektur-Hypothese (V5) für InnoSmith TaskPilot. Bewerte gegen heutigen
(April 2026) Stand der Best-Practices, Community-Konsens und neueste
Entwicklungen. Schlage Alternativen vor, **falls** sie objektiv überlegen
sind — aber nicht prophylaktisch.

Konkretes Output-Ziel: Ich soll am Ende der Lektüre eine fundierte Antwort
auf folgende drei Fragen haben:

1. Ist die gewählte Architektur (V5) eine vernünftige Wahl für April 2026?
   Wo schießt sie über das Ziel hinaus? Wo fehlt etwas Wesentliches?
2. Welche realistischen Alternativen würde ein erfahrener Architekt 2026
   ernsthaft prüfen, die ich übersehen habe?
3. Welche konkreten Risiken (technologisch, ökonomisch, ökologisch,
   reife-bedingt) sollte ich vor dem Phase-1-Start nochmals adressieren?

# PROBLEMRAUM (lösungsneutral beschrieben)

## Nutzer und Nutzungsprofil
- **1 Primärnutzer:** Senior-Berater Digitale Transformation & AI in der DACH-
  Region. 10–14 parallele Projekte (Kunden + intern + privat).
- **Spätere Skalierung (Phase 4):** Mandantenfähig für 5–20 Kundeninstanzen
  als jeweils dedizierte Deployments.
- **Budget:** Berater investiert ~2 fokussierte Halbtage/Woche, plus
  intensive Nutzung von Cursor/Claude-Code/Codex für Implementierung.
- **Hardware vorhanden:** NVIDIA GB10 Grace Blackwell Superchip mit 128 GB
  Unified Memory (DGX-Spark-Klasse) als dedizierte On-Prem-Inferenz-Node;
  Hostinger-PostgreSQL-Instanz; M365-Tenant.

## Kernaufgaben des Systems
1. **Hybrides Task-Management:** Cross-Project-Sicht über 10+ parallele Boards,
   wöchentliches Planungs-Ritual, Recurring-Tasks (wöchentlich/monatlich/jährlich).
   Heutige Praxis: MeisterTask-Pro mit täglich genutzter "Focus → This Week →
   Next Week → Waiting → This Month → Next Month → Beyond"-Pipeline.
2. **E-Mail-zu-Task-Brücke:** Microsoft 365 Copilot kategorisiert die Inbox
   bereits zuverlässig (Kategorien wie *Wichtig*, *Finanzen*, *Newsletter*).
   Es fehlt die Brücke "kategorisierte Mail → Task in Board". Pro Kategorie
   soll konfigurierbares Routing greifen, mit Approval-Gate.
3. **Mobile Quick-Capture:** Heute Self-Mail-Workaround. Gewünscht: Free-Form-
   Erfassung unterwegs (Text/Sprache), automatische Klassifikation,
   1-Klick-Bestätigung.
4. **Lernender Agent:** Soll Woche für Woche besser werden. Korrekturen des
   Beraters fließen in Memory zurück, sodass der Agent nach 4–8 Wochen weniger
   Approval-Rückfragen stellt. Lerneffekt muss messbar sein (KPIs).
5. **Strategische Begleitung:** Wöchentliche Review-Rituale (operativ),
   monatliche Reviews (semi-strategisch), jährliche Reviews (strategisch),
   plus kontinuierliche Strategie-Drift-Warnungen über Quartale hinweg.
6. **Kontinuierliche Re-Priorisierung:** Während des Tages eingehende Signale
   (Mails, Kalender-Konflikte, externe Webhook-Events) sollen proaktiv zu
   Re-Priorisierungs-Vorschlägen führen — nicht nur einmal pro Woche.
7. **Approval-Gates mit konfigurierbarer Autonomie pro Aufgabentyp:** 4 Stufen
   (Block / Approve-Required / Notify / Auto), pro Skill und Sub-Bedingung
   einzeln einstellbar, jederzeit zurücknehmbar.
8. **Datenschutz-Souveränität:** Mandantendaten dürfen die eigene Infrastruktur
   für sensitive Klassen nicht verlassen. Cloud-LLMs nur für Datenklassen
   `public` und `internal`. revDSG (Schweiz), DSGVO und EU AI Act sind
   einzuhalten.
9. **Open System:** Künftige Tools (z.B. Toggl Track für Time-Tracking,
   Runn für Capacity-Planning, Notion/Linear/Monday für Klienten-Boards,
   Obsidian/Joplin für Notizen, GitHub-Issues, Calendar) sollen sich ohne
   Architektur-Refactor anbinden lassen — Plugin-Pattern.
10. **Demo-Tauglichkeit (langfristig):** System soll im Vertriebskontext
    InnoSmith-Kundenprojekte als referenzierbares Demo-Asset dienen — aber
    erst, wenn es reif genug ist; kein Demo-Druck auf Phase 1.

## Constraints
- **Kein SaaS-Lock-in.** Daten müssen exportierbar/portierbar bleiben.
- **OSS bevorzugt** (AGPL/MIT/Apache 2.0), aber nicht dogmatisch.
- **Single-Person-Team** für Bau und Betrieb (Berater + Cursor-/Claude-Code-
  Agents), keine dedizierte DevOps-Mannschaft. → Wartungsaufwand muss niedrig
  bleiben.
- **Tag-1-produktiver Anspruch:** Nach 5 Werktagen müssen die ersten zwei
  Funktionen (Mail-Brücke + Mobile Quick-Capture) im realen Alltag nutzbar
  sein, parallel zum Bestandssystem (MeisterTask).

## Aktuelle Architektur-Hypothese (V5, zu prüfen!)
- **Agent-Runtime:** nanobot (HKUDS, MIT, Python 3.11+, ~4K LOC, Feb 2026)
  als Foundation. Bringt AgentLoop, Heartbeat, Cron, Subagent-Manager,
  AgentHook, MCP-Native-Client, Markdown-Memory (HISTORY.md + MEMORY.md)
  und 25+ Channel-Adapter mit.
- **Workflow-Orchestrator (on-demand):** LangGraph wird *erst dann* eingeführt,
  wenn ein konkreter Use-Case mehrstufige Verzweigungen mit State-Persistence
  zwingend fordert. Bis dahin reicht nanobot's AgentLoop.
- **Kanban-Backend:** Plane CE (AGPL-3.0, self-hosted) als Phase-1-Default.
  Backend-Adapter-Pattern abstrahiert das Backend, sodass Wechsel zu Vikunja
  oder zu Eigenbau (via Agentic Engineering) ohne Agent-Layer-Refactor
  möglich bleibt.
- **Memory:** Three-Tier-Hybrid — nanobot HISTORY.md (Session, append-only)
  + MEMORY.md (Workspace, "Dream Consolidation") + PostgreSQL/pgvector (HNSW)
  mit BGE-M3-Embeddings. Optionaler vierter Tier (Graphiti Temporal-KG) erst
  in Phase 2, wenn Beziehungsabfragen häufig.
- **LLM-Inferenz lokal (auf der GB10):** vLLM mit Qwen3-32B-NVFP4 für Batch-
  Tasks; SGLang für interaktive Agent-Inferenz. LiteLLM-Proxy als unified
  OpenAI-kompatibles Gateway. Cloud-LLMs (Claude Opus 4.7, Gemini 2.5 Pro,
  GPT-5.x) via LiteLLM nur für Datenklassen `public`/`internal`.
- **Safety-Layer auf der GB10:** Drei NVIDIA NeMo Guardrails NIMs als
  standalone Microservices: Content Safety, Topic Control,
  Jailbreak-Detection. Pre-/Post-Processing besonders für MCP-Tool-Outputs.
- **Authorization:** Cerbos (PEP) für ABAC-Policies vor jedem MCP-Tool-Call.
- **MCP-Layer:** TaskPilot ist sowohl MCP-Client (konsumiert Plane CE,
  Microsoft Graph, GitHub etc.) als auch MCP-Server (exponiert eigene Tools
  für Cursor / Claude Desktop).
- **UI:** Plane CE liefert das Kanban-UI. Schlankes Next.js-"Custom Cockpit"
  ergänzt nur, was Plane CE nicht abdeckt (Cross-Project-Pipeline, Daily
  Briefing, Agent-Console, Lern-Dashboard).
- **Mobile:** keine eigene App — Telegram-Bot (Phase 1) und Threema-Bot
  (Phase 2) als Quick-Capture-Channels via nanobot-Adapter.
- **Persistenz:** PostgreSQL mit Row-Level-Security für Multi-Tenant.

# RECHERCHE-FRAGEN (gewichtet)

## 1. Architektur-Gesamtbewertung (Gewicht: 30 %)
1.1 Wie würden erfahrene Architekten die Gesamtarchitektur (V5) im Vergleich
    zu typischen Alternativen 2026 einschätzen? Über-engineered, unter-
    engineered, oder angemessen?
1.2 Welche **alternativen Architektur-Patterns** würde ein unabhängiger
    Architekt für genau dieses Problem 2026 ernsthaft in Betracht ziehen,
    die ich bislang nicht erwähnt habe?
    Mögliche Beispiele zur Anregung (nicht erschöpfend):
    - Vollständig managed (z.B. Linear + Zapier + LangChain Cloud)
    - Reines Eigenbau-on-Top eines Frameworks (LlamaIndex Agents, AutoGen,
      CrewAI, ADK von Google, Microsoft Semantic Kernel, OpenAI Agent SDK)
    - Notion-basiert mit Custom-Agent-Layer
    - Obsidian-basiert mit lokalen Plugins
    - Fully-Local-Setup (z.B. n8n + Ollama + lokales Tool, ohne nanobot)
    - Hybrid-PaaS (Mendable, Inkeep, Sierra-Style Vertical Agents)
1.3 Wo bricht V5 in 6–12 Monaten am wahrscheinlichsten? Welche Komponente ist
    der "weakest link"?

## 2. Komponenten-Reife & Tragfähigkeit (Gewicht: 20 %)
2.1 nanobot (HKUDS, ~4K LOC, MIT, Feb 2026) als Foundation:
    - Wie ist die Community-Reputation per April 2026? Issues, PRs, Maintainer-
      Aktivität, Sicherheits-Audit-Berichte?
    - Gibt es vergleichbare/bessere Foundations? z.B. Pydantic AI, LlamaIndex
      Agents, smolagents (HuggingFace), CamelAI, MetaGPT, ADK (Google),
      Anthropic Agent SDK, OpenAI Agent SDK?
2.2 Plane CE als Default-Backend bei bekannten Feature-Lücken (kein natives
    Recurring, keine Pro-Workflows, eingeschränkte Custom Fields):
    - Gibt es bessere OSS-Alternativen für *individual-consultant-Use-Cases*
      mit 10+ Projekten in 2026, die ich übersehen habe?
    - Wie sehen typische Plane-CE-Adoptions-Stories aus (Erfolg / Schmerzen)?
2.3 LangGraph als optional-on-demand vs. anderen Orchestratoren (LlamaIndex
    Workflows, Burr, DSPy-Pipelines, AgentForge): Welche Wahl wäre 2026
    weniger Lock-in-anfällig?
2.4 NeMo Guardrails NIMs auf der GB10 — Reife, Latenz, Maintenance-Kosten;
    Alternativen wie Llama Guard, ShieldGemma, Granite Guardian, OpenAI
    Moderation API, oder selbstgebauter Filter?

## 3. Trends, Community-Konsens & jüngste Entwicklungen (Gewicht: 20 %)
3.1 Welche Architekturmuster sind in der Agentic-AI-Community per April 2026
    aktuell *trending* (positiv wie negativ)? Was wird kontrovers diskutiert?
3.2 Welche Tools sind in den letzten 6 Monaten *deutlich gewachsen* oder
    *deutlich gefallen* in Adoption?
3.3 Welche Veröffentlichungen (Blog-Posts erfahrener Architekten, ICLR/NeurIPS-
    Paper, KubeCon-Talks, AI Engineer Summit, etc.) der letzten 6 Monate
    sollten in die Bewertung einfließen?
3.4 Wie ändern sich die Empfehlungen mit Blick auf
    - die OpenAI Agent SDK (GA seit Q1 2026)
    - Anthropic's "Computer Use" + "Skills" + Project Memory (April 2026)
    - Microsoft Copilot Studio + Power Platform (April 2026)
    - Google ADK + A2A (Agent-to-Agent Protocol)
    - MCP-Spec-Updates (was hat sich seit September 2025 geändert?)

## 4. Tag-1-Produktivität & Onboarding-Reibung (Gewicht: 10 %)
4.1 Realistisch: Mit dem V5-Stack — wie schnell ist *tatsächlich* der erste
    produktive Nutzen für einen erfahrenen Solo-Berater erreicht?
4.2 Welche typischen Stolperfallen treten in der ersten Woche auf?
4.3 Gibt es einen radikal einfacheren Path-to-Production, der auf den ersten
    20 % der Funktionalität für 80 % des Nutzens setzt?

## 5. Datenschutz, Sicherheit, Compliance (Gewicht: 10 %)
5.1 Wie ist die V5-Architektur gegenüber bekannten Risiken bei Multi-LLM-
    Setups (Prompt Injection, Tool-Poisoning, Memory-Leakage, Supply-Chain)?
5.2 Speziell zur MCP-Security 2026: Welche realen Vorfälle / CVEs / Studien
    sind aktuell?
5.3 EU AI Act / revDSG / DSGVO: Welche Architektur-Entscheidungen würden in
    einem Audit kritisch angeschaut werden?
5.4 Vorschlag für Penetration-Test-Plan in Phase 4 (Mandantenfähigkeit)?

## 6. Wartungsaufwand für Solo-Setup (Gewicht: 5 %)
6.1 Realistischer Wartungsaufwand pro Monat für V5 (Updates, Patches,
    Schemata, Sicherheitsfixes)?
6.2 Wo sind die größten "Waste-Posten", die in einer Solo-Konstellation
    schnell zur Belastung werden?

## 7. Ökonomik & Ökologik (Gewicht: 5 %)
7.1 Erwartete monatliche LLM-Cloud-Kosten unter realistischen Annahmen?
7.2 Energie-/Wärmeprofil der GB10-DGX-Spark unter realistischer
    Heartbeat+Cron-Last?
7.3 Wann wird die Cloud günstiger als das Selber-Hosten?

# BEWERTUNGSKRITERIEN (gewichtet, Pflicht im Output)
- **Time-to-First-Value (Tag-1-Anspruch):** 20 %
- **Reife & Stabilität in Production:** 15 %
- **Lock-in-Risiko (Architektur-Reversibilität):** 15 %
- **Datenschutz / Compliance / Auditierbarkeit:** 15 %
- **Lernfähigkeit / Memory-Tauglichkeit:** 10 %
- **Wartungsaufwand für Solo-Operator:** 10 %
- **Open-System / Erweiterbarkeit:** 10 %
- **Demo-Tauglichkeit (langfristig):** 5 %

# ANTI-ANFORDERUNGEN (NICHT relevant für diese Recherche)
- Hersteller-Marketing oder Hype-Tonalität.
- Architekturen, die Cloud-Only sind und keine On-Prem-Option erlauben
  (z.B. ChatGPT Enterprise als alleinige Lösung).
- Architekturen, die bewusst Lock-in-anfällig sind (Closed-Source-Agent-
  Frameworks ohne Export-Pfad).
- Reine "best practice"-Wiederholungen ohne kritische Bewertung der
  Anwendbarkeit auf den Solo-Berater-Kontext.
- Architekturempfehlungen ohne konkrete Quellen.

# QUELLEN-ANFORDERUNGEN
- Primärquellen bevorzugt: Repo-READMEs, RFCs, MCP-Spec-Updates, offizielle
  Docs, peer-reviewed-Paper, Conference-Talks.
- Aktualität: Bevorzugt Q4 2025 oder neuer; alles ältere als 2024 nur, wenn
  es heute noch best-practice ist (dann mit Begründung).
- Gerne zitierte Communities: Hacker News, /r/LocalLLaMA, /r/MachineLearning,
  AI Engineer Summit, KubeCon AI, ETH/ EPFL/ TU München AI-Labs.
- Versions-Aktualität explizit nennen (Software-Stand zum Recherche-Datum).
- Bei widersprüchlichen Quellen: Diskrepanz benennen.
- Vendor-Pages mit Bias-Disclaimer.

# OUTPUT-FORMAT
- Sprache: Deutsch (technische Fachbegriffe Englisch belassen).
- Länge: ca. 3500–5500 Wörter.
- Pflicht-Sektionen:
  1. **Executive Summary** (300–500 Wörter, "wenn ich nichts anderes lesen
     würde, weiß ich Folgendes …")
  2. **V5-Gesamtbewertung** (Schulnote 1–6 mit Begründung)
  3. **Komponenten-Bewertung** (Tabelle pro V5-Komponente: Reife / Risiko /
     Empfehlung *Behalten / Tauschen / Aufschieben*)
  4. **Realistische Alternativ-Architekturen** (3–5 Vorschläge, je mit
     Mermaid-Architektur-Diagramm + Pro/Contra + Migrationsaufwand zu V5)
  5. **Trending / Community-Konsens 2026** (was sich gerade bewegt)
  6. **Tag-1-Produktivität-Bewertung** (Realistisches Szenario für die
     ersten 5 Werktage)
  7. **Risiken & blinde Flecken**, die ich übersehen haben könnte
  8. **Konkrete Verbesserungsempfehlungen** (10–15 priorisierte Items)
  9. **Was würden Sie persönlich tun?** (Pointierte Architektur-Empfehlung
     in 2–3 Absätzen, ohne Diplomatie)
  10. **Quellenliste** mit Zugriffsdatum

# VALIDIERUNG
- Self-Check am Ende: Was ist unsicher? Wo ist die Datenlage dünn? Welche
  Empfehlungen würden Sie selbst nochmals verifizieren wollen?
- Prüfen: Habe ich auf alle 7 Recherche-Frage-Blöcke geantwortet?
- Prüfen: Habe ich Vendor-Bias vermieden?
- Prüfen: Habe ich auch die "Anti-Hypothese" geprüft (V5 ist die falsche
  Wahl — was spricht dafür?)?

# FOLLOW-UP-VORSCHLAG
- 3–5 Folgerecherchen, die sich aus dem Ergebnis ergeben würden.
- Konkrete Hypothesen für ein 2-wöchiges Validierungsexperiment.
```

---

### 17.17 Greenfield-Architektur-Empfehlung (vollständig lösungsneutral)

> **Zweck dieses Prompts:** Im Unterschied zu Prompt 17.16 (der eine konkrete Architektur-Hypothese kritisch prüfen lässt) verzichtet dieser Prompt **vollständig auf jede Lösungsbeschreibung**. Es werden ausschliesslich Anforderungen, Constraints und der Problemkontext benannt. Der/die Recherchierende soll **von Null aus** beantworten, wie die Community 2026 dieses Problemfeld am besten lösen würde — ohne durch eine Vorab-Hypothese geframed zu sein. Ziel: blinde Flecken aufdecken, die durch die bisherige V5-Festlegung verborgen geblieben sein könnten, und sichtbar machen, was unabhängige Architekt:innen ohne Vorbelastung wirklich empfehlen würden.
>
> **Anti-Anweisung an den Researcher:** In diesem Prompt werden bewusst **keine** Tools, Frameworks, Bibliotheken oder konkrete Lösungs-Komponenten genannt — auch nicht in Beispielen. Wenn dir beim Lesen eine bestimmte Lösung in den Sinn kommt, prüfe, ob sie wirklich die *beste* aktuelle Antwort auf die Anforderung ist, oder ob sie nur die *bekannteste* ist. Schlage gerne mehrere konkurrierende Lösungspfade vor und mache die Trade-offs explizit.

```text
# ROLLE
Du bist Senior Solutions Architect mit 15+ Jahren Erfahrung in der
Gestaltung produktiver Software-Systeme für anspruchsvolle Einzelnutzer
und kleine Teams. Du hast in den letzten 24 Monaten mehrfach AI-gestützte
Produktivitäts-Systeme von Grund auf konzipiert (Greenfield) und kennst
sowohl die populären Lösungen als auch die unter dem Radar laufenden,
unterschätzten Alternativen. Du bist explizit nicht an einen Hersteller,
ein Framework oder ein bestimmtes Architektur-Paradigma gebunden.

Du arbeitest evidenzbasiert, zitierst Primärquellen, kennzeichnest
Spekulation klar und bist bereit, populären Hype zurückzuweisen, wenn
die Evidenz dafür dünn ist. Du würdest einen Auftraggeber explizit
warnen, wenn er sich in eine Sackgasse manövriert.

# MISSION
Entwirf — von Null aus, ohne Vorab-Festlegungen — wie das unten
beschriebene Problem im **April 2026** mit dem heutigen Stand der
Best-Practices, des Community-Konsenses und der jüngsten technologischen
Entwicklungen am besten gelöst werden sollte.

Konkretes Output-Ziel: Ich soll am Ende der Lektüre eine fundierte
Antwort auf folgende vier Fragen haben:

1. Welche Architektur-Pfade würde die Community 2026 für genau dieses
   Anforderungsprofil **wirklich** empfehlen — geordnet nach Reife,
   Tag-1-Tauglichkeit, Solo-Wartbarkeit und Zukunftssicherheit?
2. Welche Lösungs-Komponenten (Foundation-Frameworks, Backend-Systeme,
   Workflow-Engines, Memory-Schichten, Sicherheits-Layer, UI-Stacks)
   sind in 2026 die *konsensfähigen* Bausteine — und welche, die heute
   gehyped werden, würden Sie aktiv meiden?
3. Welche Trends der letzten 6–12 Monate verändern die Antwort auf diese
   Frage gerade — und was kommt voraussichtlich in den nächsten 12–18
   Monaten?
4. Was würden Sie persönlich heute bauen, wenn Sie für **mich** als Solo-
   Berater unter den unten genannten Constraints verantwortlich wären
   — und warum?

# PROBLEMRAUM (lösungsneutral)

## Nutzungs-Kontext und Akteure
- 1 Primärnutzer: Senior-Berater Digitale Transformation & AI im DACH-
  Raum. Solo-Operator. Verantwortet 10–14 parallele Projekte
  (Kunden + intern + privat).
- Skalierungsperspektive (Phase 4, 12–24 Monate): mandantenfähige
  Bereitstellung für 5–20 Kundeninstanzen — jeweils dediziert, mit
  strikter Daten-Isolation.
- Verfügbares Budget: ca. 2 fokussierte Halbtage pro Woche für Bau und
  Betrieb. Intensive Nutzung von AI-Coding-Assistenten ist gegeben.
- Verfügbare Hardware: dedizierte lokale Inferenz-Node mit ca. 128 GB
  Unified Memory (high-end Consumer/Workstation-AI-Klasse), zusätzlich
  externe Managed-PostgreSQL-Instanz, Microsoft-365-Tenant für Mail,
  Kalender und Identität.

## Funktionale Anforderungen (nach Prioritäten)
1. **Hybrides Aufgaben-Management mit projektübergreifender Pipeline-
   Sicht.** Heutige Praxis: tägliche Arbeit mit einer fest definierten
   Pipeline "Focus → diese Woche → nächste Woche → wartet → dieser Monat
   → nächster Monat → später", quer über alle Projekte. Diese Pipeline
   muss konfigurierbar sein (Stufen, Schwellen, Filter), nicht fest
   verdrahtet. Kanban-artige visuelle Darstellung wird erwartet.
2. **Wiederkehrende Aufgaben** (täglich/wöchentlich/monatlich/jährlich)
   müssen verlässlich erzeugt werden, ohne Halluzinationen, mit
   nachvollziehbarer Spur.
3. **E-Mail-zu-Aufgabe-Brücke.** Die Inbox wird **bereits heute** durch
   ein bestehendes, vom Nutzer genutztes System nach Kategorien
   sortiert (z.B. *Wichtig*, *Finanzen*, *Newsletter*, *Projekt-X*).
   Die neue Lösung soll diese vorhandene Klassifikation **nicht
   ersetzen**, sondern die Brücke schlagen: pro Mail-Kategorie ein
   konfigurierbares Routing zu einem Aufgaben-Vorschlag mit
   Approval-Gate.
4. **Mobile Quick-Capture.** Unterwegs erfasste Notizen (Text/Sprache)
   sollen automatisch klassifiziert und mit einem Klick bestätigt
   werden können. Heute: Self-Mail-Workaround.
5. **Lernender Agent.** Korrekturen des Beraters fliessen in das System
   zurück. Nach 4–8 Wochen soll der Agent messbar weniger Approval-
   Rückfragen stellen, weniger Fehlklassifikationen produzieren, bessere
   Priorisierungs-Vorschläge liefern. Lerneffekt muss quantifizierbar
   sein.
6. **Strategische Begleitung mit drei Ritual-Ebenen:** wöchentlich
   (operativ), monatlich (semi-strategisch), jährlich (strategisch),
   plus kontinuierliche Strategie-Drift-Warnungen über Quartale hinweg.
7. **Kontinuierliche Re-Priorisierung im Tagesverlauf.** Eingehende
   Signale (Mails, Kalender-Konflikte, externe Webhook-Events) führen
   proaktiv — nicht nur einmal pro Woche — zu Re-Priorisierungs-
   Vorschlägen.
8. **Approval-Gates mit konfigurierbarer Autonomie pro Aufgabentyp.**
   Vier Stufen: blockiert / Genehmigung erforderlich / nur Notify /
   voll autonom. Pro Aufgabentyp und Sub-Bedingung einzeln einstellbar,
   jederzeit zurücknehmbar. System soll selbst Vorschläge machen, wann
   eine Stufe erhöht werden kann.
9. **Tool-Integrations-Layer für externe Dienste.** Anbindung an
   bestehende Cloud-Services (Mail, Kalender, Dokumente, Versionierung,
   Time-Tracking, Capacity-Planning, Notiz-Systeme, Projekt-Boards
   anderer Anbieter) soll über ein einheitliches, austauschbares Muster
   erfolgen. Neue Tools müssen ohne Architektur-Refactor anbindbar sein.
10. **Multi-Modell-Routing.** Sensitive Mandantendaten dürfen die
    eigene Infrastruktur nicht verlassen und werden lokal verarbeitet.
    Für nicht-sensitive Aufgaben dürfen leistungsfähige Cloud-Modelle
    verwendet werden. Die Routing-Entscheidung muss konfigurierbar und
    transparent sein.
11. **Memory & Lernspeicher.** System merkt sich Präferenzen,
    Korrekturen, wiederkehrende Muster, Projektkontexte. Memory muss
    inspizierbar und editierbar sein (Vertrauen, Auditierbarkeit).
12. **Audit-Trail.** Sämtliche autonomen Entscheidungen werden
    nachvollziehbar protokolliert (manipulationssicher, append-only),
    damit sie im Falle eines Audits geprüft werden können.
13. **Mehrere Interaktions-Kanäle.** Web-Cockpit am Schreibtisch,
    Messenger-artige Quick-Capture unterwegs, Mail-Approval, ggf.
    Sprach-Input.
14. **Mandantenfähigkeit ab Phase 4.** Strikte Daten-Isolation
    zwischen Kundeninstanzen, separate Berechtigungsmodelle.

## Nicht-funktionale Anforderungen
- **Datenschutz:** Schweizer revDSG, EU-DSGVO, EU AI Act (greift für
  Hochrisiko-Klassen ab August 2026). Lokale Verarbeitung sensitiver
  Datenklassen ist verpflichtend.
- **Tag-1-Produktivität:** Erste Funktionen sollen nach wenigen
  Werktagen produktiv genutzt werden können — parallel zum bisherigen
  System (das nicht sofort abgelöst werden muss).
- **Schrittweise wachsende Architektur:** Jede Komponente muss einen
  klaren, nachvollziehbaren Mehrwert pro Lebenszyklus-Phase haben. Es
  darf kein "Big-Bang"-Stack entstehen, sondern ein System, das mit
  den Anforderungen mitwächst.
- **Solo-Wartbarkeit:** Maximaler Wartungsaufwand: ca. 4–6 Stunden /
  Monat für Updates, Patches und Sicherheitsfixes. Alles, was darüber
  hinausgeht, ist unrealistisch und gefährdet die Adoption.
- **Reversibilität / Lock-in-Vermeidung:** Daten exportierbar, Komponenten
  austauschbar, keine proprietären Datenformate ohne Export-Pfad.
- **Demo-Tauglichkeit (langfristig):** System soll im Vertriebskontext
  als referenzierbares Demo-Asset dienen können, sobald es reif genug
  ist. Kein Demo-Druck auf die ersten Phasen.

## Anti-Anforderungen (explizit ausgeschlossen)
- Reine SaaS-Lösungen, deren Anbieter sensitive Mandantendaten
  verarbeiten würden.
- Architekturen, die Cloud-Only sind und keine On-Prem-Option erlauben.
- Architekturen, die ein dediziertes DevOps-Team voraussetzen.
- Lösungen, die Daten in proprietären Formaten ohne Export-Pfad
  einsperren.
- Reine "best practice"-Wiederholungen ohne kritische Bewertung der
  Anwendbarkeit auf den Solo-Berater-Kontext.
- Hype-Empfehlungen ohne Evidenz-Basis (GitHub-Stars allein zählen
  nicht, wenn die Reife fehlt).

# RECHERCHE-FRAGEN (gewichtet)

## 1. Wie würde die Community dieses Problem 2026 lösen? (Gewicht: 30 %)
1.1 Welche Architektur-Pfade sind im Frühjahr 2026 in der Community
    (Hacker News, einschlägige Subreddits, AI-Engineer-Konferenzen,
    Tech-Blogs erfahrener Architekt:innen) für ein **vergleichbares
    Anforderungsprofil** (Solo-Operator, Multi-Project, Datenschutz,
    lernfähig, Open System) konsensfähig? Bitte 3–5 unterschiedliche
    Pfade nennen, jeweils mit Begründung *warum* sie konsensfähig sind.
1.2 Welche Pfade galten Mitte 2025 als konsensfähig und sind
    inzwischen als überholt oder gefährlich eingestuft? Begründung mit
    konkreten Belegen.
1.3 Welche unter dem Radar laufenden, unterschätzten Lösungsansätze
    würden Sie aus eigener Erfahrung empfehlen, die in der breiten
    Diskussion noch wenig erwähnt werden, aber substantielle Vorteile
    bieten?

## 2. Komponenten-Konsens 2026 (Gewicht: 25 %)
2.1 Für jede der folgenden architektonischen Schichten: Welche
    konkreten Lösungen / Patterns sind im April 2026 *konsensfähig*?
    Welche sind *gehyped, aber unreif*? Welche sind *bewährt, aber im
    Niedergang*?
    - Aufgaben-Backend / Kanban-System (selbst-gehostet oder
      datenschutzkonform managed)
    - Agent-Runtime / Agent-Framework (oder bewusster Verzicht
      darauf)
    - Workflow-Orchestrierung für deterministische Pipelines
    - Memory-Layer (Episodic / Semantic / Procedural)
    - Tool-Integrations-Standard (Protokoll für Tool-Aufrufe)
    - Lokale LLM-Inferenz (Engine, Modellfamilie, Quantisierungs-
      Format)
    - LLM-Routing-Layer (Cloud-Fallback-Steuerung)
    - Safety- und Guardrails-Layer
    - Authorization-Layer
    - Audit-Trail / Observability
    - UI-Layer (Cockpit-Front-End)
    - Mobile-Capture-Kanal
2.2 Pro Schicht: Welche Lösung würden Sie persönlich empfehlen — und
    welche würden Sie aktiv vermeiden, obwohl sie populär ist?

## 3. Trends der letzten 6–12 Monate (Gewicht: 15 %)
3.1 Welche technologischen, regulatorischen oder methodischen
    Entwicklungen der letzten 6–12 Monate verändern die Antwort auf
    die Architektur-Frage substantiell?
3.2 Welche Standardisierungs-Bewegungen (Protokolle, Spezifikationen)
    sind in den letzten Monaten relevant geworden — und wie reif sind
    sie wirklich?
3.3 Welche Sicherheits- und Compliance-Vorfälle der letzten Monate
    sollten in eine Architektur-Empfehlung einfliessen (CVEs,
    Audit-Berichte, Vorfälle bei vergleichbaren Systemen)?

## 4. Tag-1-Produktivität & Reibung (Gewicht: 15 %)
4.1 Welcher Lösungspfad bietet das beste Verhältnis zwischen
    "produktiver erster Nutzen nach wenigen Werktagen" und
    "tragfähige Architektur für die nächsten 2–3 Jahre"?
4.2 Welche typischen Stolperfallen würden Sie einen Solo-Operator
    bei den jeweils empfohlenen Pfaden erwarten lassen?
4.3 Gibt es einen radikal einfachen Pfad, der die ersten 80 % des
    Nutzens mit 20 % der Komplexität liefert — und was wäre der
    konkrete Migrations-Pfad in eine reichere Architektur?

## 5. Solo-Wartbarkeit & Reversibilität (Gewicht: 10 %)
5.1 Wie viele eigenständig zu wartende Komponenten halten Sie in
    diesem Setup für vertretbar — und warum?
5.2 Welcher Pfad führt zu der **niedrigsten Lock-in-Wahrscheinlichkeit**
    bei gleichzeitig hoher Funktionsabdeckung?

## 6. Demo- und Vertriebs-Tauglichkeit (Gewicht: 5 %)
6.1 Welche der empfohlenen Pfade lassen sich später am besten als
    Vertriebs-Demo nutzen — und welche Architektur-Entscheidungen
    in der ersten Phase würden diese Demo-Tauglichkeit gefährden?

# BEWERTUNGSKRITERIEN (gewichtet, im Output zu berücksichtigen)
- **Tag-1-Produktivität:** 25 %
- **Reife & Stabilität in Production:** 20 %
- **Solo-Wartbarkeit (max. 4–6 h / Monat):** 15 %
- **Reversibilität / Lock-in-Risiko:** 15 %
- **Datenschutz / Compliance / Auditierbarkeit:** 10 %
- **Lernfähigkeit / Memory-Tauglichkeit:** 10 %
- **Erweiterbarkeit / Open System:** 5 %

# QUELLEN-ANFORDERUNGEN
- Primärquellen bevorzugt: offizielle Docs, Repo-READMEs, RFCs,
  Spezifikations-Updates, peer-reviewed Paper, Konferenz-Talks.
- Aktualität: Bevorzugt letzte 6 Monate; ältere Quellen nur, wenn der
  Inhalt heute noch best-practice ist (mit Begründung).
- Bei widersprüchlichen Quellen: Diskrepanz explizit benennen und
  einen plausiblen Triangulations-Pfad vorschlagen.
- Bei Hersteller-Quellen: Bias-Disclaimer.

# OUTPUT-FORMAT
- Sprache: Deutsch (technische Fachbegriffe Englisch belassen).
- Länge: ca. 4000–6000 Wörter.
- Pflicht-Sektionen:
  1. **Executive Summary** (300–500 Wörter)
  2. **Architektur-Pfad A** (z.B. "minimaler Pragmatismus") — mit
     Mermaid-Diagramm + Pro/Contra + Wartungsaufwand-Schätzung +
     Reifegrad
  3. **Architektur-Pfad B** (z.B. "agentisch-zentral") — analog
  4. **Architektur-Pfad C** (z.B. "deterministisch-hybrid") — analog
  5. **Optional Pfad D / E** (falls weitere relevant) — analog
  6. **Komponenten-Konsens-Tabelle 2026** (pro Schicht: Konsens /
     Hype-warnung / Im-Niedergang)
  7. **Was würden Sie persönlich heute bauen?** (pointierte
     Empfehlung in 3–5 Absätzen, ohne Diplomatie, mit klarer
     Begründung warum **dieser** Pfad und **kein anderer**)
  8. **Migrations-Pfad** zwischen den vorgeschlagenen Pfaden (was
     ist später noch reversibel, was nicht)
  9. **Risiko-Matrix** (Top-10-Risiken mit Wahrscheinlichkeit,
     Auswirkung, Gegenmassnahme)
  10. **Trends-Ausblick 12–18 Monate** (was kommt, was sollte ich
      jetzt schon einplanen)
  11. **Quellenliste** mit Zugriffsdatum

# VALIDIERUNG (Self-Check vor Abgabe)
- Habe ich auf alle 6 Recherche-Frage-Blöcke geantwortet?
- Habe ich mindestens 3 unterschiedliche Architektur-Pfade
  ausgearbeitet — nicht nur einen?
- Habe ich Hype-Empfehlungen aktiv hinterfragt (mindestens eine
  populäre Lösung explizit zurückgewiesen, mit Begründung)?
- Habe ich Vendor-Bias vermieden (keine Schicht ohne Alternativ-
  Erwähnung)?
- Habe ich konkret benannt, **was ich als unsicher** einstufe?
- Habe ich die Anti-Hypothese geprüft ("Vielleicht ist meine
  Empfehlung falsch — was spricht dagegen?")?

# FOLLOW-UP-VORSCHLAG
- 3–5 vertiefende Folgerecherchen, gegliedert nach den vorgeschlagenen
  Architektur-Pfaden.
- Konkrete Hypothesen für ein 1–2-wöchiges Validierungsexperiment
  (Bake-Off zwischen 2–3 Pfaden mit echtem Mail-zu-Aufgabe-Use-Case
  als Akzeptanztest).
```

---

### 17.11 Hinweise zur iterativen Nutzung

Nach jedem Lauf ist es sinnvoll, Folgendes zu tun:

1. **Antworten in `docs/research/` ablegen** (z.B. `2026-04-25-perplexity-17.1-oss-kanban.md`) — versioniert, zitierbar.
2. **Ergebnisse triangulieren:** Pro Prompt mind. 2 Tools (z.B. Perplexity + Gemini Deep Research) — Diskrepanzen explizit markieren.
3. **ADR (Architecture Decision Record) erstellen** in `docs/adr/` für jede getroffene Entscheidung, die das Pflichtenheft beeinflusst.
4. **Pflichtenheft v0.2** nach Recherche-Runde aktualisieren (Sektion 16 offene Punkte schliessen, Sektion 9 Architektur-Empfehlung bestätigen oder revidieren).
5. **Kosten-Tracking:** Pro Deep-Research-Lauf typische Kosten und Dauer notieren (Lerneffekt für künftige Recherchen).

---

## 18. Frontend-Technologie-Entscheid für TaskPilot Cockpit (April 2026)

> **Status:** Offen — Prompt bereit für Deep Research  
> **Hintergrund:** Paradigmen-Entscheid getroffen: kein klassisches Kanban-Backend (MeisterTask/Plane/Vikunja), sondern ein eigenes agentisches Cockpit auf PostgreSQL. Die Frontend-Technologie-Wahl steht noch aus.  
> **Reflex-Evaluation:** Reflex (reflex.dev) wurde als Kandidat evaluiert. Problem: Drag-and-Drop (`rxe.dnd`) ist ein Enterprise-Feature mit "Built with Reflex"-Badge-Pflicht oder unbekannter Enterprise-Lizenzkosten. Das Badge ist visuell störend, die Lizenzkosten sind nicht öffentlich und vermutlich im Enterprise-Segment. Reflex ist daher nur geeignet, wenn DnD ohne Enterprise-Modul gebaut werden kann (HTML5 nativ oder React-Component-Wrapping — möglich, aber weniger polished).

### 18.1 Prompt: "Optimale Frontend-Technologie für ein agentisches Task-Management-Cockpit (Solo-Operator, 2026)"

```text
# KONTEXT

Ich baue ein "TaskPilot Cockpit" — eine purpose-built Web-UI für die
Zusammenarbeit eines Solo-IT-Beraters mit seinem AI-Agenten. Das Cockpit
ist KEIN generisches Kanban-Board, sondern ein agentisches Command Center
mit mehreren spezialisierten Panels.

Ich suche NICHT ein fertiges Tool oder Framework für Task-Management,
sondern die optimale Technologie-Kombination (Framework + Libraries),
um dieses Cockpit SELBST zu bauen.

# HARDWARE / DEPLOYMENT

- Self-Hosted auf ASUS GX10 (Linux, NVIDIA Blackwell, 128 GB)
- Docker Compose auf Single Host
- PostgreSQL als einzige Datenbank (Tasks, Agent-Jobs, Memory, Audit-Log)
- Single-User-System (Ein-Mann-IT-Beratung), kein Multi-Tenant
- Mobile-Nutzung sekundär (Telegram ist das mobile Interface)

# ENTWICKLER-PROFIL

- Primärsprache: Python (stark), JavaScript/TypeScript (vorhanden,
  aber nicht bevorzugt)
- Nutzt intensiv AI-Coding-Assistenten (Cursor, Claude Code, Codex)
- Wartungsbudget: 4-6 Stunden/Monat
- Erfahrung mit: Reflex (ein kleines Projekt), FastAPI, PostgreSQL,
  Docker, n8n, Obsidian, diverse Python-Frameworks
- Keine React/Vue/Angular-Tiefe — eher gelegentlicher Nutzer

# FUNKTIONALE ANFORDERUNGEN AN DAS COCKPIT

1. **Cross-Project-Pipeline (Killer-Feature):**
   - 7 Zeithorizont-Spalten: Focus | This Week | Next Week |
     Waiting for Feedback | This Month | Next Month | Beyond
   - Projektübergreifend: Tasks aus 10+ Projekten in einer Sicht
   - Drag-and-Drop zwischen Spalten UND zwischen Projekten
   - Tasks OHNE Datumszwang — die Position in der Pipeline IST
     die Priorisierung
   - Konfigurierbare Spalten (Anzahl, Namen, Reihenfolge)

2. **Task-Cards mit erweiterten Attributen:**
   - Titel, Markdown-Beschreibung, Checklisten, Tags
   - Optionale Fälligkeit (nicht erzwungen)
   - Projekt-Zugehörigkeit (mit farblicher Kennzeichnung)
   - Assignee: Ich / Agent / Gemeinsam
   - Datenklasse: public / internal / confidential / highly_confidential
   - LLM-Override: Welches Modell soll der Agent nutzen
   - Autonomie-Stufe: L0 (Block) / L1 (Approve) / L2 (Notify) / L3 (Auto)
   - Agent-Status: queued / running / awaiting-approval / completed / failed

3. **Agent-Queue-Panel (Real-Time):**
   - Live-Status aller laufenden Agent-Jobs
   - Fortschrittsanzeige (Prozent oder Phasen)
   - Aktuelles LLM-Modell und Token-Verbrauch pro Job
   - Elapsed Time
   - "Abbrechen"-Button für laufende Jobs

4. **Approval-Review-Panel:**
   - Rich Preview von Agent-Outputs (Mail-Entwürfe, Markdown-Dokumente,
     Checklisten)
   - Inline-Editing (Korrektur direkt im Preview)
   - Aktions-Buttons: Genehmigen / Editieren / Ablehnen
   - Korrektur-Feedback-Feld (Begründung für Memory)
   - Diff-View bei überarbeiteten Entwürfen

5. **Unified Inbox:**
   - Eingehende Signale aus verschiedenen Quellen (Mail, SIGNA-Trends,
     InvoiceInsight-Warnungen, Agent-Vorschläge)
   - Triage-Aktionen pro Signal: Quick Response / Task erstellen /
     Parken / Ignorieren
   - Quellfilter und Prioritätssortierung

6. **Filterbare Ansichten:**
   - Projektübergreifende Pipeline (Standard-Ansicht)
   - Einzelprojekt-Kanban (klassische Spalten pro Projekt)
   - "Meine Tasks" vs. "Agent-Tasks" vs. "Gemeinsam"
   - Status-Filter (offen / in Bearbeitung / erledigt)

7. **Memory-Dashboard (Phase 2, SHOULD):**
   - Gelernte Fakten inspizieren und korrigieren
   - Lern-KPIs: Trefferquoten, Korrekturen/Woche
   - Kosten-Zusammenfassung (Token-Verbrauch pro Modell/Woche)

8. **Skills-Overview (Phase 2, SHOULD):**
   - Liste aktiver Agent-Skills mit Trefferquoten
   - Verbesserungstrends über Zeit

# NICHT-FUNKTIONALE ANFORDERUNGEN

- NFA-1: Self-Hosted, Docker Compose, kein Cloud-Zwang
- NFA-2: PostgreSQL als einzige Datenbank
- NFA-3: Real-Time-Updates vom Agent-Backend (Agent schreibt in PostgreSQL,
  Cockpit zeigt Änderungen sofort)
- NFA-4: Wartbar mit 4-6h/Monat — minimale Framework-Komplexität
- NFA-5: Single-User, kein Auth-System nötig (einfaches Token reicht)
- NFA-6: AI-Generierbarkeit — das Framework muss gut von AI-Coding-Tools
  (Cursor, Claude Code, Codex) generierbar sein, d.h. große Trainingsbasis
  und klare Patterns
- NFA-7: Responsive, aber Mobile-First ist NICHT nötig (Desktop-primär,
  Telegram für Mobile)
- NFA-8: Dark Mode wäre nice, kein MUST
- NFA-9: Performance: Flüssiges DnD auch bei 100+ sichtbaren Task-Cards
- NFA-10: Zukunftssicherheit: Framework sollte aktiv gepflegt sein,
  stabile API, keine ständigen Breaking Changes

# WAS ICH BEREITS EVALUIERT HABE

1. **Reflex (reflex.dev):**
   - Vorteile: Pure Python, 28K Stars, 60+ Komponenten, FastAPI-Backend,
     Background Tasks für Real-Time, ich habe bereits Erfahrung damit
   - Problem: Drag-and-Drop (rxe.dnd) ist Enterprise-Feature mit
     Badge-Pflicht oder unbekannter Lizenz. Badge ist visuell störend.
   - Workaround möglich: HTML5 DnD nativ oder React-Component wrappen,
     aber weniger polished
   - Skalierung: WebSocket-basiert, wird langsam bei 3+ Usern — aber
     das ist hier irrelevant (Single-User)
   - Breaking Changes und Doku-Lücken als Risiko berichtet

2. **Next.js + React + Tailwind:**
   - Im Pflichtenheft v0.9 als Default-Kandidat genannt
   - Vorteile: Riesiges Ökosystem, exzellente DnD-Libraries
     (@dnd-kit, @hello-pangea/dnd), beste AI-Generierbarkeit,
     maximale UI-Kontrolle
   - Nachteil: JavaScript/TypeScript als Hauptsprache,
     Berater bevorzugt Python

3. **Svelte/SvelteKit:**
   - Erwähnt als Alternative zu Next.js
   - Vorteile: Weniger Boilerplate als React, reaktives Modell
   - Nachteil: Kleineres Ökosystem, weniger AI-Training-Daten

# FRAGEN, DIE BEANTWORTET WERDEN SOLLEN

1. **Framework-Vergleich für diesen spezifischen Anwendungsfall:**
   Vergleiche mindestens diese Optionen systematisch:
   - Reflex (Python, ohne Enterprise-DnD)
   - Next.js / React + Tailwind (TypeScript)
   - SvelteKit + Tailwind (TypeScript/JavaScript)
   - NiceGUI (Python, basiert auf Quasar/Vue)
   - Andere Python-First-Frameworks 2026 (Mesop, Taipy, Panel, Solara)
   - FastAPI + htmx + Alpine.js (Server-Side, Python-Backend)

   Bewertungskriterien:
   a) Drag-and-Drop-Fähigkeit (Cross-Container, Multi-Column Kanban)
   b) Real-Time-Update-Fähigkeit (Agent-Status, Live-Fortschritt)
   c) Wartbarkeit (Lernkurve, API-Stabilität, Ökosystem)
   d) AI-Generierbarkeit (Trainingsbasis, Cursor/Claude-Support)
   e) PostgreSQL-Integration (ORM, Query-Builder, Raw SQL)
   f) Komponentenreichtum (Data Tables, Charts, Markdown-Renderer,
      Inline-Editor)
   g) Eignung für Solo-Entwickler mit 4-6h/Monat Wartung
   h) Community-Grösse und Überlebenswahrscheinlichkeit 2028+

2. **Drag-and-Drop-Libraries 2026:**
   - Welche DnD-Bibliotheken funktionieren am besten für
     Multi-Column-Kanban mit Cross-Container-Movement?
   - Vergleich: @dnd-kit vs. @hello-pangea/dnd vs. react-beautiful-dnd
     (deprecated?) vs. pragmatic-drag-and-drop (Atlassian) vs. andere
   - Gibt es Python-native DnD-Lösungen, die produktionsreif sind?
   - Wie gut funktioniert DnD über Reflex's React-Component-Wrapping?

3. **Real-Time-Patterns für Agent-Status-Updates:**
   - SSE vs. WebSocket vs. Long-Polling für Single-User-Szenario?
   - Wie implementiert man "Agent schreibt in PostgreSQL, UI zeigt
     Änderungen in <2 Sekunden" mit minimalem Aufwand?
   - PostgreSQL LISTEN/NOTIFY als Real-Time-Trigger — praktikabel?

4. **Python-First-Optionen jenseits von Reflex:**
   - NiceGUI: Hat es natives DnD? Wie reif ist es 2026?
   - Taipy: Eignung für interaktive Dashboards mit DnD?
   - FastAPI + htmx + Alpine.js: Wie viel JavaScript braucht man
     wirklich für DnD in diesem Stack?
   - Gibt es 2026 ein Python-Framework, das DnD, Real-Time UND
     gute AI-Generierbarkeit kombiniert — OHNE Enterprise-Lizenz?

5. **AI-Generierbarkeit als Entscheidungsfaktor:**
   - Welches Framework/Library-Kombination hat die grösste
     Trainingsbasis in LLM-Modellen (Stand April 2026)?
   - Erfahrungsberichte: Wie gut generieren Cursor/Claude Code/Codex
     komplette Kanban-Boards in den verschiedenen Frameworks?
   - Gibt es Benchmarks oder Community-Erfahrungen zum Thema
     "AI-generierter Code in Framework X"?

6. **Build-or-Wrap-Entscheid für Reflex:**
   - Falls Reflex gewählt wird: Wie aufwändig ist es, @dnd-kit oder
     @hello-pangea/dnd als Custom React Component in Reflex zu wrappen?
   - Gibt es Community-Beispiele für Kanban-Boards in Reflex OHNE
     Enterprise-Modul?
   - Lohnt sich der Wrapping-Aufwand, oder ist der Vorteil von
     "Pure Python" kleiner als gedacht, wenn man React-Components
     wrappen muss?

# FORMAT DER ANTWORT

- Pro Framework: Bewertungstabelle mit Scores (1-5) für jedes
  Kriterium (a-h)
- Klare Empfehlung mit Begründung
- Zweitbeste Option als Fallback
- Konkrete Starter-Architektur (welche Libraries, welche Folder-
  Struktur, wie verbindet sich Frontend mit PostgreSQL)
- Bekannte Risiken und Mitigationen
- Anti-Hypothese: "Warum könnte meine Empfehlung falsch sein?"

# QUALITÄTS-CHECKLISTE (vor Abgabe prüfen)

- Wurden alle 6 Fragen beantwortet?
- Wurde Reflex fair bewertet (nicht nur Nachteile)?
- Wurde mindestens eine populäre Lösung explizit zurückgewiesen
  (mit Begründung)?
- Wurden konkrete Library-Versionen und GitHub-Stars genannt?
- Wurde die AI-Generierbarkeit mit konkreten Beispielen belegt?
- Wurde die DnD-Fähigkeit mit realen Kanban-Beispielen belegt?
```

### 18.2 Follow-Up-Prompts (nach erstem Research-Lauf)

**Follow-Up A — Deep-Dive auf den Gewinner:**
```text
Basierend auf der Empfehlung [FRAMEWORK X]: Zeige mir eine konkrete
Starter-Architektur für das TaskPilot Cockpit:
- Folder-Struktur
- PostgreSQL-Schema für Tasks, Agent-Jobs, Projects, Pipeline-Positionen
- Wie verbindet sich das Frontend mit der Datenbank?
- Wie implementiert man die Cross-Project-Pipeline mit DnD?
- Wie funktionieren Real-Time-Updates vom Agent-Backend?
- Code-Beispiel: Eine minimale Task-Card mit DnD in einer Spalte
```

**Follow-Up B — Reflex-spezifisch (falls Reflex empfohlen wird):**
```text
Konkreter Deep-Dive: Wie wrappe ich @dnd-kit in Reflex als Custom
React Component, sodass ich ein Kanban-Board mit 7 Spalten und
Cross-Container-Drag-and-Drop bekomme? Zeige mir:
- Den Wrapping-Code (Python-Seite)
- Die React-Component-Definition
- State-Management für die Spalten-Zuordnung
- Bekannte Pitfalls beim Wrapping von DnD-Libraries in Reflex
```

**Follow-Up C — Performance-Validierung:**
```text
Kann das empfohlene Framework mit 100+ sichtbaren Task-Cards in 7
Spalten flüssig arbeiten (DnD, Scroll, Filter)? Gibt es Benchmarks
oder Erfahrungsberichte? Was sind die typischen Performance-Bottlenecks
bei Kanban-Boards mit vielen Cards?
```

---
