"""Tests für die reparierten Graph-Client API-Calls.

Prüft:
- get_conversation_messages(): kein $orderby, Python-Sortierung, $search-Fallback
- search_sender_emails(): kein $orderby, body im $select, $search-Fallback
"""

import pytest
import httpx
import respx

from graph_client import GraphClient, GraphConfig


@pytest.fixture
def graph_client():
    config = GraphConfig(
        tenant_id="test-tenant",
        client_id="test-client",
        client_secret="test-secret",
        user_email="user@example.com",
    )
    client = GraphClient(config)
    client._token.access_token = "fake-token"
    client._token.expires_at = 9999999999.0
    return client


CONVERSATION_MESSAGES = [
    {
        "id": "msg-2",
        "subject": "Re: Test",
        "from": {"emailAddress": {"address": "b@example.com", "name": "B"}},
        "receivedDateTime": "2026-04-02T10:00:00Z",
        "bodyPreview": "Reply",
        "body": {"contentType": "html", "content": "<p>Reply</p>"},
        "conversationId": "conv-123",
    },
    {
        "id": "msg-1",
        "subject": "Test",
        "from": {"emailAddress": {"address": "a@example.com", "name": "A"}},
        "receivedDateTime": "2026-04-01T10:00:00Z",
        "bodyPreview": "Hello",
        "body": {"contentType": "html", "content": "<p>Hello</p>"},
        "conversationId": "conv-123",
    },
]

SENDER_MESSAGES = [
    {
        "id": "msg-old",
        "subject": "Alte Mail",
        "from": {"emailAddress": {"address": "sender@example.com", "name": "Sender"}},
        "receivedDateTime": "2026-03-01T10:00:00Z",
        "bodyPreview": "Alt",
        "body": {"contentType": "html", "content": "<p>Alt</p>"},
        "conversationId": "conv-old",
    },
    {
        "id": "msg-new",
        "subject": "Neue Mail",
        "from": {"emailAddress": {"address": "sender@example.com", "name": "Sender"}},
        "receivedDateTime": "2026-04-15T10:00:00Z",
        "bodyPreview": "Neu",
        "body": {"contentType": "html", "content": "<p>Neu</p>"},
        "conversationId": "conv-new",
    },
]


@pytest.mark.asyncio
@respx.mock
async def test_get_conversation_messages_no_orderby(graph_client):
    """$orderby darf NICHT im Request sein, Sortierung geschieht in Python."""
    route = respx.get(
        url__startswith="https://graph.microsoft.com/v1.0/users/user@example.com/messages",
    ).respond(json={"value": CONVERSATION_MESSAGES})

    result = await graph_client.get_conversation_messages("conv-123")

    assert route.called
    request = route.calls[0].request
    assert "$orderby" not in str(request.url)
    assert "conversationId" in str(request.url)
    assert result[0]["receivedDateTime"] <= result[1]["receivedDateTime"]


@pytest.mark.asyncio
@respx.mock
async def test_get_conversation_messages_fallback_on_400(graph_client):
    """Bei HTTP 400 auf $filter muss $search als Fallback genutzt werden."""
    filter_route = respx.get(
        url__startswith="https://graph.microsoft.com/v1.0/users/user@example.com/messages",
    ).mock(side_effect=[
        httpx.Response(400, json={"error": {"message": "Bad Request"}}),
        httpx.Response(200, json={"value": CONVERSATION_MESSAGES}),
    ])

    result = await graph_client.get_conversation_messages("conv-123")

    assert filter_route.call_count == 2
    second_request = filter_route.calls[1].request
    url_decoded = str(second_request.url).replace("%24", "$")
    assert "$search" in url_decoded
    assert len(result) == 2


@pytest.mark.asyncio
@respx.mock
async def test_search_sender_emails_no_orderby(graph_client):
    """$orderby darf NICHT im Request sein, body muss im $select sein."""
    route = respx.get(
        url__startswith="https://graph.microsoft.com/v1.0/users/user@example.com/messages",
    ).respond(json={"value": SENDER_MESSAGES})

    result = await graph_client.search_sender_emails("sender@example.com")

    assert route.called
    request = route.calls[0].request
    url_str = str(request.url)
    assert "$orderby" not in url_str
    assert "body" in url_str
    assert result[0]["receivedDateTime"] >= result[1]["receivedDateTime"]


@pytest.mark.asyncio
@respx.mock
async def test_search_sender_emails_fallback_on_400(graph_client):
    """Bei HTTP 400 auf $filter muss $search als Fallback genutzt werden."""
    route = respx.get(
        url__startswith="https://graph.microsoft.com/v1.0/users/user@example.com/messages",
    ).mock(side_effect=[
        httpx.Response(400, json={"error": {"message": "Bad Request"}}),
        httpx.Response(200, json={"value": SENDER_MESSAGES}),
    ])

    result = await graph_client.search_sender_emails("sender@example.com")

    assert route.call_count == 2
    second_request = route.calls[1].request
    url_decoded = str(second_request.url).replace("%24", "$")
    assert "$search" in url_decoded
    assert len(result) == 2
