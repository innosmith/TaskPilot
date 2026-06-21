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


# ---------------------------------------------------------------------------
# create_draft: Reply-im-Thread + Empfaenger-Korrektheit (Stil-Lern-Signal)
# ---------------------------------------------------------------------------

import json as _json


@pytest.mark.asyncio
@respx.mock
async def test_create_draft_reply_uses_createreplyall_without_overriding_recipients(graph_client):
    """Reply (Default): createReplyAll nutzen, toRecipients NICHT mitschicken."""
    isread_route = respx.get(
        url__startswith="https://graph.microsoft.com/v1.0/users/user@example.com/messages/orig-1",
    ).respond(json={"id": "orig-1", "isRead": True})
    reply_all_route = respx.post(
        url__startswith="https://graph.microsoft.com/v1.0/users/user@example.com/messages/orig-1/createReplyAll",
    ).respond(json={"id": "draft-1", "conversationId": "conv-1"})
    new_mail_route = respx.post(
        url="https://graph.microsoft.com/v1.0/users/user@example.com/messages",
    ).respond(json={"id": "should-not-be-used"})

    draft = await graph_client.create_draft(
        subject="RE: Test",
        body_html="<p>Antwort</p>",
        to_recipients=["falsch@example.com"],
        reply_to_id="orig-1",
    )

    assert draft["id"] == "draft-1"
    assert reply_all_route.called
    # Niemals ein neuer Thread bei Reply.
    assert not new_mail_route.called
    assert isread_route.called
    body = _json.loads(reply_all_route.calls[0].request.content)
    # createReplyAll-Default-Empfaenger NICHT ueberschreiben.
    assert "toRecipients" not in body["message"]
    assert body["message"]["body"]["content"] == "<p>Antwort</p>"


@pytest.mark.asyncio
@respx.mock
async def test_create_draft_reply_sender_only_uses_createreply(graph_client):
    """reply_all=False: createReply (nur an den Absender) nutzen, nicht createReplyAll."""
    respx.get(
        url__startswith="https://graph.microsoft.com/v1.0/users/user@example.com/messages/orig-3",
    ).respond(json={"id": "orig-3", "isRead": True})
    reply_all_route = respx.post(
        url__startswith="https://graph.microsoft.com/v1.0/users/user@example.com/messages/orig-3/createReplyAll",
    ).respond(json={"id": "should-not-be-used"})
    reply_route = respx.post(
        url="https://graph.microsoft.com/v1.0/users/user@example.com/messages/orig-3/createReply",
    ).respond(json={"id": "draft-3", "conversationId": "conv-3"})

    draft = await graph_client.create_draft(
        subject="RE: Test",
        body_html="<p>Antwort</p>",
        to_recipients=["sender@example.com"],
        reply_to_id="orig-3",
        reply_all=False,
    )

    assert draft["id"] == "draft-3"
    assert reply_route.called
    assert not reply_all_route.called


@pytest.mark.asyncio
@respx.mock
async def test_create_draft_reply_adds_cc_additively(graph_client):
    """CC darf bei Reply ergaenzt werden (additiv), TO bleibt createReplyAll-Default."""
    respx.get(
        url__startswith="https://graph.microsoft.com/v1.0/users/user@example.com/messages/orig-2",
    ).respond(json={"id": "orig-2", "isRead": True})
    reply_route = respx.post(
        url__startswith="https://graph.microsoft.com/v1.0/users/user@example.com/messages/orig-2/createReplyAll",
    ).respond(json={"id": "draft-2"})

    await graph_client.create_draft(
        subject="RE: Test",
        body_html="<p>Hi</p>",
        to_recipients=["sender@example.com"],
        cc_recipients=["chef@example.com"],
        reply_to_id="orig-2",
    )

    body = _json.loads(reply_route.calls[0].request.content)
    assert "toRecipients" not in body["message"]
    cc = [r["emailAddress"]["address"] for r in body["message"]["ccRecipients"]]
    assert cc == ["chef@example.com"]


@pytest.mark.asyncio
@respx.mock
async def test_create_draft_new_mail_sets_recipients(graph_client):
    """Ohne reply_to_id: normale neue Mail mit explizitem TO-Empfaenger."""
    new_mail_route = respx.post(
        url="https://graph.microsoft.com/v1.0/users/user@example.com/messages",
    ).respond(json={"id": "draft-new"})

    draft = await graph_client.create_draft(
        subject="Neue Mail",
        body_html="<p>Text</p>",
        to_recipients=["empfaenger@example.com"],
    )

    assert draft["id"] == "draft-new"
    assert new_mail_route.called
    body = _json.loads(new_mail_route.calls[0].request.content)
    to = [r["emailAddress"]["address"] for r in body["toRecipients"]]
    assert to == ["empfaenger@example.com"]


# ---------------------------------------------------------------------------
# Kalender: Zeitzonen-Offset in der calendarView-Abfrage (Überbuchungs-Fix)
# ---------------------------------------------------------------------------

class TestEnsureTzOffset:
    """Prüft das DST-sichere Anhängen des Europe/Zurich-Offsets."""

    def test_summer_offset_added(self):
        """Sommerzeit (Juni) → +02:00 wird angehängt."""
        result = GraphClient._ensure_tz_offset("2026-06-01T16:00:00")
        assert result == "2026-06-01T16:00:00+02:00"

    def test_winter_offset_added(self):
        """Winterzeit (Januar) → +01:00 wird angehängt."""
        result = GraphClient._ensure_tz_offset("2026-01-15T16:00:00")
        assert result == "2026-01-15T16:00:00+01:00"

    def test_existing_offset_untouched(self):
        """Bereits vorhandener Offset bleibt unverändert."""
        assert GraphClient._ensure_tz_offset("2026-06-01T16:00:00+02:00") == "2026-06-01T16:00:00+02:00"

    def test_utc_z_suffix_untouched(self):
        """UTC-Z-Suffix bleibt unverändert."""
        assert GraphClient._ensure_tz_offset("2026-06-01T16:00:00Z") == "2026-06-01T16:00:00Z"


CALENDAR_BUSY_EVENT = [
    {
        "id": "evt-1",
        "subject": "Weiteres Vorgehen NITL",
        "start": {"dateTime": "2026-06-01T16:00:00.0000000", "timeZone": "Europe/Zurich"},
        "end": {"dateTime": "2026-06-01T17:00:00.0000000", "timeZone": "Europe/Zurich"},
        "showAs": "busy",
        "isCancelled": False,
    },
]


@pytest.mark.asyncio
@respx.mock
async def test_find_free_slots_query_has_tz_offset(graph_client):
    """Das Suchfenster muss mit Zeitzonen-Offset an Graph gehen (sonst UTC-Bug)."""
    route = respx.get(
        url__startswith="https://graph.microsoft.com/v1.0/users/user@example.com/calendarView",
    ).respond(json={"value": []})

    await graph_client.find_free_slots(
        start="2026-06-01T16:00:00",
        end="2026-06-01T20:00:00",
        duration_minutes=90,
    )

    assert route.called
    url_decoded = str(route.calls[0].request.url).replace("%3A", ":").replace("%2B", "+")
    assert "2026-06-01T16:00:00+02:00" in url_decoded
    assert "2026-06-01T20:00:00+02:00" in url_decoded


@pytest.mark.asyncio
@respx.mock
async def test_find_free_slots_detects_overlapping_meeting(graph_client):
    """Ein 16:00-Termin muss als busy erkannt werden → 16:00 nicht frei.

    Reproduziert die Debitoren-Überbuchung: vor dem Fix wurde 16:00 als frei
    gemeldet und der Termin darüber gebucht.
    """
    respx.get(
        url__startswith="https://graph.microsoft.com/v1.0/users/user@example.com/calendarView",
    ).respond(json={"value": CALENDAR_BUSY_EVENT})

    slots = await graph_client.find_free_slots(
        start="2026-06-01T16:00:00",
        end="2026-06-01T20:00:00",
        duration_minutes=90,
    )

    # Kein Slot darf um 16:00 starten (Konflikt mit bestehendem Termin).
    assert all(not s["start"].endswith("16:00:00") for s in slots)
    # Erster freier Slot beginnt frühestens um 17:00 (nach dem Termin).
    assert slots
    assert slots[0]["start"].endswith("17:00:00")
