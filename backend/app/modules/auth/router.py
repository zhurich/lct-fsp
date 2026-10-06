import logging
import secrets
import smtplib
from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import mail
from app.core.config import settings
from app.core.db import Base, get_db, utcnow
from app.core.deps import ACCESS_COOKIE, find_session, get_current_user
from app.core.ratelimit import RateLimiter
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.modules.auth.models import AuthSession, User
from app.modules.auth.schemas import EmailIn, LoginIn, Message, RegisteredOut, RegisterIn, TokenIn, UserOut

router = APIRouter(prefix="/auth", tags=["Авторизация"])
logger = logging.getLogger("app.auth")

# Письмо подтверждения: не чаще раза в минуту и пяти раз в час на адрес, двадцати запросов в час с одного
# источника — иначе чужой адрес можно завалить письмами.
resend_pause = RateLimiter(1, 60)
resend_per_email = RateLimiter(5, 3600)
resend_per_source = RateLimiter(20, 3600)
# Подбор пароля: десять неудачных входов на адрес или пятьдесят с одного источника за 15 минут.
failed_logins_per_email = RateLimiter(10, 900)
failed_logins_per_source = RateLimiter(50, 900)
LIMITERS = (resend_pause, resend_per_email, resend_per_source, failed_logins_per_email, failed_logins_per_source)

_TOO_MANY = {429: {"description": "Слишком много запросов"}}


def _source(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def start_session(response: Response, user: User, db: Session) -> None:
    """Открывает сессию и выдаёт токен доступа в httpOnly-cookie; общий для входа по паролю и через ФСП ID."""
    ttl = timedelta(minutes=settings.access_token_ttl_min)
    now = utcnow()
    # Истёкшие сессии пользователя убираются при входе, отдельной фоновой очистки нет.
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id, AuthSession.expires_at <= now))
    session = AuthSession(id=secrets.token_urlsafe(32), user_id=user.id, expires_at=now + ttl)
    db.add(session)
    db.commit()
    response.set_cookie(
        ACCESS_COOKIE,
        create_token(user.id, "access", ttl, session.id),
        max_age=int(ttl.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


def _send_verification(user: User) -> None:
    token = create_token(user.id, "verify", timedelta(hours=settings.verify_token_ttl_hours))
    link = f"{settings.frontend_url}/verify?token={token}"
    mail.send_mail(
        user.email,
        "Подтверждение регистрации",
        f"Чтобы завершить регистрацию, перейдите по ссылке:\n{link}\n\n"
        f"Ссылка действует {settings.verify_token_ttl_hours} ч.",
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=RegisteredOut,
    summary="Регистрация по электронной почте",
    responses={
        409: {"description": "Почта уже зарегистрирована"},
        503: {"description": "Не удалось отправить письмо; учётная запись не создана"},
    },
)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с такой почтой уже зарегистрирован")
    user = User(
        email=email,
        password_hash=hash_password(data.password),
        role=data.role,
        consent_at=utcnow(),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с такой почтой уже зарегистрирован") from None
    if settings.demo_mode:
        # На стенде проверки письмо не нужно: проверяющий должен войти сразу после регистрации.
        user.email_verified = True
        db.commit()
        return RegisteredOut(
            message="Учётная запись создана. Стенд работает в демо-режиме: почту подтверждать не нужно", verified=True
        )
    # Запись сохраняется только после отправки письма: при сбое почты не остаётся учётной записи,
    # которую нельзя ни подтвердить, ни зарегистрировать заново.
    try:
        _send_verification(user)
    except (OSError, smtplib.SMTPException):
        db.rollback()
        logger.exception("Не удалось отправить письмо подтверждения для %s", email)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Не удалось отправить письмо с подтверждением. Учётная запись не создана — попробуйте ещё раз позже",
        ) from None
    db.commit()
    resend_pause.allow(email)
    return RegisteredOut(message="Письмо со ссылкой для подтверждения отправлено на указанную почту", verified=False)


@router.post(
    "/verify",
    response_model=Message,
    summary="Подтверждение адреса почты по токену из письма",
    responses={400: {"description": "Ссылка недействительна или устарела"}},
)
def verify(data: TokenIn, db: Session = Depends(get_db)):
    user_id = decode_token(data.token, "verify")
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ссылка недействительна или устарела")
    user.email_verified = True
    db.commit()
    return Message(message="Почта подтверждена")


@router.post(
    "/resend-verification",
    response_model=Message,
    summary="Повторная отправка письма (не чаще раза в минуту на адрес)",
    responses=_TOO_MANY,
)
def resend_verification(data: EmailIn, request: Request, db: Session = Depends(get_db)):
    email = data.email.lower()
    # Лимиты считаются до обращения к базе и одинаково для любых адресов: по ответу нельзя проверить,
    # зарегистрирована ли почта.
    if not resend_per_source.allow(_source(request)) or not resend_per_email.allow(email):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Слишком много запросов. Попробуйте позже")
    if not resend_pause.allow(email):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Письмо уже отправлено. Повторить можно через минуту"
        )
    user = db.scalar(select(User).where(User.email == email))
    if user and not user.email_verified:
        try:
            _send_verification(user)
        except (OSError, smtplib.SMTPException):
            logger.exception("Не удалось отправить письмо подтверждения для %s", email)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Не удалось отправить письмо. Попробуйте ещё раз позже"
            ) from None
    return Message(message="Если почта зарегистрирована и не подтверждена, письмо отправлено повторно")


@router.post(
    "/login",
    response_model=UserOut,
    summary="Вход; токен доступа выдаётся в httpOnly-cookie",
    responses={
        401: {"description": "Неверная почта или пароль"},
        403: {"description": "Почта не подтверждена"},
        **_TOO_MANY,
    },
)
def login(data: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    email, source = data.email.lower(), _source(request)
    if failed_logins_per_email.blocked(email) or failed_logins_per_source.blocked(source):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Слишком много неудачных попыток входа. Попробуйте через 15 минут"
        )
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(data.password, user.password_hash):
        failed_logins_per_email.allow(email)
        failed_logins_per_source.allow(source)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверная почта или пароль")
    if not user.email_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Почта не подтверждена. Перейдите по ссылке из письма")
    start_session(response, user, db)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Выход: сессия закрывается на сервере")
def logout(
    response: Response,
    access_token: str | None = Cookie(default=None, include_in_schema=False),
    db: Session = Depends(get_db),
):
    # Удаления cookie мало: токен, скопированный до выхода, оставался бы действующим до истечения срока.
    session = find_session(db, access_token)
    if session:
        db.delete(session)
        db.commit()
    response.delete_cookie(ACCESS_COOKIE)


@router.get("/me", response_model=UserOut, summary="Текущий пользователь")
def me(user: User = Depends(get_current_user)):
    return user


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отозвать согласие: удалить учётную запись и все связанные данные",
)
def delete_account(response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Удаляются строки всех таблиц, прямо или через другие таблицы ссылающихся на пользователя: профиль,
    # попытки тестов, категория, приглашения, потребности, вакансии с откликами, задания с ответами.
    # Список берётся из схемы, поэтому новые таблицы подхватываются сами, а результат не зависит от того,
    # включены ли в СУБД каскадные внешние ключи.
    # Таблицы обходятся от зависимых к главным: сначала строки, ссылающиеся на удаляемые (например,
    # отклики на вакансии удаляемого работодателя), затем сами удаляемые строки.
    doomed = {User.__table__: User.__table__.select().with_only_columns(User.id).where(User.id == user.id)}
    order = Base.metadata.sorted_tables
    for table in order:
        conditions = [
            column.in_(doomed[constraint.referred_table])
            for constraint in table.foreign_key_constraints
            if constraint.referred_table in doomed
            for column in constraint.columns
        ]
        if conditions and table is not User.__table__:
            key = list(table.primary_key.columns)[0]
            doomed[table] = table.select().with_only_columns(key).where(or_(*conditions))
    for table in reversed(order):
        if table in doomed and table is not User.__table__:
            key = list(table.primary_key.columns)[0]
            db.execute(table.delete().where(key.in_(doomed[table])))
    db.delete(user)
    db.commit()
    response.delete_cookie(ACCESS_COOKIE)
