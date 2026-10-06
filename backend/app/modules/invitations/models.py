import enum
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime, utcnow


class InvitationStatus(str, enum.Enum):
    sent = "sent"
    viewed = "viewed"
    accepted = "accepted"
    declined = "declined"


# Статусы, в которых кандидат ещё не дал ответа.
PENDING = (InvitationStatus.sent, InvitationStatus.viewed)


class Invitation(Base):
    """Приглашение работодателя конкретному кандидату; к опубликованной вакансии не привязано."""

    __tablename__ = "invitations"
    # У работодателя не больше одного действующего приглашения кандидату; после отказа можно пригласить снова.
    __table_args__ = (
        Index(
            "uq_invitations_active",
            "employer_id",
            "candidate_id",
            unique=True,
            sqlite_where=text("status != 'declined'"),
            postgresql_where=text("status != 'declined'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    salary_from: Mapped[int]
    salary_to: Mapped[int]
    contact: Mapped[str] = mapped_column(String(300))
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(InvitationStatus, native_enum=False, length=20), default=InvitationStatus.sent
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
