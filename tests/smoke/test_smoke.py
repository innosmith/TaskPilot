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


def _ensure_credentials():
    """Fragt Credentials einmal interaktiv ab (fuer Auth-Tests)."""
    global _smoke_email, _smoke_password, _credentials_prompted
    if _credentials_prompted:
        return
    _credentials_prompted = True
    _smoke_email = os.environ.get("TP_TEST_EMAIL", "admin@innosmith.ai")
    print(f"\n  Smoke-Auth-Test: Email = {_smoke_email}")
    _smoke_password = getpass.getpass(f"  Passwort (leer = Auth-Tests ueberspringen): ")
    if not _smoke_password:
        print("  → Auth-Smoke-Tests werden uebersprungen.\n")


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
        assert r.status_code == 200
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
        email, password = self._get_credentials()

        login_r = httpx.post(
            f"{backend}/api/auth/login",
            json={"email": email, "password": password},
            timeout=TIMEOUT,
        )
        assert login_r.status_code == 200, f"Login fehlgeschlagen: {login_r.status_code} {login_r.text}"

        token = login_r.json().get("access_token")
        assert token, "Kein access_token in Login-Response"

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

    def _login(self, backend) -> str | None:
        _ensure_credentials()
        if not _smoke_password:
            return None
        r = httpx.post(
            f"{backend}/api/auth/login",
            json={"email": _smoke_email, "password": _smoke_password},
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return None
        return r.json().get("access_token")

    def test_projects_endpoint(self, backend):
        """GET /api/projects antwortet (mit Auth)."""
        token = self._login(backend)
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
        token = self._login(backend)
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
        token = self._login(backend)
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
        token = self._login(backend)
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
