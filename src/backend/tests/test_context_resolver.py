"""Tests fuer den Context Resolver (services/context_resolver.py).

Prüft:
- ResolvedContext: Datei-Limits, Zeichen-Limits, Truncation
- LLM-Kontext-Formatierung
- Path-Traversal-Schutz bei lokalen Uploads
- Textextraktion (_extract_text) nach Dateityp/MIME
- Konstanten (Allowed Extensions, Limits)
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.context_resolver import (
    ALLOWED_TEXT_EXTENSIONS,
    ALLOWED_UPLOAD_DIR,
    MAX_FILES_PER_REQUEST,
    MAX_TOTAL_CHARS,
    ResolvedContext,
    _extract_text,
    _resolve_local_upload,
)


# ---------------------------------------------------------------------------
# ResolvedContext — Limits und Formatierung
# ---------------------------------------------------------------------------

class TestResolvedContextLimits:
    """Prüft Datei- und Zeichen-Limits von ResolvedContext."""

    def test_add_file_within_limits(self):
        ctx = ResolvedContext()
        ctx.add_file("test.md", "Hallo Welt", "Upload")

        assert len(ctx.files) == 1
        assert ctx.files[0]["name"] == "test.md"
        assert ctx.files[0]["content"] == "Hallo Welt"
        assert ctx.files[0]["source"] == "Upload"
        assert ctx.total_chars == len("Hallo Welt")
        assert not ctx.truncated

    def test_max_files_limit(self):
        """Nach MAX_FILES_PER_REQUEST Dateien werden weitere ignoriert."""
        ctx = ResolvedContext()
        for i in range(MAX_FILES_PER_REQUEST):
            ctx.add_file(f"file_{i}.txt", "x", "Upload")

        assert len(ctx.files) == MAX_FILES_PER_REQUEST
        assert not ctx.truncated

        ctx.add_file("overflow.txt", "y", "Upload")
        assert len(ctx.files) == MAX_FILES_PER_REQUEST
        assert ctx.truncated

    def test_max_chars_truncation(self):
        """Überschreitung des Zeichen-Limits kürzt den Inhalt."""
        ctx = ResolvedContext()
        content = "A" * (MAX_TOTAL_CHARS - 10)
        ctx.add_file("big.txt", content, "Upload")
        assert not ctx.truncated

        ctx.add_file("extra.txt", "B" * 100, "Upload")
        assert ctx.truncated
        assert len(ctx.files) == 2
        assert ctx.files[1]["content"].endswith("[... Text gekürzt ...]")

    def test_zero_remaining_chars(self):
        """Wenn keine Zeichen mehr übrig, wird die Datei nicht hinzugefügt."""
        ctx = ResolvedContext()
        ctx.add_file("full.txt", "A" * MAX_TOTAL_CHARS, "Upload")
        assert not ctx.truncated

        ctx.add_file("nope.txt", "mehr Text", "Upload")
        assert ctx.truncated
        assert len(ctx.files) == 1

    def test_empty_context(self):
        ctx = ResolvedContext()
        assert ctx.files == []
        assert ctx.total_chars == 0
        assert not ctx.truncated


class TestResolvedContextFormatting:
    """Prüft die LLM-Kontext-Formatierung."""

    def test_to_llm_context_empty(self):
        ctx = ResolvedContext()
        assert ctx.to_llm_context() == ""

    def test_to_llm_context_single_file(self):
        ctx = ResolvedContext()
        ctx.add_file("readme.md", "# Projekt", "OneDrive")
        result = ctx.to_llm_context()

        assert "<attached_files>" in result
        assert "</attached_files>" in result
        assert "## Datei: readme.md (OneDrive)" in result
        assert "# Projekt" in result

    def test_to_llm_context_truncation_hint(self):
        """Bei Truncation wird ein Hinweis angehängt."""
        ctx = ResolvedContext()
        for i in range(MAX_FILES_PER_REQUEST + 1):
            ctx.add_file(f"f{i}.txt", "x", "Upload")

        result = ctx.to_llm_context()
        assert "[Hinweis:" in result
        assert f"{MAX_TOTAL_CHARS:,}" in result

    def test_to_llm_context_multiple_files(self):
        ctx = ResolvedContext()
        ctx.add_file("a.py", "print(1)", "Upload")
        ctx.add_file("b.md", "# B", "OneDrive")
        result = ctx.to_llm_context()

        assert "## Datei: a.py (Upload)" in result
        assert "## Datei: b.md (OneDrive)" in result


# ---------------------------------------------------------------------------
# _extract_text — Dateiextraktion nach Extension/MIME
# ---------------------------------------------------------------------------

class TestExtractText:
    """Prüft _extract_text fuer verschiedene Dateitypen."""

    def test_plain_text_by_extension(self):
        data = "Hello World".encode("utf-8")
        result = _extract_text(data, "notes.txt", "")
        assert result == "Hello World"

    def test_markdown_by_extension(self):
        data = "# Heading".encode("utf-8")
        result = _extract_text(data, "doc.md", "")
        assert result == "# Heading"

    def test_python_by_extension(self):
        data = "print('hi')".encode("utf-8")
        result = _extract_text(data, "script.py", "")
        assert result == "print('hi')"

    def test_text_by_mime_type(self):
        """Fallback: text/plain MIME erkennt unbekannte Extension."""
        data = "Inhalt".encode("utf-8")
        result = _extract_text(data, "unknown.xyz", "text/plain")
        assert result == "Inhalt"

    def test_binary_file_returns_none(self):
        data = b"\x89PNG\r\n\x1a\n"
        result = _extract_text(data, "image.png", "image/png")
        assert result is None

    def test_unknown_extension_no_mime_returns_none(self):
        data = b"some bytes"
        result = _extract_text(data, "file.bin", "application/octet-stream")
        assert result is None

    def test_utf8_with_replacement(self):
        """Ungültige UTF-8-Bytes werden ersetzt statt Exception."""
        data = b"G\xfcltig"
        result = _extract_text(data, "test.txt", "")
        assert result is not None
        assert "ltig" in result

    @pytest.mark.parametrize("ext", [".md", ".csv", ".json", ".yaml", ".sql", ".sh"])
    def test_allowed_extensions(self, ext):
        data = f"content-{ext}".encode("utf-8")
        result = _extract_text(data, f"test{ext}", "")
        assert result is not None


# ---------------------------------------------------------------------------
# Konstanten-Validierung
# ---------------------------------------------------------------------------

class TestConstants:
    """Stellt sicher, dass sicherheitsrelevante Konstanten korrekte Werte haben."""

    def test_max_total_chars(self):
        assert MAX_TOTAL_CHARS == 100_000

    def test_max_files_per_request(self):
        assert MAX_FILES_PER_REQUEST == 20

    def test_allowed_extensions_contain_common_types(self):
        for ext in (".md", ".txt", ".csv", ".json", ".py", ".sql"):
            assert ext in ALLOWED_TEXT_EXTENSIONS

    def test_allowed_extensions_exclude_dangerous_types(self):
        for ext in (".exe", ".dll", ".so", ".bat", ".cmd"):
            assert ext not in ALLOWED_TEXT_EXTENSIONS

    def test_upload_dir_is_absolute(self):
        assert ALLOWED_UPLOAD_DIR.is_absolute()


# ---------------------------------------------------------------------------
# _resolve_local_upload — Path-Traversal-Schutz
# ---------------------------------------------------------------------------

class TestResolveLocalUpload:
    """Prüft Path-Traversal-Schutz und Datei-Handling bei lokalen Uploads."""

    def test_path_traversal_blocked(self, tmp_path):
        """Directory-Traversal (../) wird blockiert."""
        ctx = ResolvedContext()
        source = {"upload_id": "../../../etc/passwd", "name": "attack.txt"}

        with patch(
            "app.services.context_resolver.ALLOWED_UPLOAD_DIR", tmp_path
        ):
            _resolve_local_upload(ctx, source)

        assert len(ctx.files) == 0

    def test_valid_upload_file(self, tmp_path):
        """Gültige Datei im Upload-Verzeichnis wird gelesen."""
        test_file = tmp_path / "doc.txt"
        test_file.write_text("Testinhalt", encoding="utf-8")

        ctx = ResolvedContext()
        source = {"upload_id": "doc.txt", "name": "Dokument"}

        with patch(
            "app.services.context_resolver.ALLOWED_UPLOAD_DIR", tmp_path
        ):
            _resolve_local_upload(ctx, source)

        assert len(ctx.files) == 1
        assert ctx.files[0]["content"] == "Testinhalt"
        assert ctx.files[0]["source"] == "Upload"

    def test_nonexistent_file(self, tmp_path):
        """Nicht existierende Datei wird übersprungen."""
        ctx = ResolvedContext()
        source = {"upload_id": "missing.txt", "name": "ghost"}

        with patch(
            "app.services.context_resolver.ALLOWED_UPLOAD_DIR", tmp_path
        ):
            _resolve_local_upload(ctx, source)

        assert len(ctx.files) == 0

    def test_unsupported_extension(self, tmp_path):
        """Nicht-Text-Dateien erhalten eine Hinweis-Meldung."""
        binary_file = tmp_path / "image.png"
        binary_file.write_bytes(b"\x89PNG")

        ctx = ResolvedContext()
        source = {"upload_id": "image.png", "name": "Bild"}

        with patch(
            "app.services.context_resolver.ALLOWED_UPLOAD_DIR", tmp_path
        ):
            _resolve_local_upload(ctx, source)

        assert len(ctx.files) == 1
        assert "wird nicht als Text unterstützt" in ctx.files[0]["content"]

    def test_symlink_escape_blocked(self, tmp_path):
        """Symlink der aus dem Upload-Verzeichnis zeigt, wird blockiert."""
        secret = tmp_path / "outside" / "secret.txt"
        secret.parent.mkdir()
        secret.write_text("geheim", encoding="utf-8")

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()
        link = upload_dir / "link.txt"
        link.symlink_to(secret)

        ctx = ResolvedContext()
        source = {"upload_id": "link.txt", "name": "sneaky"}

        with patch(
            "app.services.context_resolver.ALLOWED_UPLOAD_DIR", upload_dir
        ):
            _resolve_local_upload(ctx, source)

        assert len(ctx.files) == 0

    def test_markdown_upload(self, tmp_path):
        """Markdown-Datei wird korrekt als Text gelesen."""
        md_file = tmp_path / "notes.md"
        md_file.write_text("# Notizen\n\n- Punkt 1", encoding="utf-8")

        ctx = ResolvedContext()
        source = {"upload_id": "notes.md", "name": "Notizen"}

        with patch(
            "app.services.context_resolver.ALLOWED_UPLOAD_DIR", tmp_path
        ):
            _resolve_local_upload(ctx, source)

        assert len(ctx.files) == 1
        assert "# Notizen" in ctx.files[0]["content"]

    def test_subdirectory_traversal_blocked(self, tmp_path):
        """Traversal via Subdirectory (subdir/../../etc/passwd) wird blockiert."""
        ctx = ResolvedContext()
        source = {"upload_id": "subdir/../../etc/passwd", "name": "trick"}

        with patch(
            "app.services.context_resolver.ALLOWED_UPLOAD_DIR", tmp_path
        ):
            _resolve_local_upload(ctx, source)

        assert len(ctx.files) == 0
