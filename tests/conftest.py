"""Root-Conftest fuer alle Test-Suiten (Smoke, E2E, Contract, AI-Audit).

Laedt automatisch .env.int, damit TP_OWNER_EMAIL, TP_OWNER_PASSWORD etc.
als Umgebungsvariablen verfuegbar sind — alle Tests unter tests/ laufen
gegen die Integration-Umgebung (make int, Ports 8100/3100).
"""

from pathlib import Path

from dotenv import load_dotenv

_env_int = Path(__file__).resolve().parents[1] / ".env.integration"
if _env_int.exists():
    load_dotenv(_env_int, override=False)
