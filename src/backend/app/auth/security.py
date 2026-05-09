from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import get_settings

settings = get_settings()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None


def create_refresh_token(data: dict, role: str = "owner") -> str:
    """Erstellt Refresh-Token mit rollenabhaengiger TTL (24h Owner, 4h Member)."""
    to_encode = data.copy()
    hours = settings.refresh_token_expire_hours if role == "owner" else 4
    expire = datetime.now(timezone.utc) + timedelta(hours=hours)
    to_encode["exp"] = expire
    to_encode["type"] = "refresh"
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_refresh_token(token: str) -> dict | None:
    """Dekodiert Refresh-Token und prueft, dass type == 'refresh'."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if payload.get("type") != "refresh":
            return None
        return payload
    except JWTError:
        return None
