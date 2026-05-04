"""Router für Chat-Nachrichten-Export (Markdown, Word, PDF, PowerPoint)."""

import logging
import tempfile
import uuid
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.models.models import LlmMessage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat-export"])

EXPORT_TMP_DIR = Path(tempfile.gettempdir()) / "taskpilot-exports"
EXPORT_TMP_DIR.mkdir(parents=True, exist_ok=True)


class ExportRequest(BaseModel):
    format: Literal["markdown", "docx", "pdf", "pptx"]
    title: str = "Export"
    author: str = "InnoSmith"
    title_page: bool = True
    toc: bool = True
    template: str | None = None
    pptx_template: str | None = None
    filename: str | None = None


def prepare_markdown_for_docx(
    content: str,
    title: str,
    author: str,
    title_page: bool = True,
) -> str:
    """Bereitet Chat-Markdown fuer den mdConverter auf.

    Fuegt YAML-Frontmatter und optionalen Titelblock hinzu,
    wenn diese im Content fehlen.
    """
    today = date.today()
    today_iso = today.strftime("%Y-%m-%d")
    lines = content.strip().split("\n")
    has_frontmatter = len(lines) > 0 and lines[0].strip() == "---"
    has_h1 = any(line.startswith("# ") for line in lines[:5])

    parts: list[str] = []

    if not has_frontmatter:
        parts.append(
            f'---\ntitle: "{title}"\nauthor: "{author}"\n'
            f'date: "{today_iso}"\nlang: "de-CH"\n---\n'
        )

    if title_page and not has_h1:
        month_year = today.strftime("%B %Y")
        parts.append(
            f"# {title}\n\n## \n\n"
            f"| | |\n|---|---|\n"
            f"| **Autor** | {author} |\n"
            f"| **Datum** | {month_year} |\n\n---\n"
        )

    parts.append(content)
    return "\n".join(parts)


@router.post("/messages/{msg_id}/export")
async def export_message(
    msg_id: str,
    body: ExportRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exportiert eine Chat-Nachricht als Markdown, DOCX, PDF oder PPTX."""
    result = await db.execute(
        select(LlmMessage).where(LlmMessage.id == msg_id)
    )
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Nachricht nicht gefunden")

    base_name = body.filename or f"export-{date.today().isoformat()}"

    if body.format == "markdown":
        md_path = EXPORT_TMP_DIR / f"{uuid.uuid4().hex}.md"
        md_path.write_text(msg.content, encoding="utf-8")
        return FileResponse(
            str(md_path),
            filename=f"{base_name}.md",
            media_type="text/markdown",
        )

    if body.format == "pptx":
        return await _export_pptx(msg.content, base_name, body)

    return await _export_docx_pdf(msg.content, base_name, body)


async def _export_pptx(
    content: str,
    base_name: str,
    body: ExportRequest,
) -> FileResponse:
    """Exportiert als PowerPoint via md2powerpoint."""
    try:
        from md2powerpoint.parser import parse_markdown
        from md2powerpoint.classifier import classify_slides
        from md2powerpoint.builder import build_presentation
        from md2powerpoint.config import ConverterConfig
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="md2powerpoint ist nicht installiert",
        )

    settings = get_settings()
    template_dir = Path(settings.pptx_template_dir)

    template_path = None
    if body.pptx_template:
        template_path = Path(body.pptx_template)
    else:
        candidates = list(template_dir.glob("*.pptx")) if template_dir.exists() else []
        if candidates:
            template_path = candidates[0]

    if not template_path or not template_path.exists():
        raise HTTPException(
            status_code=400,
            detail="Kein PPTX-Template gefunden. Bitte Template-Pfad angeben.",
        )

    try:
        slides = classify_slides(parse_markdown(content))
        prs = build_presentation(slides, template_path, ConverterConfig())
        output_path = EXPORT_TMP_DIR / f"{uuid.uuid4().hex}.pptx"
        prs.save(str(output_path))
    except Exception as e:
        logger.error("PowerPoint-Konvertierung fehlgeschlagen: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"PowerPoint-Konvertierung fehlgeschlagen: {e}",
        )

    return FileResponse(
        str(output_path),
        filename=f"{base_name}.pptx",
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


async def _export_docx_pdf(
    content: str,
    base_name: str,
    body: ExportRequest,
) -> FileResponse:
    """Exportiert als Word oder PDF via mdConverter."""
    try:
        from mdconverter import convert, convert_to_pdf
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="mdconverter ist nicht installiert",
        )

    prepared = prepare_markdown_for_docx(
        content,
        title=body.title,
        author=body.author,
        title_page=body.title_page,
    )

    tmp_md = EXPORT_TMP_DIR / f"{uuid.uuid4().hex}.md"
    tmp_md.write_text(prepared, encoding="utf-8")

    reference_doc = None
    if body.template:
        settings = get_settings()
        ref_candidate = Path(settings.mdconverter_path) / "templates" / f"{body.template}.docx"
        if ref_candidate.exists():
            reference_doc = str(ref_candidate)

    try:
        docx_path = convert(
            input_file=str(tmp_md),
            output=str(EXPORT_TMP_DIR / f"{uuid.uuid4().hex}.docx"),
            title_page=body.title_page,
            toc=body.toc,
            reference_doc=reference_doc,
            title=body.title,
            author=body.author,
        )
    except Exception as e:
        logger.error("mdConverter-Fehler: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Konvertierung fehlgeschlagen: {e}",
        )
    finally:
        tmp_md.unlink(missing_ok=True)

    if body.format == "pdf":
        try:
            pdf_path = convert_to_pdf(str(docx_path))
        except Exception as e:
            logger.error("PDF-Konvertierung fehlgeschlagen: %s", e)
            raise HTTPException(
                status_code=500,
                detail=f"PDF-Konvertierung fehlgeschlagen: {e}",
            )
        return FileResponse(
            str(pdf_path),
            filename=f"{base_name}.pdf",
            media_type="application/pdf",
        )

    return FileResponse(
        str(docx_path),
        filename=f"{base_name}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
