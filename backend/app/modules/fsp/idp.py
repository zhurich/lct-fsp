"""Вход через ФСП ID.

ФСП ID — единый аккаунт участника на ресурсах Федерации (сервер Keycloak, протокол OpenID Connect).
Доступа к нему на хакатоне нет, поэтому здесь зафиксирован контракт провайдера (FspIdProvider) и его мок.
Платформа проходит тот же путь, что и с настоящим сервером: перенаправление на страницу входа провайдера,
возврат с одноразовым кодом, обмен кода на сведения об участнике. Для реальной интеграции достаточно
реализовать authorize_url() и exchange() поверх Keycloak; остальной код не меняется.
"""

import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

CLIENT_ID = "fsp-career"
# Куда провайдер возвращает пользователя с кодом — страница интерфейса платформы.
REDIRECT_PATH = "/fsp-callback"


@dataclass(frozen=True)
class FspIdentity:
    # Идентификатор участника (claim sub): по нему запрашиваются достижения в реестре.
    sub: str
    email: str


class FspIdProvider(Protocol):
    def authorize_url(self, state: str) -> str:
        """Адрес страницы входа провайдера; state возвращается платформе без изменений."""

    def exchange(self, code: str) -> FspIdentity | None:
        """Обмен одноразового кода на сведения об участнике; None — код неизвестен, использован или устарел."""


class MockFspId:
    """Демонстрационный ФСП ID: страница входа — часть интерфейса платформы, участники — выдуманные.

    Войти можно с любой почтой и общим паролем DEMO_PASSWORD: идентификатор участника выводится из почты,
    поэтому одна и та же почта всегда даёт одного и того же участника с одним набором достижений.
    """

    DEMO_PASSWORD = "fsp-demo"
    CODE_TTL_SECONDS = 120
    # Участники с заранее известной историей — для показа разных состояний профиля.
    DEMO_ACCOUNTS: dict[str, tuple[str, str]] = {
        "champion@fsp.example": ("FSP-1000007", "Шесть соревнований, пять призовых мест"),
        "participant@fsp.example": ("FSP-1000008", "Два участия без призовых мест"),
        "newcomer@fsp.example": ("FSP-1000002", "Аккаунт без истории соревнований"),
    }

    def __init__(self) -> None:
        # Выданные коды живут в памяти процесса, как и счётчики частоты.
        self._codes: dict[str, tuple[FspIdentity, float]] = {}

    def authorize_url(self, state: str) -> str:
        query = urlencode(
            {
                "client_id": CLIENT_ID,
                "response_type": "code",
                "scope": "openid email achievements",
                "redirect_uri": REDIRECT_PATH,
                "state": state,
            }
        )
        return f"/fsp-id?{query}"

    def participant(self, email: str) -> str:
        """Идентификатор участника для почты."""
        if email in self.DEMO_ACCOUNTS:
            return self.DEMO_ACCOUNTS[email][0]
        # Семизначные номера не пересекаются с шестизначными номерами синтетических кандидатов демо-базы.
        number = int(hashlib.sha256(email.encode()).hexdigest()[:8], 16) % 9_000_000 + 1_000_000
        # Номера, кратные 7, в мок-реестре отсутствуют, а вошедший участник существовать обязан.
        return f"FSP-{number + (number % 7 == 0)}"

    def login(self, email: str, password: str) -> str | None:
        """Вход на странице провайдера: выдаёт одноразовый код либо None при неверном пароле."""
        if not secrets.compare_digest(password.encode(), self.DEMO_PASSWORD.encode()):
            return None
        now = time.monotonic()
        self._codes = {code: item for code, item in self._codes.items() if item[1] > now}
        code = secrets.token_urlsafe(24)
        self._codes[code] = (FspIdentity(self.participant(email), email), now + self.CODE_TTL_SECONDS)
        return code

    def exchange(self, code: str) -> FspIdentity | None:
        identity, expires = self._codes.pop(code, (None, 0.0))
        return identity if expires > time.monotonic() else None


provider = MockFspId()
