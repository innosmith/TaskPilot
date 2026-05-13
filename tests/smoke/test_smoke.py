"""Smoke-Tests fuer die Multi-Container-Integration.

Laufen nach `make int` gegen die Integration-Umgebung (Ports 8100/3100).
Pruefen ob alle Services erreichbar und grundlegend funktional sind.

Ausfuehrung:
    make test-smoke
    # oder: python -m pytest tests/smoke/ -v -s

Health-Checks brauchen keine Credentials.
Auth-Tests fragen das Passwort interaktiv ab (getpass).
"""

import getpass
import os

import httpx
import pytest

BACKEND_URL = os.environ.get("TP_SMOKE_BACKEND_URL", "http://localhost:8100")
FRONTEND_URL = os.environ.get("TP_SMOKE_FRONTEND_URL", "http://localhost:3100")
TIMEOUT = 10.0

_smoke_email: str = ""
_smoke_password: str = ""
_credentials_prompted = False
_cached_token: str | None = None


def _ensure_credentials():
    """Fragt Credentials einmal interaktiv ab (fuer Auth-Tests)."""
    global _smoke_email, _smoke_password, _credentials_prompted
    if _credentials_prompted:
        return
    _credentials_prompted = True
    _smoke_email = os.environ.get("TP_TEST_EMAIL") or os.environ.get("TP_OWNER_EMAIL")
    if not _smoke_email:
        pytest.skip("TP_TEST_EMAIL oder TP_OWNER_EMAIL muss gesetzt sein")
    print(f"\n  Smoke-Auth-Test: Email = {_smoke_email}")
    _smoke_password = os.environ.get("TP_TEST_PASSWORD") or os.environ.get("TP_OWNER_PASSWORD", "")
    if not _smoke_password:
        try:
            _smoke_password = getpass.getpass("  Passwort (leer = Auth-Tests ueberspringen): ")
        except (EOFError, OSError):
            _smoke_password = ""
    if not _smoke_password:
        print("  → Auth-Smoke-Tests werden uebersprungen.\n")


def _get_token(backend: str) -> str | None:
    """Login einmal ausfuehren, Token fuer alle Tests cachen.

    Falls MFA aktiviert ist, wird der TOTP-Code interaktiv abgefragt.
    """
    global _cached_token
    _ensure_credentials()
    if not _smoke_password:
        return None
    if _cached_token is not None:
        return _cached_token

    payload: dict = {"email": _smoke_email, "password": _smoke_password}
    r = httpx.post(f"{backend}/api/auth/login", json=payload, timeout=TIMEOUT)
    if r.status_code != 200:
        return None

    data = r.json()
    if data.get("requires_mfa") and not data.get("access_token"):
        try:
            mfa_code = getpass.getpass("  MFA-Code (TOTP): ")
        except (EOFError, OSError):
            mfa_code = ""
        if not mfa_code:
            print("  → Kein MFA-Code eingegeben, Auth-Tests uebersprungen.\n")
            return None
        payload["mfa_code"] = mfa_code
        r = httpx.post(f"{backend}/api/auth/login", json=payload, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        data = r.json()

    _cached_token = data.get("access_token", "")
    return _cached_token or None


@pytest.fixture
def backend():
    return BACKEND_URL


@pytest.fixture
def frontend():
    return FRONTEND_URL


class TestHealthChecks:
    """Alle Services muessen erreichbar sein — keine Credentials noetig."""

    def test_backend_health(self, backend):
        """Backend /api/health gibt 200 zurueck."""
        r = httpx.get(f"{backend}/api/health", timeout=TIMEOUT)
        assert r.status_code == 200, f"Backend Health fehlgeschlagen: {r.status_code} {r.text}"

    def test_frontend_reachable(self, frontend):
        """Frontend liefert HTML zurueck."""
        r = httpx.get(frontend, timeout=TIMEOUT, follow_redirects=True)
        assert r.status_code == 200, f"Frontend nicht erreichbar: {r.status_code}"
        assert "text/html" in r.headers.get("content-type", "")

    def test_backend_openapi_schema(self, backend):
        """OpenAPI-Schema ist verfuegbar (fuer Contract-Guard)."""
        r = httpx.get(f"{backend}/openapi.json", timeout=TIMEOUT)
        assert r.status_code == 200, (
            f"OpenAPI-Schema nicht verfuegbar ({r.status_code}). "
            "Pruefe TP_DEBUG=true in der Umgebungskonfiguration."
        )
        schema = r.json()
        assert "paths" in schema
        assert "/api/auth/login" in schema["paths"]


class TestAuthRoundtrip:
    """Login mit interaktiv eingegebenen Credentials."""

    def _get_credentials(self):
        _ensure_credentials()
        if not _smoke_password:
            pytest.skip("Kein Passwort eingegeben — Auth-Smoke uebersprungen")
        return _smoke_email, _smoke_password

    def test_login_and_me(self, backend):
        """Login → Token → GET /me liefert User-Daten."""
        email, _ = self._get_credentials()

        token = _get_token(backend)
        assert token, "Login fehlgeschlagen (kein Token erhalten)"

        me_r = httpx.get(
            f"{backend}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )
        assert me_r.status_code == 200, f"GET /me fehlgeschlagen: {me_r.status_code}"
        assert me_r.json().get("email") == email

    def test_unauthenticated_rejected(self, backend):
        """Geschuetzter Endpoint ohne Token gibt 401/403 zurueck."""
        r = httpx.get(f"{backend}/api/projects", timeout=TIMEOUT)
        assert r.status_code in (401, 403)


class TestCriticalEndpoints:
    """Kritische API-Endpoints existieren und antworten korrekt."""

    def test_projects_endpoint(self, backend):
        """GET /api/projects antwortet (mit Auth)."""
        token = _get_token(backend)
        if not token:
            pytest.skip("Login nicht moeglich")
        r = httpx.get(
            f"{backend}/api/projects",
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_pipeline_endpoint(self, backend):
        """GET /api/pipeline antwortet (mit Auth)."""
        token = _get_token(backend)
        if not token:
            pytest.skip("Login nicht moeglich")
        r = httpx.get(
            f"{backend}/api/pipeline",
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200

    def test_tags_endpoint(self, backend):
        """GET /api/tags antwortet (mit Auth)."""
        token = _get_token(backend)
        if not token:
            pytest.skip("Login nicht moeglich")
        r = httpx.get(
            f"{backend}/api/tags",
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_sse_endpoint_exists(self, backend):
        """SSE-Endpoint existiert (Connection wird sofort geschlossen)."""
        token = _get_token(backend)
        if not token:
            pytest.skip("Login nicht moeglich")
        try:
            with httpx.stream(
                "GET",
                f"{backend}/api/sse/events?token={token}",
                timeout=3.0,
            ) as r:
                assert r.status_code == 200
                assert "text/event-stream" in r.headers.get("content-type", "")
        except httpx.ReadTimeout:
            pass  # SSE-Stream laeuft endlos, Timeout ist erwartet

    def test_models_available(self, backend):
        """GET /api/models/available -- LLM-Gateway erreichbar (Ollama/LiteLLM)."""
        token = _get_token(backend)
        if not token:
            pytest.skip("Login nicht moeglich")
        r = httpx.get(
            f"{backend}/api/models/available",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15.0,
        )
        assert r.status_code == 200, f"Models-Endpoint fehlgeschlagen: {r.status_code} {r.text}"
        data = r.json()
        assert isinstance(data, dict), "Response muss ein Dict sein"
        all_models = data.get("local", []) + data.get("cloud", [])
        assert len(all_models) > 0, (
            "Keine Modelle verfuegbar -- Ollama/LiteLLM nicht erreichbar? "
            "Pruefe TP_OLLAMA_BASE_URL / TP_LITELLM_BASE_URL im Container."
        )

    def test_settings_endpoint(self, backend):
        """GET /api/settings -- Owner-Settings ladbar."""
        token = _get_token(backend)
        if not token:
            pytest.skip("Login nicht moeglich")
        r = httpx.get(
            f"{backend}/api/settings",
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, f"Settings fehlgeschlagen: {r.status_code}"

    def test_creditors_dashboard(self, backend):
        """GET /api/creditors/dashboard -- InvoiceInsight MCP erreichbar."""
        token = _get_token(backend)
        if not token:
            pytest.skip("Login nicht moeglich")
        r = httpx.get(
            f"{backend}/api/creditors/dashboard",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15.0,
        )
        # 200 = MCP erreichbar, 503 = URL nicht konfiguriert, 400 = Key fehlt
        # Alles ausser 500 ist akzeptabel (zeigt, dass der Endpoint existiert)
        assert r.status_code != 500, (
            f"Creditors-Dashboard Serverfehler: {r.text[:200]}. "
            "Pruefe TP_INVOICEINSIGHT_URL im Container."
        )


class TestDockerIntegration:
    """Tests die Docker-spezifische Probleme erkennen (Volumes, Nginx, Alembic)."""

    def test_upload_small_file(self, backend):
        """Upload einer kleinen Datei -- prueft Volume-Rechte + Nginx body-size."""
        token = _get_token(backend)
        if not token:
            pytest.skip("Login nicht moeglich")
        # 1-Pixel PNG (68 Bytes)
        import base64
        tiny_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQAB"
            "Nl7BcQAAAABJRU5ErkJggg=="
        )
        r = httpx.post(
            f"{backend}/api/uploads/avatars",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.png", tiny_png, "image/png")},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, (
            f"Upload fehlgeschlagen ({r.status_code}): {r.text[:200]}. "
            "Pruefe Volume-Rechte (/app/uploads) im Container."
        )
        data = r.json()
        assert "url" in data, "Upload-Response enthaelt keine URL"

    def test_upload_via_nginx(self, frontend, backend):
        """Upload durch Nginx-Proxy -- prueft client_max_body_size."""
        token = _get_token(backend)
        if not token:
            pytest.skip("Login nicht moeglich")
        # 2MB Dummy-Datei (ueber Default 1MB Nginx-Limit)
        big_data = b"\x00" * (2 * 1024 * 1024)
        r = httpx.post(
            f"{frontend}/api/uploads/avatars",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("big.bin", big_data, "application/octet-stream")},
            timeout=30.0,
        )
        # Wenn Nginx client_max_body_size zu klein ist, kommt 413
        assert r.status_code != 413, (
            "Nginx blockiert Uploads > 1MB (HTTP 413). "
            "client_max_body_size in nginx.conf.template erhoehen."
        )

    def test_pipeline_structure(self, backend):
        """GET /api/pipeline liefert valide Struktur (nicht nur 200)."""
        token = _get_token(backend)
        if not token:
            pytest.skip("Login nicht moeglich")
        r = httpx.get(
            f"{backend}/api/pipeline",
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert "columns" in data, "Pipeline-Response hat kein 'columns'-Feld"
        assert isinstance(data["columns"], list), "'columns' muss eine Liste sein"

    def test_alembic_in_container(self):
        """Alembic-Dateien sind im Backend-Container vorhanden."""
        import subprocess
        result = subprocess.run(
            ["docker", "exec", "taskpilot-backend-int",
             "test", "-f", "/app/alembic.ini"],
            capture_output=True,
        )
        assert result.returncode == 0, (
            "alembic.ini fehlt im Container -- "
            "Dockerfile muss alembic.ini + migrations/ kopieren."
        )
        result2 = subprocess.run(
            ["docker", "exec", "taskpilot-backend-int",
             "test", "-d", "/app/migrations/versions"],
            capture_output=True,
        )
        assert result2.returncode == 0, (
            "migrations/versions/ fehlt im Container -- "
            "Dockerfile muss migrations/ kopieren."
        )

    def test_uploads_dir_writable(self):
        """Upload-Verzeichnis im Container ist beschreibbar."""
        import subprocess
        result = subprocess.run(
            ["docker", "exec", "taskpilot-backend-int",
             "gosu", "taskpilot", "touch", "/app/uploads/.write-test"],
            capture_output=True,
        )
        assert result.returncode == 0, (
            "/app/uploads nicht beschreibbar als taskpilot-User. "
            "Volume-Rechte im entrypoint.sh pruefen."
        )
        # Aufraeumen
        subprocess.run(
            ["docker", "exec", "taskpilot-backend-int",
             "rm", "-f", "/app/uploads/.write-test"],
            capture_output=True,
        )
