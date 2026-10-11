import enum
from datetime import datetime

from sqlalchemy import JSON, Enum, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime, utcnow


class AttemptStatus(str, enum.Enum):
    in_progress = "in_progress"
    passed = "passed"
    failed = "failed"


class Assessment(Base):
    """Попытка тестирования: ответы опроса (специализация, грейд) и выданный кандидату вариант теста."""

    __tablename__ = "assessments"
    # Один незавершённый тест на кандидата гарантирует база: проверки в приложении при одновременных
    # запросах недостаточно.
    __table_args__ = (
        Index(
            "uq_assessments_in_progress",
            "user_id",
            unique=True,
            sqlite_where=text("status = 'in_progress'"),
            postgresql_where=text("status = 'in_progress'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    specialization: Mapped[str] = mapped_column(String(30))
    grade: Mapped[str] = mapped_column(String(30))
    status: Mapped[AttemptStatus] = mapped_column(
        Enum(AttemptStatus, native_enum=False, length=20), default=AttemptStatus.in_progress
    )
    # Выданные задания в порядке показа: текст, варианты, верный ответ, параметры IRT и ответ кандидата
    # (ключ answer появляется после ответа). Клиенту отдаётся только текущее задание без поля correct.
    questions: Mapped[list[dict]] = mapped_column(JSON, default=list)
    # Текущая оценка уровня по шкале IRT и её стандартная ошибка.
    theta: Mapped[float]
    se: Mapped[float | None] = mapped_column(default=None)
    correct_count: Mapped[int | None] = mapped_column(default=None)
    score: Mapped[float | None] = mapped_column(default=None)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    # Номер версии строки: из двух одновременных ответов на одно задание сохраняется только первый,
    # второй получает отказ (оптимистическая блокировка).
    version: Mapped[int] = mapped_column(default=1)

    __mapper_args__ = {"version_id_col": version}


class ItemExposure(Base):
    """Счётчик показов задания банка: по нему выравнивается частота выдачи."""

    __tablename__ = "item_exposures"

    item_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    shown: Mapped[int] = mapped_column(default=0)


class ItemFlag(Base):
    """Задание, снятое с выдачи мониторингом дрейфа: его решали заметно чаще, чем предсказывает модель.

    Строка не удаляется автоматически: задание возвращают в банк вручную, после того как его переписали.
    """

    __tablename__ = "item_flags"

    item_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    shown: Mapped[int]
    observed: Mapped[float]
    expected: Mapped[float]
    flagged_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class CandidateCategory(Base):
    """Подтверждённая тестом категория кандидата (специализация × грейд) — её видит работодатель."""

    __tablename__ = "candidate_categories"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    specialization: Mapped[str] = mapped_column(String(30), index=True)
    grade: Mapped[str] = mapped_column(String(30), index=True)
    score: Mapped[float]
    # Тест пройден с запасом на следующий грейд: его можно сдать сразу, не дожидаясь срока смены категории.
    upgrade_offer: Mapped[bool] = mapped_column(default=False)
    assigned_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
