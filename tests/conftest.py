"""Root-Conftest fuer alle Test-Suiten (Smoke, E2E, Contract, AI-Audit).

Laedt automatisch .env.test, damit TP_OWNER_EMAIL, TP_TEST_EMAIL etc.
als Umgebungsvariablen verfuegbar sind — unabhaengig davon, wie pytest
aufgerufen wird.
"""

from pathlib import Path

from dotenv import load_dotenv

_env_test = Path(__file__).resolve().parents[1] / ".env.test"
if _env_test.exists():
    load_dotenv(_env_test, override=False)
