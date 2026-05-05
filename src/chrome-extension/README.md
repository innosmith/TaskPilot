# TaskPilot LinkedIn Sync — Chrome Extension

LinkedIn-Kontakte mit einem Klick in Pipedrive synchronisieren.  
Powered by [InnoSmith.ch](https://innosmith.ch) — AI-Agenten & Automation.

## Features

- **Neuer Kontakt:** Profildaten (Name, Rolle, Firma, Ort, Profilbild) von einer LinkedIn-Profilseite extrahieren und in Pipedrive als Person anlegen.
- **Bestehender Kontakt:** Erkennt automatisch, ob die Person bereits in Pipedrive existiert (per LinkedIn-URL oder Name). Zeigt Änderungen als Diff an und ermöglicht selektive Aktualisierung.
- **Multi-Org:** Bei Personen mit mehreren Arbeitgebern kann die gewünschte Organisation ausgewählt werden.
- **Profilbild-Sync:** LinkedIn-Profilbild wird automatisch nach Pipedrive übertragen.

## Voraussetzungen

- Google Chrome (oder Chromium-basierter Browser)
- TaskPilot-Backend läuft (lokal oder remote)
- Pipedrive-Integration in TaskPilot konfiguriert
- Pipedrive Person-Feld "LinkedIn" existiert (Standard in den meisten Setups)

## Installation (Developer Mode)

1. Chrome öffnen → `chrome://extensions/`
2. **Entwicklermodus** oben rechts aktivieren
3. **Entpackte Erweiterung laden** klicken
4. Den Ordner `src/chrome-extension/` auswählen
5. Die Extension erscheint in der Toolbar

## Konfiguration

1. Auf das Extension-Icon klicken → Zahnrad-Icon (oder Rechtsklick → "Optionen")
2. **Backend-URL** eingeben (z.B. `https://tp.innosmith.ai` oder `http://localhost:8000`)
3. **API-Key** generieren und eingeben:
   - TaskPilot im Browser öffnen → **Einstellungen → Integrationen**
   - Im Abschnitt **Browser-Extension** auf **"API-Key generieren"** klicken
   - Den angezeigten Key (beginnt mit `tpk_`) kopieren
   - In der Extension einfügen
4. **Cloudflare Access** (optional, falls Backend geschützt):
   - Cloudflare Zero Trust → Access → Service Auth → **Service Token erstellen**
   - Client-ID und Client Secret in der Extension eintragen
5. **Speichern** klicken
6. **Verbindung testen** klicken

## Verwendung

### Neuer Kontakt erstellen

1. LinkedIn-Profilseite öffnen (`linkedin.com/in/...`)
2. Extension-Popup öffnen (Icon klicken)
3. Extrahierte Daten prüfen/anpassen
4. Organisation im Dropdown wählen
5. "Kontakt erstellen" klicken
6. Erfolg → Link zu Pipedrive

### Bestehenden Kontakt aktualisieren

1. LinkedIn-Profilseite öffnen
2. Extension erkennt automatisch den bestehenden Pipedrive-Kontakt
3. Änderungen werden als Checkliste angezeigt (Rolle, Organisation, Profilbild)
4. Gewünschte Änderungen anhäkeln
5. "Ausgewählte Felder aktualisieren" klicken

## Architektur

```
Chrome Extension (Manifest V3)
  ├── Content Script     → DOM-Extraktion auf linkedin.com/in/*
  ├── Popup              → UI mit 3 Zuständen (neu/existiert/update)
  ├── Background Worker  → API-Calls an TaskPilot Backend
  └── Options            → Backend-URL + API-Key + Cloudflare Access

TaskPilot Backend
  ├── POST /api/pipedrive/linkedin-lookup  → Duplikat-Check
  └── POST /api/pipedrive/linkedin-sync    → Create / Update Person
```

## Datenschutz

- Daten werden nur an das konfigurierte TaskPilot-Backend gesendet (self-hosted)
- Keine Drittpartei-Server, kein SaaS, keine Telemetrie
- Nur manuell ausgelöst (kein automatisches Scraping)
- Nur sichtbare Profildaten werden extrahiert (kein LinkedIn-API-Zugriff)
- Cloudflare Access Service Token schützt die API zusätzlich
