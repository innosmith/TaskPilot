import logging
import time
from collections import defaultdict

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import decode_access_token
from app.database import get_db
from app.models import User

logger = logging.getLogger("taskpilot.auth")

security_scheme = HTTPBearer()

API_KEY_PREFIX = "tpk_"

_apikey_failures: dict[str, list[float]] = defaultdict(list)
_APIKEY_RATE_WINDOW = 300
_APIKEY_RATE_MAX = 20


def _check_apikey_rate_limit(ip: str) -> None:
    now = time.time()
    attempts = _apikey_failures[ip]
    _apikey_failures[ip] = [t for t in attempts if now - t < _APIKEY_RATE_WINDOW]
    if len(_apikey_failures[ip]) >= _APIKEY_RATE_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Zu viele fehlgeschlagene Authentifizierungsversuche.",
        )


async def _authenticate_via_api_key(
    token: str, db: AsyncSession, client_ip: str
) -> User | None:
    """API-Key (tpk_...) gegen den Owner-User pruefen."""
    _check_apikey_rate_limit(client_ip)

    result = await db.execute(select(User).where(User.role == "owner"))
    owner = result.scalar_one_or_none()
    if owner is None or not owner.is_active:
        return None

    key_hash = (owner.settings or {}).get("extension_api_key_hash")
    if not key_hash:
        return None

    if bcrypt.checkpw(token.encode(), key_hash.encode()):
        return owner

    _apikey_failures[client_ip].append(time.time())
    logger.warning("Fehlgeschlagener API-Key-Versuch von %s", client_ip)
    return None


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials

    if token.startswith(API_KEY_PREFIX):
        client_ip = request.client.host if request.client else "unknown"
        user = await _authenticate_via_api_key(token, db, client_ip)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ungueltiger API-Key",
            )
        return user

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user


async def require_owner(user: User = Depends(get_current_user)) -> User:
    if user.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required")
    return user
