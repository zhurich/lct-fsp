from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime, utcnow


class CandidateProfile(Base):
    """Самоописанная часть профиля. Категория для работодателя строится не по ней, а по тестированию."""

    __tablename__ = "candidate_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    telegram: Mapped[str] = mapped_column(String(100), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    about: Mapped[str] = mapped_column(Text, default="")
    specialization: Mapped[str | None] = mapped_column(String(30), default=None)
    stack: Mapped[list[str]] = mapped_column(JSON, default=list)
    roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    soft_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    experience_years: Mapped[float] = mapped_column(default=0)
    work_formats: Mapped[list[str]] = mapped_column(JSON, default=list)
    salary_expectation: Mapped[int | None] = mapped_column(default=None)
    # Согласие на публикацию: пока False, профиль не попадает в выдачу работодателям.
    is_published: Mapped[bool] = mapped_column(default=False)
    # Необязательные сведения, которые кандидат скрыл от работодателей (см. HIDEABLE_FIELDS).
    hidden_fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Связь с участником ФСП и копия его достижений из реестра на момент последней синхронизации.
    # Пустые значения — нейтральное состояние: профиль без истории ФСП полноценно участвует в подборе.
    fsp_id: Mapped[str | None] = mapped_column(String(20), unique=True, default=None)
    fsp_achievements: Mapped[list[dict]] = mapped_column(JSON, default=list)
    fsp_rank: Mapped[str | None] = mapped_column(String(60), default=None)
    fsp_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
