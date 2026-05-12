#!/usr/bin/env python3
"""AI-Explorations-Audit fuer TaskPilot.

Nutzt browser-use mit Qwen 3.5 35B (Ollama, multimodal) um die App
visuell zu pruefen und einen strukturierten Report zu generieren.

Ausfuehrung:
    make test-explore
    # oder: python tests/ai-audit/run_audit.py

Voraussetzungen:
    pip install browser-use langchain-ollama
    Ollama laeuft mit qwen3.5:latest

Umgebungsvariablen:
    TP_E2E_BASE_URL  - App-URL (default: http://localhost:3100)
    TP_TEST_EMAIL    - Login-Email
    TP_TEST_PASSWORD - Login-Passwort (MUSS gesetzt sein)
    TP_AUDIT_MODEL   - Ollama-Modell (default: qwen3.5:latest)
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

REQUIRED_PACKAGES = ["browser_use", "langchain_ollama"]

def check_dependencies():
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Fehlende Pakete: {', '.join(missing)}")
        print("Installiere mit: pip install browser-use langchain-ollama")
        sys.exit(1)


BASE_URL = os.environ.get("TP_E2E_BASE_URL", "http://localhost:3100")
LOGIN_EMAIL = os.environ.get("TP_TEST_EMAIL", "admin@innosmith.ai")
LOGIN_PASSWORD = os.environ.get("TP_TEST_PASSWORD")
AUDIT_MODEL = os.environ.get("TP_AUDIT_MODEL", "qwen3.5:latest")

REPORT_DIR = Path(__file__).parent / "reports"

AUDIT_SCENARIOS = [
    {
        "name": "Navigations-Audit",
        "task": f"""
        1. Oeffne {BASE_URL}/login
        2. Logge dich ein mit Email '{LOGIN_EMAIL}' und dem Passwort aus der Umgebung
        3. Nach dem Login, navigiere zu jeder dieser Seiten und berichte ob sie korrekt laden:
           - Cockpit (Startseite /)
           - Pipeline (/pipeline)
           - Projekte (/projects)
           - Inbox (/inbox)
           - Agenten (/agenten)
           - Einstellungen (/einstellungen)
        4. Fuer jede Seite: Wird sie korrekt angezeigt? Gibt es Fehlermeldungen? Fehlen Elemente?
        5. Erstelle einen strukturierten Bericht mit dem Status jeder Seite.
        """,
    },
    {
        "name": "Visual-Audit",
        "task": f"""
        1. Oeffne {BASE_URL} und logge dich ein mit Email '{LOGIN_EMAIL}'
        2. Navigiere zur Pipeline-Seite (/pipeline)
        3. Pruefe visuell:
           - Sind die Kanban-Spalten sichtbar und korrekt ausgerichtet?
           - Gibt es ueberlagerte Elemente?
           - Sind alle Buttons und Links sichtbar und klickbar?
        4. Oeffne ein Projekt-Board (klicke auf ein Projekt unter /projects)
        5. Pruefe dort die gleichen visuellen Aspekte
        6. Erstelle einen Bericht mit allen gefundenen visuellen Problemen.
        """,
    },
]


async def run_audit():
    if not LOGIN_PASSWORD:
        print("FEHLER: TP_TEST_PASSWORD muss gesetzt sein.")
        print("Setze die Variable: export TP_TEST_PASSWORD='dein-passwort'")
        sys.exit(1)

    check_dependencies()

    from browser_use import Agent
    from langchain_ollama import ChatOllama

    llm = ChatOllama(model=AUDIT_MODEL)

    REPORT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORT_DIR / f"audit_{timestamp}.md"

    report_lines = [
        f"# TaskPilot AI-Audit Report",
        f"",
        f"**Datum:** {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        f"**Modell:** {AUDIT_MODEL}",
        f"**URL:** {BASE_URL}",
        f"",
        f"---",
        f"",
    ]

    for scenario in AUDIT_SCENARIOS:
        print(f"\n{'='*60}")
        print(f"Audit: {scenario['name']}")
        print(f"{'='*60}")

        task_with_password = scenario["task"].replace(
            "dem Passwort aus der Umgebung", f"Passwort '{LOGIN_PASSWORD}'"
        )

        try:
            agent = Agent(task=task_with_password, llm=llm)
            result = await agent.run()

            report_lines.extend([
                f"## {scenario['name']}",
                f"",
                f"### Ergebnis",
                f"",
                str(result),
                f"",
                f"---",
                f"",
            ])
            print(f"Abgeschlossen: {scenario['name']}")

        except Exception as exc:
            report_lines.extend([
                f"## {scenario['name']}",
                f"",
                f"### FEHLER",
                f"",
                f"```",
                f"{type(exc).__name__}: {exc}",
                f"```",
                f"",
                f"---",
                f"",
            ])
            print(f"Fehler bei {scenario['name']}: {exc}")

    report_content = "\n".join(report_lines)
    report_path.write_text(report_content)
    print(f"\nReport gespeichert: {report_path}")


if __name__ == "__main__":
    asyncio.run(run_audit())
