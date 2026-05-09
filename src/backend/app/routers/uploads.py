import logging
import pathlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.auth.deps import get_current_user, require_role
from app.config import get_settings
from app.models import User

logger = logging.getLogger("taskpilot.uploads")

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

UPLOADS_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "uploads"
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
MAX_SIZE = 2 * 1024 * 1024


class UploadResult(BaseModel):
    url: str


async def _scan_with_clamav(data: bytes) -> bool:
    """Prueft Datei-Bytes via ClamAV. Gibt True zurueck wenn sauber."""
    settings = get_settings()
    clamav_host = getattr(settings, "clamav_host", "clamav")
    clamav_port = getattr(settings, "clamav_port", 3310)
    try:
        import aioclamd
        cd = aioclamd.ClamdAsyncClient(host=clamav_host, port=clamav_port)
        result = await cd.instream(data)
        if result and result.get("stream", ("OK",))[0] == "FOUND":
            logger.warning("ClamAV: Schädliche Datei erkannt: %s", result)
            return False
        return True
    except ImportError:
        logger.debug("aioclamd nicht installiert, Virus-Scan übersprungen")
        return True
    except Exception:
        logger.exception("ClamAV-Scan fehlgeschlagen, Upload wird trotzdem akzeptiert")
        return True


@router.post("/avatars", response_model=UploadResult)
async def upload_avatar(
    file: UploadFile,
    _user: User = Depends(require_role("member")),
) -> UploadResult:
    return await _save_file(file, "avatars")


@router.post("/icons", response_model=UploadResult)
async def upload_icon(
    file: UploadFile,
    _user: User = Depends(require_role("member")),
) -> UploadResult:
    return await _save_file(file, "icons")


@router.get("/icons/{filename}")
async def serve_icon(filename: str) -> FileResponse:
    """Icons/Logos ohne Auth ausliefern (nicht-sensible Assets)."""
    safe_filename = pathlib.Path(filename).name
    filepath = UPLOADS_DIR / "icons" / safe_filename
    if not filepath.is_file():
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")
    return FileResponse(filepath)


@router.get("/avatars/{filename}")
async def serve_avatar(filename: str) -> FileResponse:
    """Avatars ohne Auth ausliefern (Profilbilder, nicht-sensitiv)."""
    safe_filename = pathlib.Path(filename).name
    filepath = UPLOADS_DIR / "avatars" / safe_filename
    if not filepath.is_file():
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")
    return FileResponse(filepath)


@router.get("/tasks/{task_id}/{filename}")
async def serve_task_attachment(
    task_id: str,
    filename: str,
    _user: User = Depends(require_role("member")),
) -> FileResponse:
    """Task-Attachments mit Auth ausliefern."""
    safe_task_id = pathlib.Path(task_id).name
    safe_filename = pathlib.Path(filename).name
    filepath = UPLOADS_DIR / "tasks" / safe_task_id / safe_filename
    if not filepath.is_file():
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")
    return FileResponse(filepath)


@router.get("/{subfolder}/{filename}")
async def serve_upload(
    subfolder: str,
    filename: str,
    _user: User = Depends(require_role("member")),
) -> FileResponse:
    safe_subfolder = pathlib.Path(subfolder).name
    safe_filename = pathlib.Path(filename).name
    filepath = UPLOADS_DIR / safe_subfolder / safe_filename
    if not filepath.is_file():
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")
    return FileResponse(filepath)


async def _save_file(file: UploadFile, subfolder: str) -> UploadResult:
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Nicht erlaubter Dateityp")

    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="Datei zu gross (max 2 MB)")

    is_clean = await _scan_with_clamav(data)
    if not is_clean:
        raise HTTPException(status_code=422, detail="Datei wurde als schädlich erkannt")

    ext = pathlib.Path(file.filename or "img.png").suffix or ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOADS_DIR / subfolder / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    return UploadResult(url=f"/api/uploads/{subfolder}/{filename}")
