from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db, utcnow
from app.core.security import decode_access_token
from app.modules.auth.models import AuthSession, Role, User

ACCESS_COOKIE = "access_token"


def find_session(db: Session, access_token: str | None) -> AuthSession | None:
    """Действующая сессия по токену доступа; после выхода строки нет, и подписанный токен не принимается."""
    decoded = decode_access_token(access_token) if access_token else None
    if decoded is None:
        return None
    user_id, session_id = decoded
    session = db.get(AuthSession, session_id)
    if session is None or session.user_id != user_id or session.expires_at <= utcnow():
        return None
    return session


def get_current_user(
    access_token: str | None = Cookie(default=None, include_in_schema=False),
    db: Session = Depends(get_db),
) -> User:
    session = find_session(db, access_token)
    user = db.get(User, session.user_id) if session else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется вход в систему")
    return user


def require_role(role: Role):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role != role:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав для этого раздела")
        return user

    return dependency


current_candidate = require_role(Role.candidate)
current_employer = require_role(Role.employer)
