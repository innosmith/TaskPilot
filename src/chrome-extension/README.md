# TaskPilot LinkedIn Sync — Chrome Extension

LinkedIn-Kontakte mit einem Klick in Pipedrive synchronisieren.  
Powered by [InnoSmith.ch](https://innosmith.ch) — AI-Agenten & Automation.

## Features

- **Neuer Kontakt:** Profildaten (Name, Rolle, Firma, Ort, Profilbild) von einer LinkedIn-Profilseite extrahieren und in Pipedrive als Person anlegen.
- **Bestehender Kontakt:** Erkennt automatisch, ob die Person bereits in Pipedrive existiert (per LinkedIn-URL oder Name). Zeigt Aenderungen als Diff an und ermoeglicht selektive Aktualisierung.
- **Multi-Org:** Bei Personen mit mehreren Arbeitgebern kann die gewuenschte Organisation ausgewaehlt werden.
- **Profilbild-Sync:** LinkedIn-Profilbild wird automatisch nach Pipedrive uebertragen.

## Voraussetzungen

- Google Chrome (oder Chromium-basierter Browser)
- TaskPilot-Backend laeuft (lokal oder remote)
- Pipedrive-Integration in TaskPilot konfiguriert
- Pipedrive Person-Feld "LinkedIn" existiert (Standard in den meisten Setups)

## Installation (Developer Mode)

1. Chrome oeffnen → `chrome://extensions/`
2. **Entwicklermodus** oben rechts aktivieren
3. **Entpackte Erweiterung laden** klicken
4. Den Ordner `src/chrome-extension/` auswaehlen
5. Die Extension erscheint in der Toolbar

## Konfiguration

1. Auf das Extension-Icon klicken → Zahnrad-Icon (oder Rechtsklick → "Optionen")
2. **Backend-URL** eingeben (z.B. `http://localhost:8000`)
3. **API-Token** eingeben:
   - TaskPilot im Browser oeffnen
   - Browser DevTools oeffnen (F12) → Console
   - `localStorage.getItem('token')` eingeben → Token kopieren
4. **Speichern** klicken
5. Optional: **Verbindung testen** klicken

## Verwendung

### Neuer Kontakt erstellen

1. LinkedIn-Profilseite oeffnen (`linkedin.com/in/...`)
2. Extension-Popup oeffnen (Icon klicken)
3. Extrahierte Daten pruefen/anpassen
4. Organisation im Dropdown waehlen
5. "Kontakt erstellen" klicken
6. Erfolg → Link zu Pipedrive

### Bestehenden Kontakt aktualisieren

1. LinkedIn-Profilseite oeffnen
2. Extension erkennt automatisch den bestehenden Pipedrive-Kontakt
3. Aenderungen werden als Checkliste angezeigt (Rolle, Organisation, Profilbild)
4. Gewuenschte Aenderungen anhaekeln
5. "Ausgewaehlte Felder aktualisieren" klicken

## Architektur

```
Chrome Extension (Manifest V3)
  ├── Content Script     → DOM-Extraktion auf linkedin.com/in/*
  ├── Popup              → UI mit 3 Zustaenden (neu/existiert/update)
  ├── Background Worker  → API-Calls an TaskPilot Backend (umgeht CORS)
  └── Options            → Backend-URL + Token Konfiguration

TaskPilot Backend
  ├── POST /api/pipedrive/linkedin-lookup  → Duplikat-Check
  └── POST /api/pipedrive/linkedin-sync    → Create / Update Person
```

## Datenschutz

- Daten werden nur an das konfigurierte TaskPilot-Backend gesendet (self-hosted)
- Keine Drittpartei-Server, kein SaaS, keine Telemetrie
- Nur manuell ausgeloest (kein automatisches Scraping)
- Nur sichtbare Profildaten werden extrahiert (kein LinkedIn-API-Zugriff)
