"""Router für Chat-Nachrichten-Export (Markdown, Word, PDF, PowerPoint).

Alle Konvertierungen laufen über den contentConverter MCP-Client-Service --
ein einziger Codepath für Agent und Chat-Modus.
"""

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
from app.database import get_db
from app.models import User
from app.models.models import LlmMessage
from app.services import content_converter as cc

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
    """Exportiert als PowerPoint via contentConverter MCP-Server."""
    pptx_template = body.pptx_template
    if not pptx_template:
        from app.config import get_settings
        settings = get_settings()
        template_dir = Path(settings.pptx_template_dir)
        candidates = list(template_dir.glob("*.pptx")) if template_dir.exists() else []
        if candidates:
            pptx_template = str(candidates[0])

    if not pptx_template:
        raise HTTPException(
            status_code=400,
            detail="Kein PPTX-Template gefunden. Bitte Template-Pfad angeben.",
        )

    slide_script = await cc.call_tool("prepare_for_slides", text=content)

    tmp_md = EXPORT_TMP_DIR / f"{uuid.uuid4().hex}.md"
    tmp_md.write_text(
        slide_script if isinstance(slide_script, str) else str(slide_script),
        encoding="utf-8",
    )

    try:
        result_path = await cc.call_tool(
            "convert_to_pptx",
            input_file=str(tmp_md),
            template=pptx_template,
            output=str(EXPORT_TMP_DIR / f"{uuid.uuid4().hex}.pptx"),
        )
    except Exception as e:
        logger.error("PowerPoint-Konvertierung fehlgeschlagen: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"PowerPoint-Konvertierung fehlgeschlagen: {e}",
        )
    finally:
        tmp_md.unlink(missing_ok=True)

    output_path = result_path if isinstance(result_path, str) else str(result_path)

    return FileResponse(
        output_path,
        filename=f"{base_name}.pptx",
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


async def _export_docx_pdf(
    content: str,
    base_name: str,
    body: ExportRequest,
) -> FileResponse:
    """Exportiert als Word oder PDF via contentConverter MCP-Server."""
    prepared = await cc.call_tool(
        "prepare_for_word",
        text=content,
        title=body.title,
        author=body.author,
        lang="de-CH",
    )

    tmp_md = EXPORT_TMP_DIR / f"{uuid.uuid4().hex}.md"
    tmp_md.write_text(
        prepared if isinstance(prepared, str) else str(prepared),
        encoding="utf-8",
    )

    try:
        docx_output = str(EXPORT_TMP_DIR / f"{uuid.uuid4().hex}.docx")
        docx_path = await cc.call_tool(
            "convert_to_word",
            input_file=str(tmp_md),
            output=docx_output,
            lang="de-CH",
            author=body.author,
            title=body.title,
            template=body.template,
        )
    except Exception as e:
        logger.error("Word-Konvertierung fehlgeschlagen: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Konvertierung fehlgeschlagen: {e}",
        )
    finally:
        tmp_md.unlink(missing_ok=True)

    docx_path_str = docx_path if isinstance(docx_path, str) else str(docx_path)

    if body.format == "pdf":
        try:
            pdf_path = await cc.call_tool(
                "convert_to_pdf",
                input_file=docx_path_str,
            )
        except Exception as e:
            logger.error("PDF-Konvertierung fehlgeschlagen: %s", e)
            raise HTTPException(
                status_code=500,
                detail=f"PDF-Konvertierung fehlgeschlagen: {e}",
            )
        return FileResponse(
            pdf_path if isinstance(pdf_path, str) else str(pdf_path),
            filename=f"{base_name}.pdf",
            media_type="application/pdf",
        )

    return FileResponse(
        docx_path_str,
        filename=f"{base_name}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
