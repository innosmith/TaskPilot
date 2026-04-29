"""Tests für den Toggl Track API Client.

Testet:
- HTTP Basic Auth Header
- Rate-Limit-Retry (429 → automatischer Retry)
- Workspaces, Clients, Projects
- Lokale Suchfilterung
"""

import pytest
import httpx
import respx

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "toggl"))

from toggl_client import TogglClient, TogglConfig, BASE_URL, REPORTS_URL


@pytest.fixture
def tg_client():
    return TogglClient(TogglConfig(api_token="test-toggl-token", workspace_id=12345))


# ── Config ───────────────────────────────────────────────

def test_config_defaults():
    config = TogglConfig()
    assert config.is_configured is False
    assert config.workspace_id == 0


def test_config_auth_header():
    config = TogglConfig(api_token="abc123", workspace_id=99)
    assert config.is_configured is True
    assert config.auth_header.startswith("Basic ")


# ── Verbindungstest ──────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_connection_success(tg_client):
    respx.get(f"{BASE_URL}/me").mock(
        return_value=httpx.Response(200, json={
            "id": 1,
            "fullname": "Test User",
            "email": "test@toggl.com",
            "default_workspace_id": 12345,
        })
    )

    result = await tg_client.test_connection()

    assert result["ok"] is True
    assert result["name"] == "Test User"
    assert result["email"] == "test@toggl.com"


@respx.mock
@pytest.mark.asyncio
async def test_connection_failure(tg_client):
    respx.get(f"{BASE_URL}/me").mock(
        return_value=httpx.Response(403, json={"error": "Forbidden"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        await tg_client.test_connection()


# ── Workspaces ───────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_list_workspaces(tg_client):
    respx.get(f"{BASE_URL}/me/workspaces").mock(
        return_value=httpx.Response(200, json=[
            {"id": 12345, "name": "Mein Workspace"},
        ])
    )

    ws = await tg_client.list_workspaces()

    assert len(ws) == 1
    assert ws[0]["name"] == "Mein Workspace"


# ── Clients ──────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_list_clients(tg_client):
    respx.get(f"{BASE_URL}/workspaces/12345/clients").mock(
        return_value=httpx.Response(200, json=[
            {"id": 1, "name": "Kunde A"},
            {"id": 2, "name": "Kunde B"},
        ])
    )

    clients = await tg_client.list_clients()

    assert len(clients) == 2
    assert clients[0]["name"] == "Kunde A"


@respx.mock
@pytest.mark.asyncio
async def test_create_client(tg_client):
    respx.post(f"{BASE_URL}/workspaces/12345/clients").mock(
        return_value=httpx.Response(200, json={"id": 42, "name": "Neuer Kunde"})
    )

    result = await tg_client.create_client(12345, "Neuer Kunde")

    assert result["id"] == 42
    assert result["name"] == "Neuer Kunde"


@respx.mock
@pytest.mark.asyncio
async def test_search_clients(tg_client):
    respx.get(f"{BASE_URL}/workspaces/12345/clients").mock(
        return_value=httpx.Response(200, json=[
            {"id": 1, "name": "Innosmith GmbH"},
            {"id": 2, "name": "Andere Firma AG"},
            {"id": 3, "name": "Innosmith Beratung"},
        ])
    )

    results = await tg_client.search_clients("innosmith")

    assert len(results) == 2
    assert all("innosmith" in r["name"].lower() for r in results)


# ── Projects ─────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_list_projects(tg_client):
    respx.get(f"{BASE_URL}/workspaces/12345/projects").mock(
        return_value=httpx.Response(200, json=[
            {"id": 10, "name": "Projekt Alpha", "active": True},
            {"id": 11, "name": "Projekt Beta", "active": True},
        ])
    )

    projects = await tg_client.list_projects()

    assert len(projects) == 2


@respx.mock
@pytest.mark.asyncio
async def test_create_project(tg_client):
    respx.post(f"{BASE_URL}/workspaces/12345/projects").mock(
        return_value=httpx.Response(200, json={
            "id": 99, "name": "Neues Projekt", "billable": True,
        })
    )

    result = await tg_client.create_project(12345, "Neues Projekt", client_id=1)

    assert result["id"] == 99
    assert result["name"] == "Neues Projekt"


@respx.mock
@pytest.mark.asyncio
async def test_search_projects(tg_client):
    respx.get(f"{BASE_URL}/workspaces/12345/projects").mock(
        return_value=httpx.Response(200, json=[
            {"id": 10, "name": "TaskPilot Entwicklung"},
            {"id": 11, "name": "Website Redesign"},
            {"id": 12, "name": "TaskPilot Support"},
        ])
    )

    results = await tg_client.search_projects("taskpilot")

    assert len(results) == 2


# ── Rate-Limit Retry ─────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_rate_limit_retry(tg_client):
    """429 wird automatisch wiederholt."""
    route = respx.get(f"{BASE_URL}/me/workspaces")
    route.side_effect = [
        httpx.Response(429, json={"error": "Too many requests"}),
        httpx.Response(200, json=[{"id": 12345, "name": "WS"}]),
    ]

    result = await tg_client.list_workspaces()

    assert len(result) == 1
    assert route.call_count == 2


# ── Time Entries ─────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_search_time_entries(tg_client):
    respx.post(f"{REPORTS_URL}/workspace/12345/search/time_entries").mock(
        return_value=httpx.Response(200, json=[
            {"id": 1001, "description": "Entwicklung", "seconds": 3600},
        ])
    )

    entries = await tg_client.search_time_entries(12345, "2026-04-01", "2026-04-30")

    assert len(entries) == 1
    assert entries[0]["seconds"] == 3600
