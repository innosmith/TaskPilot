"""Tests für die Dokumenten-Kontext-Brücke (Chat-Endpoint + Hermes-Worker).

Prüft, dass angehängte Dokumente (lokale Uploads + OneDrive) über den
`context_resolver` als `<attached_files>`-Block in Chat-, Agent- und
Task-Prompts gelangen. LLM/Graph werden nicht real aufgerufen.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.context_resolver import ResolvedContext


# ---------------------------------------------------------------------------
# Chat-/Agent-Brücke (app.routers.chat)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_attached_context_local_only_skips_graph():
    """Ohne OneDrive-Quelle wird kein Graph-Client erstellt."""
    from app.routers import chat

    async def fake_resolve(sources, graph_client=None):
        assert graph_client is None
        ctx = ResolvedContext()
        ctx.add_file("a.txt", "INHALT", "Upload")
        return ctx

    with patch(
        "app.services.context_resolver.resolve_context_sources", fake_resolve
    ):
        result = await chat._resolve_attached_context(
            [{"type": "local_upload", "upload_id": "chat/x.txt", "name": "a.txt"}]
        )

    assert "<attached_files>" in result
    assert "INHALT" in result


@pytest.mark.asyncio
async def test_resolve_attached_context_onedrive_uses_graph():
    """OneDrive-Quelle lädt den Graph-Client."""
    from app.routers import chat

    captured = {}

    async def fake_resolve(sources, graph_client=None):
        captured["graph_client"] = graph_client
        ctx = ResolvedContext()
        ctx.add_file("cloud.docx", "CLOUD", "OneDrive")
        return ctx

    with patch(
        "app.services.context_resolver.resolve_context_sources", fake_resolve
    ), patch("app.services.graph.get_graph_client", return_value="GRAPH"):
        result = await chat._resolve_attached_context(
            [{"type": "onedrive_file", "item_id": "ABC", "name": "cloud.docx"}]
        )

    assert captured["graph_client"] == "GRAPH"
    assert "CLOUD" in result


@pytest.mark.asyncio
async def test_resolve_attached_context_empty():
    from app.routers import chat

    assert await chat._resolve_attached_context([]) == ""
    assert await chat._resolve_attached_context(None) == ""


@pytest.mark.asyncio
async def test_resolve_attached_context_never_raises():
    """Fehler bei der Auflösung blockieren den Chat nicht (leerer String)."""
    from app.routers import chat

    async def boom(sources, graph_client=None):
        raise RuntimeError("kaputt")

    with patch("app.services.context_resolver.resolve_context_sources", boom):
        result = await chat._resolve_attached_context(
            [{"type": "local_upload", "upload_id": "chat/x.txt", "name": "x"}]
        )

    assert result == ""


def test_build_agent_prompt_includes_attached_context():
    """Der Agent-Prompt enthält den Dokumentkontext."""
    from app.routers import chat

    prompt = chat._build_agent_prompt(
        "Was steht im Dokument?",
        [],
        "<attached_files>\nDOKUMENT-TEXT\n</attached_files>",
    )

    assert "Angehängte Dokumente" in prompt
    assert "DOKUMENT-TEXT" in prompt
    assert "Was steht im Dokument?" in prompt


def test_build_agent_prompt_without_context_has_no_section():
    from app.routers import chat

    prompt = chat._build_agent_prompt("Hallo", [])
    assert "Angehängte Dokumente" not in prompt


# ---------------------------------------------------------------------------
# Worker-Brücke (app.services.hermes_worker)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_task_attachment_context_maps_sources():
    """Task-Anhänge werden korrekt zu context_sources gemappt und injiziert."""
    from app.services import hermes_worker

    task = SimpleNamespace(attachments=[
        SimpleNamespace(
            filepath="/uploads/tasks/abc/file.pdf",
            filename="file.pdf",
            mime_type="application/pdf",
        ),
        SimpleNamespace(
            filepath="onedrive://ITEM123",
            filename="cloud.docx",
            mime_type=None,
        ),
    ])

    captured = {}

    async def fake_resolve(sources, graph_client=None):
        captured["sources"] = sources
        captured["graph_client"] = graph_client
        ctx = ResolvedContext()
        ctx.add_file("file.pdf", "PDF INHALT", "Upload")
        return ctx

    with patch(
        "app.services.context_resolver.resolve_context_sources", fake_resolve
    ), patch("app.services.graph.get_graph_client", return_value="GRAPH"):
        result = await hermes_worker._resolve_task_attachment_context(task)

    assert "<attached_files>" in result
    assert "PDF INHALT" in result

    local = next(s for s in captured["sources"] if s["type"] == "local_upload")
    assert local["upload_id"] == "tasks/abc/file.pdf"

    onedrive = next(s for s in captured["sources"] if s["type"] == "onedrive_file")
    assert onedrive["item_id"] == "ITEM123"

    # OneDrive-Quelle vorhanden → Graph-Client wurde geladen
    assert captured["graph_client"] == "GRAPH"


@pytest.mark.asyncio
async def test_task_attachment_context_no_attachments():
    from app.services import hermes_worker

    task = SimpleNamespace(attachments=[])
    assert await hermes_worker._resolve_task_attachment_context(task) == ""


@pytest.mark.asyncio
async def test_task_attachment_context_local_only_no_graph():
    """Nur lokale Anhänge → kein Graph-Client."""
    from app.services import hermes_worker

    task = SimpleNamespace(attachments=[
        SimpleNamespace(
            filepath="/uploads/tasks/abc/notes.txt",
            filename="notes.txt",
            mime_type="text/plain",
        ),
    ])

    captured = {}

    async def fake_resolve(sources, graph_client=None):
        captured["graph_client"] = graph_client
        ctx = ResolvedContext()
        ctx.add_file("notes.txt", "NOTIZEN", "Upload")
        return ctx

    with patch(
        "app.services.context_resolver.resolve_context_sources", fake_resolve
    ):
        result = await hermes_worker._resolve_task_attachment_context(task)

    assert captured["graph_client"] is None
    assert "NOTIZEN" in result
