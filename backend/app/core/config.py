from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Значение из старых версий и примеров: с ним токен входа может подписать кто угодно.
_DEMO_SECRET = "dev-secret-change-me-in-production-please"
_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    # .env ищется в корне репозитория и в текущем каталоге: сервер стартует из корня, скрипты — из backend.
    model_config = SettingsConfigDict(env_file=(_ROOT / ".env", ".env"), extra="ignore")

    # SQLite — только для локальной разработки без Docker; в compose подставляется PostgreSQL.
    database_url: str = "sqlite:///./dev.db"
    # Секрет подписи токенов. Значения по умолчанию нет намеренно: без своего секрета приложение не стартует.
    secret_key: str = ""
    access_token_ttl_min: int = 720
    verify_token_ttl_hours: int = 48
    cookie_secure: bool = False

    frontend_url: str = "http://localhost:5183"

    # Если smtp_host не задан, письма пишутся в лог приложения.
    smtp_host: str | None = None
    smtp_port: int = 1025
    smtp_from: str = "no-reply@fsp-career.local"

    # Сменить подтверждённую категорию можно не чаще, чем раз в этот срок.
    grade_change_cooldown_days: int = 90
    # После проваленного теста этот грейд и грейды выше закрыты на этот срок; грейды ниже доступны сразу.
    retake_cooldown_days: int = 14
    test_duration_min: int = 30

    # Режим проверки стенда: почта при регистрации подтверждается сразу, а кандидат может сбросить свои
    # попытки теста и пройти его заново, не дожидаясь сроков. На рабочем стенде должен быть выключен.
    demo_mode: bool = False

    # Каталог с DejaVuSans.ttf и DejaVuSans-Bold.ttf для PDF-профиля; по умолчанию — системные шрифты.
    pdf_font_dir: str | None = None
    resume_max_mb: int = 5

    @field_validator("secret_key")
    @classmethod
    def secret_is_set(cls, value: str) -> str:
        if len(value) < 32 or value == _DEMO_SECRET:
            raise ValueError(
                "задайте SECRET_KEY (не короче 32 символов) в окружении или в .env: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return value


settings = Settings()
