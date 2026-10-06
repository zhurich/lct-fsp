from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings
from app.core.db import utcnow

_hasher = PasswordHasher()
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_token(user_id: int, purpose: str, ttl: timedelta, session_id: str | None = None) -> str:
    payload = {"sub": str(user_id), "purpose": purpose, "exp": utcnow() + ttl}
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def _decode(token: str, purpose: str) -> tuple[int, dict] | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != purpose:
        return None
    try:
        return int(payload["sub"]), payload
    except (KeyError, TypeError, ValueError):
        return None


def decode_token(token: str, purpose: str) -> int | None:
    """Возвращает id пользователя либо None, если токен невалиден, истёк или выдан для другой цели."""
    decoded = _decode(token, purpose)
    return decoded[0] if decoded else None


def decode_access_token(token: str) -> tuple[int, str] | None:
    """Возвращает id пользователя и id сессии из токена доступа; токен без сессии не принимается."""
    decoded = _decode(token, "access")
    if decoded is None or not isinstance(decoded[1].get("sid"), str):
        return None
    return decoded[0], decoded[1]["sid"]
