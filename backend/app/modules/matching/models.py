from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime, utcnow


class Need(Base):
    """Потребность работодателя: исходный текст и разобранная из него структура, по которой строится подборка.

    Подборка не хранится, а вычисляется по потребности при каждом открытии: в ней сразу видны новые
    кандидаты, а уточняющие фильтры накладываются поверх и саму потребность не меняют.
    """

    __tablename__ = "needs"

    id: Mapped[int] = mapped_column(primary_key=True)
    employer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text, default="")
    specialization: Mapped[str] = mapped_column(String(30))
    grade: Mapped[str] = mapped_column(String(30))
    stack: Mapped[list[str]] = mapped_column(JSON, default=list)
    work_formats: Mapped[list[str]] = mapped_column(JSON, default=list)
    salary_from: Mapped[int | None] = mapped_column(default=None)
    salary_to: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
