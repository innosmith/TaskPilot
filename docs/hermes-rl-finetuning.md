# Hermes RL-Fine-Tuning — Vorbereitung (gegated, NICHT aktiv)

Stand: Juni 2026. Dieses Dokument beschreibt die **vorbereitete, aber bewusst
deaktivierte** Datenbasis für ein späteres Reinforcement-/Präferenz-Fine-Tuning
des lokalen Hauptmodells (`qwen3.6:latest`). Es ist Teil von Tier 3 des
Hermes-Potenzial-Reviews und dient als Doku + Gate, **nicht** als laufender Prozess.

## Warum gegated

- **Kein Online-Training im Produktivbetrieb.** Fine-Tuning läuft ausschliesslich
  offline, manuell angestossen, auf einer Kopie der Daten. TaskPilot selbst trainiert
  nichts automatisch.
- **Datenschutz-Souveränität.** Trajektorien können sensible Inhalte (E-Mails,
  Kundendaten) enthalten. Vor jeder Nutzung als Trainingsdaten ist eine Sichtung/
  Anonymisierung Pflicht. Daten verlassen die lokale Maschine nicht.
- **Risiko/Nutzen.** Solange Skills, Memory, Few-Shot-Recall und gelernte Regeln
  das Verhalten ausreichend steuern, ist ein Modell-Fine-Tuning nicht nötig. Die
  Datensammlung läuft trotzdem mit, damit die Option offen bleibt.

## Datenquellen (bereits gesammelt)

1. **Trajektorien** — `~/.hermes/trajectories/`
   - `trajectory_samples.jsonl` (erfolgreiche Konversationen)
   - `failed_trajectories.jsonl` (fehlgeschlagene Läufe)
   - Gebündelt über den Trajektorien-Pfad-Shim in `hermes_worker._install_trajectory_path_shim()`.
   - Jede Zeile = vollständige Nachrichten-Historie inkl. Tool-Calls und Ergebnis.

2. **Feedback-Labels** — PostgreSQL-Tabelle `agent_feedback`
   - `feedback_type`: `draft_edit`, `approved_clean`, `triage_reclass`, `rejected`,
     `thumbs_up`, `thumbs_down`.
   - Liefert das **Reward-/Präferenzsignal**: `approved_clean` / `thumbs_up` = positiv,
     `rejected` / `thumbs_down` / starke `draft_edit` = negativ.

3. **Episodisches Gedächtnis** — `agent_episodes` (mit `was_corrected`)
   - Korrigierte Episoden sind hochwertige Negativ-/Korrektur-Paare.

4. **Gelernte Regeln** — `learned_rules` (Status `active`)
   - Können als zusätzliche Instruktions-/Constraint-Beispiele dienen.

## Skizze des Offline-Workflows (manuell, nicht implementiert)

```text
1. Export: trajectory_samples.jsonl + agent_feedback (join über job/episode) →
   gelabelte (prompt, response, reward)-Tripel.
2. Sichtung + Anonymisierung (PII entfernen, Kundennamen redigieren).
3. Präferenzpaare bilden (chosen vs. rejected) für DPO/ORPO, ODER
   gefilterte SFT auf nur positiven Trajektorien.
4. Training offline (z. B. LoRA auf qwen3.6) auf der lokalen GPU.
5. Eval gegen einen gehaltenen Triage-/Chat-Testsatz, bevor irgendetwas
   produktiv übernommen wird.
```

## Aktueller Gate-Status

| Komponente | Status |
|---|---|
| Trajektorien-Sammlung | **aktiv** (Shim schreibt nach `~/.hermes/trajectories/`) |
| Feedback-Labels | **aktiv** (`agent_feedback` wird befüllt) |
| Export-/Trainings-Pipeline | **nicht implementiert** (bewusst) |
| Automatisches/Online-Training | **deaktiviert** (kein Code-Pfad) |

Hermes' `rl`-Toolset bleibt **nicht** in der Agent-Allowlist
(`LOCAL_CORE_TOOLSETS` in `hermes_worker.py`). Eine Aktivierung wäre eine bewusste,
separate Entscheidung mit eigenem Review.
