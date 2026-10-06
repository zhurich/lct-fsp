from datetime import datetime

from sqlalchemy import JSON, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime, utcnow
from app.modules.invitations.models import InvitationStatus


class Vacancy(Base):
    """Вакансия, опубликованная работодателем напрямую. Зарплатная вилка обязательна."""

    __tablename__ = "vacancies"

    id: Mapped[int] = mapped_column(primary_key=True)
    employer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    specialization: Mapped[str] = mapped_column(String(30), index=True)
    grade: Mapped[str] = mapped_column(String(30))
    stack: Mapped[list[str]] = mapped_column(JSON, default=list)
    work_formats: Mapped[list[str]] = mapped_column(JSON, default=list)
    salary_from: Mapped[int]
    salary_to: Mapped[int]
    # Закрытая вакансия не показывается кандидатам, но отклики на неё сохраняются.
    is_open: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Application(Base):
    """Отклик кандидата на вакансию. Статусы те же, что у приглашений, но отвечает работодатель."""

    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("vacancy_id", "candidate_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    vacancy_id: Mapped[int] = mapped_column(ForeignKey("vacancies.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(InvitationStatus, native_enum=False, length=20), default=InvitationStatus.sent
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
