"""Tests für den Bexio Buchhaltungs-API Client.

Testet:
- Bearer Token Authentifizierung
- Rate-Limit-Retry (429 → automatischer Retry)
- Kontakte, Aufträge, Rechnungen, Projekte
- Kontaktsuche nach Name und E-Mail
"""

import pytest
import httpx
import respx

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "bexio"))

from bexio_client import BexioClient, BexioConfig, BASE_URL_V2, BASE_URL_V3


@pytest.fixture
def bx_client():
    return BexioClient(BexioConfig(api_token="test-bexio-token"))


# ── Config ───────────────────────────────────────────────

def test_config_defaults():
    config = BexioConfig()
    assert config.is_configured is False


def test_config_with_token():
    config = BexioConfig(api_token="abc123")
    assert config.is_configured is True


# ── Verbindungstest ──────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_connection_success(bx_client):
    respx.get(f"{BASE_URL_V3}/users/me").mock(
        return_value=httpx.Response(200, json={
            "id": 1,
            "firstname": "Anthony",
            "lastname": "Smith",
            "email": "anthony@example.com",
        })
    )

    result = await bx_client.test_connection()

    assert result["ok"] is True
    assert result["name"] == "Anthony Smith"
    assert result["email"] == "anthony@example.com"


@respx.mock
@pytest.mark.asyncio
async def test_connection_auth_header(bx_client):
    respx.get(f"{BASE_URL_V3}/users/me").mock(
        return_value=httpx.Response(200, json={"id": 1, "firstname": "A", "lastname": "S", "email": "a@b.com"})
    )

    await bx_client.test_connection()

    req = respx.calls[0].request
    assert req.headers["authorization"] == "Bearer test-bexio-token"


# ── Kontakte ─────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_list_contacts(bx_client):
    respx.get(f"{BASE_URL_V2}/contact").mock(
        return_value=httpx.Response(200, json=[
            {"id": 1, "name_1": "Muster AG", "mail": "info@muster.ch"},
            {"id": 2, "name_1": "Beispiel GmbH", "mail": "info@beispiel.ch"},
        ])
    )

    contacts = await bx_client.list_contacts(limit=10)

    assert len(contacts) == 2
    assert contacts[0]["name_1"] == "Muster AG"


@respx.mock
@pytest.mark.asyncio
async def test_get_contact(bx_client):
    respx.get(f"{BASE_URL_V2}/contact/1").mock(
        return_value=httpx.Response(200, json={
            "id": 1, "name_1": "Muster AG", "mail": "info@muster.ch",
        })
    )

    contact = await bx_client.get_contact(1)

    assert contact["id"] == 1
    assert contact["name_1"] == "Muster AG"


@respx.mock
@pytest.mark.asyncio
async def test_create_contact(bx_client):
    respx.post(f"{BASE_URL_V2}/contact").mock(
        return_value=httpx.Response(201, json={
            "id": 42, "name_1": "Neue Firma AG",
        })
    )

    result = await bx_client.create_contact({"name_1": "Neue Firma AG", "contact_type_id": 1})

    assert result["id"] == 42


@respx.mock
@pytest.mark.asyncio
async def test_search_contact_by_name(bx_client):
    respx.post(f"{BASE_URL_V2}/contact/search").mock(
        return_value=httpx.Response(200, json=[
            {"id": 1, "name_1": "Innosmith GmbH", "mail": "info@innosmith.ch"},
        ])
    )

    results = await bx_client.search_contact_by_name("Innosmith")

    assert len(results) == 1
    assert results[0]["name_1"] == "Innosmith GmbH"


@respx.mock
@pytest.mark.asyncio
async def test_search_contact_by_email(bx_client):
    respx.post(f"{BASE_URL_V2}/contact/search").mock(
        return_value=httpx.Response(200, json=[
            {"id": 1, "name_1": "Innosmith GmbH", "mail": "info@innosmith.ch"},
        ])
    )

    results = await bx_client.search_contact_by_email("info@innosmith.ch")

    assert len(results) == 1


# ── Aufträge ─────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_list_orders(bx_client):
    respx.get(f"{BASE_URL_V2}/kb_order").mock(
        return_value=httpx.Response(200, json=[
            {"id": 10, "title": "Auftrag 2026-001", "total": "5000.00"},
        ])
    )

    orders = await bx_client.list_orders(limit=10)

    assert len(orders) == 1
    assert orders[0]["title"] == "Auftrag 2026-001"


@respx.mock
@pytest.mark.asyncio
async def test_get_order(bx_client):
    respx.get(f"{BASE_URL_V2}/kb_order/10").mock(
        return_value=httpx.Response(200, json={
            "id": 10, "title": "Auftrag 2026-001",
        })
    )

    order = await bx_client.get_order(10)

    assert order["id"] == 10


# ── Rechnungen ───────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_list_invoices(bx_client):
    respx.get(f"{BASE_URL_V2}/kb_invoice").mock(
        return_value=httpx.Response(200, json=[
            {"id": 20, "title": "Rechnung 2026-001", "total": "3500.00"},
        ])
    )

    invoices = await bx_client.list_invoices()

    assert len(invoices) == 1


# ── Projekte ─────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_list_projects(bx_client):
    respx.get(f"{BASE_URL_V2}/pr_project").mock(
        return_value=httpx.Response(200, json=[
            {"id": 5, "name": "TaskPilot", "status_id": 1},
        ])
    )

    projects = await bx_client.list_projects()

    assert len(projects) == 1
    assert projects[0]["name"] == "TaskPilot"


@respx.mock
@pytest.mark.asyncio
async def test_get_project(bx_client):
    respx.get(f"{BASE_URL_V2}/pr_project/5").mock(
        return_value=httpx.Response(200, json={
            "id": 5, "name": "TaskPilot",
        })
    )

    project = await bx_client.get_project(5)

    assert project["name"] == "TaskPilot"


# ── Rate-Limit Retry ─────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_rate_limit_retry(bx_client):
    """429 wird automatisch wiederholt."""
    route = respx.get(f"{BASE_URL_V2}/contact")
    route.side_effect = [
        httpx.Response(429, json={"error": "Rate limit exceeded"}),
        httpx.Response(200, json=[{"id": 1, "name_1": "Test"}]),
    ]

    result = await bx_client.list_contacts()

    assert len(result) == 1
    assert route.call_count == 2
