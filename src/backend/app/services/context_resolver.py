"""Context Resolver: Löst Datei-Referenzen (OneDrive, lokale Uploads) auf
und extrahiert Text als LLM-Kontext.

Sicherheitsmodell:
- OneDrive: Lesen erlaubt (via Graph API mit OAuth-Scoping)
- Lokale Uploads: Lesen erlaubt (User hat Datei explizit bereitgestellt)
- Beliebige lokale Pfade: Gesperrt (kein unkontrollierter Dateisystem-Zugriff)
"""

import hashlib
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MAX_TOTAL_CHARS = 100_000
MAX_FILES_PER_REQUEST = 20
FILE_CACHE_DIR = Path("/tmp/taskpilot-files")

ALLOWED_TEXT_EXTENSIONS = {
    ".md", ".txt", ".csv", ".json", ".xml", ".yaml", ".yml",
    ".py", ".js", ".ts", ".html", ".css", ".sql", ".sh",
    ".log", ".ini", ".toml", ".cfg", ".conf",
}

ALLOWED_UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"


class ContextSource:
    """Basisklasse fuer Kontext-Quellen."""

    def __init__(self, source_type: str, name: str, **kwargs):
        self.source_type = source_type
        self.name = name
        self.metadata = kwargs


class ResolvedContext:
    """Aufgelöster Kontext mit Dateiinhalten."""

    def __init__(self):
        self.files: list[dict] = []
        self.total_chars: int = 0
        self.truncated: bool = False

    def add_file(self, name: str, content: str, source: str):
        """Fügt eine Datei zum Kontext hinzu (mit Limits)."""
        if len(self.files) >= MAX_FILES_PER_REQUEST:
            self.truncated = True
            return

        remaining = MAX_TOTAL_CHARS - self.total_chars
        if remaining <= 0:
            self.truncated = True
            return

        if len(content) > remaining:
            content = content[:remaining] + "\n\n[... Text gekürzt ...]"
            self.truncated = True

        self.files.append({
            "name": name,
            "content": content,
            "source": source,
            "chars": len(content),
        })
        self.total_chars += len(content)

    def to_llm_context(self) -> str:
        """Generiert einen formatierten Kontext-String fuer das LLM."""
        if not self.files:
            return ""

        parts = ["<attached_files>"]
        for f in self.files:
            parts.append(f"\n## Datei: {f['name']} ({f['source']})\n")
            parts.append(f['content'])
        parts.append("\n</attached_files>")

        if self.truncated:
            parts.append(
                "\n[Hinweis: Einige Dateien wurden gekürzt oder ausgelassen "
                f"(Limit: {MAX_TOTAL_CHARS:,} Zeichen, {MAX_FILES_PER_REQUEST} Dateien)]"
            )

        return "\n".join(parts)


async def resolve_context_sources(
    sources: list[dict],
    graph_client=None,
) -> ResolvedContext:
    """Löst eine Liste von Kontext-Quellen auf und extrahiert Text.

    Args:
        sources: Liste von Quell-Definitionen
        graph_client: Optional vorkonfigurierter GraphClient

    Returns:
        ResolvedContext mit extrahierten Dateiinhalten
    """
    ctx = ResolvedContext()

    for source in sources:
        source_type = source.get("type", "")

        if source_type == "onedrive_file":
            await _resolve_onedrive_file(ctx, source, graph_client)
        elif source_type == "onedrive_folder":
            await _resolve_onedrive_folder(ctx, source, graph_client)
        elif source_type == "local_upload":
            _resolve_local_upload(ctx, source)
        else:
            logger.warning("Unbekannter Kontext-Quelltyp: %s", source_type)

        if ctx.truncated:
            break

    return ctx


async def _resolve_onedrive_file(
    ctx: ResolvedContext,
    source: dict,
    graph_client,
):
    """Löst eine einzelne OneDrive-Datei auf."""
    if not graph_client:
        logger.warning("Graph-Client nicht verfügbar für OneDrive-Datei")
        return

    item_id = source.get("item_id", "")
    name = source.get("name", "unbekannt")

    try:
        meta = await graph_client.get_drive_item(item_id)
        filename = meta.get("name", name)
        mime = (meta.get("file") or {}).get("mimeType", "")
        size = meta.get("size", 0)

        if size > 10 * 1024 * 1024:
            ctx.add_file(filename, f"[Datei zu gross: {size:,} Bytes]", "OneDrive")
            return

        data = await graph_client.download_drive_item(item_id)
        text = _extract_text(data, filename, mime)

        if text:
            ctx.add_file(filename, text, "OneDrive")
        else:
            ctx.add_file(filename, f"[Textextraktion nicht möglich: {mime}]", "OneDrive")

    except Exception as e:
        logger.error("OneDrive-Datei %s konnte nicht geladen werden: %s", name, e)
        ctx.add_file(name, f"[Fehler beim Laden: {e}]", "OneDrive")


async def _resolve_onedrive_folder(
    ctx: ResolvedContext,
    source: dict,
    graph_client,
):
    """Löst einen OneDrive-Ordner auf (optional rekursiv)."""
    if not graph_client:
        return

    path = source.get("path", "/")
    recursive = source.get("recursive", False)

    try:
        items = await graph_client.list_drive_items(path=path, top=50)
        for item in items:
            if ctx.truncated:
                break

            if item.get("folder") and recursive:
                child_path = f"{path.rstrip('/')}/{item['name']}"
                await _resolve_onedrive_folder(
                    ctx,
                    {"path": child_path, "recursive": True},
                    graph_client,
                )
            elif item.get("file"):
                await _resolve_onedrive_file(
                    ctx,
                    {"item_id": item["id"], "name": item["name"]},
                    graph_client,
                )

    except Exception as e:
        logger.error("OneDrive-Ordner %s konnte nicht geladen werden: %s", path, e)


def _resolve_local_upload(ctx: ResolvedContext, source: dict):
    """Löst eine lokal hochgeladene Datei auf (Sicherheitsprüfung inklusive)."""
    upload_id = source.get("upload_id", "")
    name = source.get("name", "upload")

    resolved = ALLOWED_UPLOAD_DIR / upload_id
    try:
        resolved = resolved.resolve()
    except (OSError, ValueError):
        logger.warning("Ungültiger Upload-Pfad: %s", upload_id)
        return

    if not str(resolved).startswith(str(ALLOWED_UPLOAD_DIR.resolve())):
        logger.warning("Path-Traversal-Versuch blockiert: %s", upload_id)
        return

    if not resolved.exists():
        logger.warning("Upload-Datei nicht gefunden: %s", resolved)
        return

    ext = resolved.suffix.lower()
    if ext in ALLOWED_TEXT_EXTENSIONS:
        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
            ctx.add_file(name, text, "Upload")
        except Exception as e:
            ctx.add_file(name, f"[Fehler beim Lesen: {e}]", "Upload")
    else:
        ctx.add_file(name, f"[Dateityp {ext} wird nicht als Text unterstützt]", "Upload")


def _extract_text(data: bytes, filename: str, mime: str) -> Optional[str]:
    """Extrahiert Text aus heruntergeladenen Datei-Bytes."""
    ext = Path(filename).suffix.lower()

    if ext in ALLOWED_TEXT_EXTENSIONS or mime.startswith("text/"):
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return None

    if ext == ".pdf":
        return _extract_pdf_text(data)

    if ext in (".docx",):
        return _extract_docx_text(data)

    return None


def _extract_pdf_text(data: bytes) -> Optional[str]:
    """Extrahiert Text aus PDF-Bytes via PyMuPDF."""
    try:
        import fitz
        doc = fitz.open(stream=data, filetype="pdf")
        pages = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        return "\n\n".join(pages)
    except ImportError:
        logger.warning("PyMuPDF (fitz) nicht installiert — PDF-Extraktion nicht möglich")
        return None
    except Exception as e:
        logger.error("PDF-Extraktion fehlgeschlagen: %s", e)
        return None


def _extract_docx_text(data: bytes) -> Optional[str]:
    """Extrahiert Text aus DOCX-Bytes via python-docx."""
    try:
        import io
        from docx import Document
        doc = Document(io.BytesIO(data))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        logger.warning("python-docx nicht installiert — DOCX-Extraktion nicht möglich")
        return None
    except Exception as e:
        logger.error("DOCX-Extraktion fehlgeschlagen: %s", e)
        return None
