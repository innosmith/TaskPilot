import pathlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.models import User

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

UPLOADS_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "uploads"
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"}
MAX_SIZE = 2 * 1024 * 1024


class UploadResult(BaseModel):
    url: str


@router.post("/avatars", response_model=UploadResult)
async def upload_avatar(
    file: UploadFile,
    _user: User = Depends(get_current_user),
) -> UploadResult:
    return await _save_file(file, "avatars")


@router.post("/icons", response_model=UploadResult)
async def upload_icon(
    file: UploadFile,
    _user: User = Depends(get_current_user),
) -> UploadResult:
    return await _save_file(file, "icons")


async def _save_file(file: UploadFile, subfolder: str) -> UploadResult:
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Nicht erlaubter Dateityp")

    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="Datei zu gross (max 2 MB)")

    ext = pathlib.Path(file.filename or "img.png").suffix or ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOADS_DIR / subfolder / filename
    dest.write_bytes(data)

    return UploadResult(url=f"/uploads/{subfolder}/{filename}")
