# Ausbauplan: Proaktive Assistenz-Features

Stand: 2. Juli 2026 — Kandidaten aus der Best-Practice-Recherche (FinkBot, amaiko,
Orbis, Daemora, Privault). Gemeinsames Muster erfolgreicher persönlicher
Assistenz-Systeme: Die grösste Wertschöpfung nach der E-Mail-Triage liegt in
**proaktiven, geplanten Agenten-Läufen** statt rein reaktiver Verarbeitung.
Alle vier Kandidaten sind mit dem bestehenden MCP-Stack umsetzbar und bleiben
vollständig on-prem (lokales Qwen via Ollama).

Bewusst zurückgestellt (Entscheid vom 2. Juli 2026): zuerst werden die
Feinschliff-Pakete der Hermes-Gesamtintegration umgesetzt.

## 1. Tagesbriefing im Cockpit (empfohlen als erstes)

**Nutzen:** In der Community durchgängig als «highest-ROI»-Baustein bezeichnet.
Schliesst die Lücke aus Pflichtenheft-Szenario A (Wochenplanung am Montagmorgen —
Agenda vorhanden, Agent-Vorschlag fehlt).

**Idee:** Ein geplanter Agent-Job (z. B. werktags 06:30) kompiliert:

- Heutige Termine (`list_calendar_events`) inkl. Vorbereitungshinweisen
- Offene Fokus-Tasks und heute fällige Aufgaben (`list_tasks`)
- Wichtige ungelesene E-Mails seit gestern (Triage-Ergebnisse, `needs_review`)
- Fällige HITL-Freigaben (wartende Drafts, Regel-Vorschläge)
- Optional: SIGNA-Signale des Tages, InvoiceInsight-Warnungen

**Umsetzung:** Neuer `job_type='daily_briefing'` im bestehenden Scheduler-Loop;
Ergebnis als Markdown im Cockpit (neue Karte) und optional als Notification.
Autonomie: L2 (führt aus, informiert) — keine externe Kommunikation.

## 2. Meeting-Vorbereitung (Dossier vor Terminen)

**Nutzen:** Klassischer CoPilot-Mehrwert, datenschutzkonform mit lokalem LLM.

**Idee:** 30–60 Minuten vor einem Termin mit externen Teilnehmern erstellt der
Agent ein Dossier: Pipedrive-Historie (Deals, Notizen, Aktivitäten),
E-Mail-Verlauf mit dem Kontakt (`search_sender_history`), letzte Themen,
offene Tasks, optional SIGNA-Signale zur Organisation.

**Umsetzung:** Scheduler prüft `list_calendar_events` auf bevorstehende Termine
mit externen Teilnehmern; `job_type='meeting_prep'`; Ergebnis als Notification
+ Cockpit-Karte. Alle Quellen existieren bereits als MCP-Tools.

## 3. Follow-up-Erkennung (unbeantwortete gesendete Mails)

**Nutzen:** «Unusual comms gaps» — kein Faden reisst mehr ab.

**Idee:** Gesendete Mails, auf die nach X Tagen (konfigurierbar, z. B. 5
Arbeitstage) keine Antwort einging, werden erkannt und als Vorschlag/Task
angeboten («Nachfassen bei …?»).

**Umsetzung:** Der Style-Store-Sync liest die Sent Items bereits täglich —
dieselbe Datenbasis um `conversationId`-Abgleich mit der Inbox erweitern.
Deterministische Erkennung (kein LLM nötig), LLM nur für den optionalen
Nachfass-Entwurf (dann Zwei-Pass-Draft-Pfad, HITL-L1).

## 4. Meeting-Nachbereitung (Transkript → Protokoll + Action Items)

**Nutzen:** 15 Minuten Nacharbeit pro Call entfallen; Action Items landen
direkt als Task-Vorschläge im Board.

**Idee:** Nach Teams-Meetings mit Transkript erstellt der Agent Protokoll +
Action-Item-Liste; erkannte Aufgaben werden als `needs_review`-Tasks
vorgeschlagen.

**Umsetzung:** `get_meeting_transcript` existiert im mcp-graph bereits und wird
nirgends genutzt. Der Job-Typ `meeting_summary` ist im Schema
(`chat_triage.triage_class`) sogar schon vorgesehen, aber nie implementiert.
Scheduler erkennt beendete Meetings; `job_type='meeting_summary'`.

## Empfohlene Reihenfolge

1. **Tagesbriefing** — grösster Alltagsnutzen, geringste Komplexität (nur lesen).
2. **Meeting-Nachbereitung** — Baustein (`get_meeting_transcript`) liegt brach,
   Schema ist vorbereitet.
3. **Follow-up-Erkennung** — deterministisch, baut auf Style-Store-Sync auf.
4. **Meeting-Vorbereitung** — höchster Demo-/Showcase-Wert, aber am meisten
   Orchestrierung (Zeitfenster, externe Teilnehmer erkennen).

Alle vier eignen sich auch als Showcase-Features für Kunden-Demos
(«Was kann ein persönlicher KI-Assistent mit lokalem LLM?»).
