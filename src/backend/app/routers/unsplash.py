import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.deps import get_current_user
from app.config import get_settings
from app.models import User

router = APIRouter(prefix="/api/unsplash", tags=["unsplash"])


@router.get("/search")
async def search_photos(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=30),
    _user: User = Depends(get_current_user),
) -> dict:
    settings = get_settings()
    if not settings.unsplash_access_key:
        raise HTTPException(status_code=503, detail="Unsplash not configured")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://api.unsplash.com/search/photos",
            params={"query": q, "page": page, "per_page": per_page, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {settings.unsplash_access_key}"},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Unsplash API error")

        data = resp.json()
        return {
            "total": data.get("total", 0),
            "results": [
                {
                    "id": photo["id"],
                    "thumb": photo["urls"]["small"],
                    "regular": photo["urls"]["regular"],
                    "full": photo["urls"]["full"],
                    "hq": _hq_url(photo["urls"].get("raw", photo["urls"]["full"])),
                    "author": photo["user"]["name"],
                    "author_url": photo["user"]["links"]["html"],
                    "description": photo.get("alt_description", ""),
                }
                for photo in data.get("results", [])
            ],
        }


def _hq_url(raw_url: str) -> str:
    """Hochwertige URL aus der Unsplash-Raw-URL generieren (1920px, Qualitaet 85%)."""
    base = raw_url.split("?")[0]
    return f"{base}?w=1920&q=85&fm=jpg&fit=crop&auto=format"
