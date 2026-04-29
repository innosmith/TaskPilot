"""Tests fuer den Pipedrive API Client.

Testet:
- Authentifizierung via x-api-token Header
- Rate-Limit-Retry (429 → automatischer Retry)
- CRUD-Operationen fuer Deals, Persons, Activities
- Fehlerbehandlung bei HTTP-Fehlern
"""

import pytest
import httpx
import respx

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "pipedrive"))

from pipedrive_client import PipedriveClient, PipedriveConfig


@pytest.fixture
def pd_client():
    config = PipedriveConfig(
        api_token="test-token-1234",
        company_domain="testcompany",
    )
    return PipedriveClient(config)


@pytest.fixture
def base_url():
    return "https://testcompany.pipedrive.com/api"


# ── Verbindungstest ──────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_connection_success(pd_client, base_url):
    respx.get(f"{base_url}/v1/users/me").mock(
        return_value=httpx.Response(200, json={
            "success": True,
            "data": {
                "name": "Test User",
                "email": "test@example.com",
                "company_name": "TestCo",
            },
        })
    )

    result = await pd_client.test_connection()

    assert result["ok"] is True
    assert result["name"] == "Test User"
    assert result["company"] == "TestCo"

    req = respx.calls[0].request
    assert req.headers["x-api-token"] == "test-token-1234"


@respx.mock
@pytest.mark.asyncio
async def test_connection_failure(pd_client, base_url):
    respx.get(f"{base_url}/v1/users/me").mock(
        return_value=httpx.Response(401, json={"success": False, "error": "Unauthorized"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        await pd_client.test_connection()


# ── Deals ────────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_list_deals(pd_client, base_url):
    respx.get(f"{base_url}/v2/deals").mock(
        return_value=httpx.Response(200, json={
            "success": True,
            "data": [
                {"id": 1, "title": "Deal A", "status": "open", "value": 5000, "currency": "CHF"},
                {"id": 2, "title": "Deal B", "status": "open", "value": 12000, "currency": "EUR"},
            ],
        })
    )

    deals = await pd_client.list_deals(status="open", limit=10)

    assert len(deals) == 2
    assert deals[0]["title"] == "Deal A"
    assert deals[1]["value"] == 12000


@respx.mock
@pytest.mark.asyncio
async def test_create_deal(pd_client, base_url):
    respx.post(f"{base_url}/v2/deals").mock(
        return_value=httpx.Response(201, json={
            "success": True,
            "data": {"id": 42, "title": "Neuer Deal", "status": "open"},
        })
    )

    deal = await pd_client.create_deal("Neuer Deal", value=15000, currency="CHF")

    assert deal["id"] == 42
    assert deal["title"] == "Neuer Deal"


# ── Persons ──────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_list_persons(pd_client, base_url):
    respx.get(f"{base_url}/v2/persons").mock(
        return_value=httpx.Response(200, json={
            "success": True,
            "data": [
                {"id": 10, "name": "Max Muster", "email": [{"value": "max@example.com"}]},
            ],
        })
    )

    persons = await pd_client.list_persons(limit=5)

    assert len(persons) == 1
    assert persons[0]["name"] == "Max Muster"


# ── Activities ───────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_list_activities(pd_client, base_url):
    respx.get(f"{base_url}/v2/activities").mock(
        return_value=httpx.Response(200, json={
            "success": True,
            "data": [
                {"id": 100, "subject": "Follow-up Anruf", "type": "call", "done": False, "due_date": "2026-05-01"},
            ],
        })
    )

    acts = await pd_client.list_activities(done=False, limit=10)

    assert len(acts) == 1
    assert acts[0]["subject"] == "Follow-up Anruf"
    assert acts[0]["done"] is False


@respx.mock
@pytest.mark.asyncio
async def test_mark_activity_done(pd_client, base_url):
    respx.patch(f"{base_url}/v2/activities/100").mock(
        return_value=httpx.Response(200, json={
            "success": True,
            "data": {"id": 100, "done": True},
        })
    )

    result = await pd_client.mark_activity_done(100)

    assert result["done"] is True


# ── Rate-Limit Retry ─────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_rate_limit_retry(pd_client, base_url):
    """429 wird automatisch wiederholt, beim zweiten Mal klappt es."""
    route = respx.get(f"{base_url}/v2/pipelines")
    route.side_effect = [
        httpx.Response(429, json={"error": "Rate limit"}),
        httpx.Response(200, json={"success": True, "data": [{"id": 1, "name": "Sales"}]}),
    ]

    result = await pd_client.list_pipelines()

    assert len(result) == 1
    assert result[0]["name"] == "Sales"
    assert route.call_count == 2


# ── Suche ────────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_search_items(pd_client, base_url):
    respx.get(f"{base_url}/v2/itemSearch").mock(
        return_value=httpx.Response(200, json={
            "success": True,
            "data": {
                "items": [
                    {"item": {"id": 1, "type": "deal", "title": "Test Deal"}},
                ],
            },
        })
    )

    results = await pd_client.search_items("Test")

    assert len(results) == 1


# ── Config ───────────────────────────────────────────────

def test_config_defaults():
    config = PipedriveConfig()
    assert config.company_domain == "innosmith"
    assert config.is_configured is False


def test_config_with_token():
    config = PipedriveConfig(api_token="abc123", company_domain="myco")
    assert config.is_configured is True
    assert config.base_url_v2 == "https://myco.pipedrive.com/api/v2"
    assert config.base_url_v1 == "https://myco.pipedrive.com/api/v1"
