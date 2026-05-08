"""Router für Chat-Nachrichten-Export (Markdown, Word, PDF, PowerPoint).

Alle Konvertierungen laufen über den contentConverter MCP-Client-Service --
ein einziger Codepath für Agent und Chat-Modus.
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Literal

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import User
from app.models.models import LlmMessage
from app.services.document_export import ConvertOptions, convert_markdown

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat-export"])


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

    opts = ConvertOptions(
        format=body.format,
        title=body.title,
        author=body.author,
        title_page=body.title_page,
        toc=body.toc,
        template=body.template,
        pptx_template=body.pptx_template,
        filename=body.filename,
    )

    return await convert_markdown(msg.content, base_name, opts)
