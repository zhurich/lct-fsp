from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db, utcnow
from app.core.deps import current_candidate, find_session
from app.core.security import create_token, decode_token
from app.modules.auth.models import Role, User
from app.modules.auth.router import start_session
from app.modules.auth.schemas import UserOut
from app.modules.candidates.models import CandidateProfile
from app.modules.candidates.router import get_or_create_profile
from app.modules.candidates.schemas import CandidateProfileOut
from app.modules.fsp.idp import FspIdentity, provider
from app.modules.fsp.registry import registry

router = APIRouter(tags=["Связь с ФСП ID"])
mock_router = APIRouter(prefix="/fsp-id", tags=["Демонстрационный ФСП ID (мок провайдера)"])

# Назначение state: вход на платформу либо привязка к уже открытому профилю (тогда в нём id пользователя).
_LOGIN, _LINK = "fsp-login", "fsp-link"
_STATE_TTL = timedelta(minutes=10)

_TAKEN = "Этот ФСП ID уже привязан к другому профилю"


class AuthorizeOut(BaseModel):
    url: str = Field(description="Адрес страницы входа ФСП ID, на который нужно перейти")


class CallbackIn(BaseModel):
    code: str = Field(min_length=1, max_length=200)
    state: str = Field(min_length=1, max_length=2000)


class CallbackOut(BaseModel):
    user: UserOut
    intent: Literal["login", "link"]


def _sync(profile: CandidateProfile, fsp_id: str) -> None:
    """Копирует в профиль достижения и разряд участника из реестра."""
    achievements = registry.fetch(fsp_id)
    if achievements is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Участник не найден в реестре ФСП")
    profile.fsp_id = fsp_id
    profile.fsp_achievements = achievements
    profile.fsp_rank = registry.rank(fsp_id)
    profile.fsp_synced_at = utcnow()


@router.get("/auth/fsp/start", response_model=AuthorizeOut, summary="Начать вход через ФСП ID")
def start_login():
    return AuthorizeOut(url=provider.authorize_url(create_token(0, _LOGIN, _STATE_TTL)))


@router.get(
    "/candidate/fsp/start",
    response_model=AuthorizeOut,
    summary="Начать привязку ФСП ID к профилю: владение подтверждается входом в ФСП ID",
)
def start_link(user: User = Depends(current_candidate)):
    return AuthorizeOut(url=provider.authorize_url(create_token(user.id, _LINK, _STATE_TTL)))


def _login(db: Session, identity: FspIdentity, owner: CandidateProfile | None) -> User:
    """Пользователь платформы для участника ФСП: уже привязанный либо созданный при первом входе."""
    if owner:
        return db.get(User, owner.user_id)
    if db.scalar(select(User).where(User.email == identity.email)):
        # Учётные записи не объединяются по совпадению почты: иначе вход в ФСП ID давал бы доступ к
        # чужому профилю на платформе.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Эта почта уже зарегистрирована на платформе. Войдите по паролю и привяжите ФСП ID в настройках",
        )
    # Пароля у такой записи нет — вход только через ФСП ID. Почту подтвердил провайдер; согласие на
    # обработку данных даётся на экране входа.
    user = User(email=identity.email, password_hash="", role=Role.candidate, email_verified=True, consent_at=utcnow())
    db.add(user)
    db.flush()
    _sync(get_or_create_profile(db, user), identity.sub)
    return user


@router.post(
    "/auth/fsp/callback",
    response_model=CallbackOut,
    summary="Завершить вход или привязку: обмен кода ФСП ID на сведения об участнике",
    responses={
        400: {"description": "Код или state недействительны либо устарели"},
        401: {"description": "Привязку завершает не тот пользователь, который её начал"},
        409: {"description": "ФСП ID привязан к другому профилю либо почта уже зарегистрирована"},
    },
)
def callback(
    data: CallbackIn,
    response: Response,
    access_token: str | None = Cookie(default=None, include_in_schema=False),
    db: Session = Depends(get_db),
):
    link_user_id = decode_token(data.state, _LINK)
    if link_user_id is None and decode_token(data.state, _LOGIN) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Запрос на вход устарел. Начните заново")
    identity = provider.exchange(data.code)
    if identity is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Код входа недействителен или устарел. Начните заново")
    owner = db.scalar(select(CandidateProfile).where(CandidateProfile.fsp_id == identity.sub))
    try:
        if link_user_id is None:
            user = _login(db, identity, owner)
            db.commit()
            start_session(response, user, db)
            return CallbackOut(user=user, intent="login")
        user = db.get(User, link_user_id)
        session = find_session(db, access_token)
        if user is None or session is None or session.user_id != user.id:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется вход в систему")
        if owner and owner.user_id != user.id:
            raise HTTPException(status.HTTP_409_CONFLICT, _TAKEN)
        _sync(get_or_create_profile(db, user), identity.sub)
        db.commit()
    except IntegrityError:
        # Параллельный запрос успел занять этот ФСП ID или почту.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, _TAKEN) from None
    return CallbackOut(user=user, intent="link")


@router.post(
    "/candidate/fsp/refresh",
    response_model=CandidateProfileOut,
    summary="Обновить достижения из реестра ФСП",
    responses={409: {"description": "ФСП ID не привязан"}},
)
def refresh(user: User = Depends(current_candidate), db: Session = Depends(get_db)):
    profile = get_or_create_profile(db, user)
    if profile.fsp_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "ФСП ID не привязан")
    _sync(profile, profile.fsp_id)
    db.commit()
    return profile


@router.delete(
    "/candidate/fsp",
    response_model=CandidateProfileOut,
    summary="Отвязать ФСП ID",
    responses={409: {"description": "Учётная запись создана через ФСП ID: другого способа входа нет"}},
)
def unlink(user: User = Depends(current_candidate), db: Session = Depends(get_db)):
    if not user.password_hash:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Вы вошли через ФСП ID, другого способа входа у этой учётной записи нет. Достижения можно скрыть "
            "от работодателей в настройках выше",
        )
    profile = get_or_create_profile(db, user)
    profile.fsp_id = None
    profile.fsp_achievements = []
    profile.fsp_rank = None
    profile.fsp_synced_at = None
    db.commit()
    return profile


class MockLoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class MockCodeOut(BaseModel):
    code: str = Field(description="Одноразовый код, с которым пользователь возвращается на платформу")


class MockAccountsOut(BaseModel):
    password: str = Field(description="Общий пароль демонстрационного стенда")
    accounts: list[dict] = Field(description="Участники с заранее известной историей: почта и описание")


@mock_router.post(
    "/login",
    response_model=MockCodeOut,
    summary="Страница входа демонстрационного ФСП ID: проверка пароля и выдача кода",
    responses={401: {"description": "Неверный пароль"}},
)
def mock_login(data: MockLoginIn):
    code = provider.login(data.email.lower(), data.password)
    if code is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверная почта или пароль ФСП ID")
    return MockCodeOut(code=code)


@mock_router.get("/accounts", response_model=MockAccountsOut, summary="Подсказка для страницы входа: демо-участники")
def mock_accounts():
    return MockAccountsOut(
        password=provider.DEMO_PASSWORD,
        accounts=[{"email": email, "note": note} for email, (_, note) in provider.DEMO_ACCOUNTS.items()],
    )
