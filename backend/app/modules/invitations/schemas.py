from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.core.schemas import BodyId, InputModel, Money
from app.modules.invitations.models import InvitationStatus


class InvitationIn(InputModel):
    candidate_id: BodyId
    title: str = Field(min_length=1, max_length=200, description="Должность или роль")
    message: str = Field(min_length=1, max_length=5000, description="Описание предложения")
    salary_from: Money = Field(description="Зарплата от, ₽")
    salary_to: Money = Field(description="Зарплата до, ₽")
    contact: str = Field(min_length=1, max_length=300, description="Способ связи с работодателем")

    @model_validator(mode="after")
    def salary_range(self):
        if self.salary_to < self.salary_from:
            raise ValueError("Верхняя граница зарплаты меньше нижней")
        return self


class InvitationBase(BaseModel):
    id: int
    title: str
    message: str
    salary_from: int
    salary_to: int
    contact: str
    status: InvitationStatus
    created_at: datetime
    responded_at: datetime | None


class CandidateContacts(BaseModel):
    full_name: str
    email: str
    phone: str
    telegram: str


class EmployerInvitationOut(InvitationBase):
    candidate_id: int
    specialization: str | None
    grade: str | None
    contacts: CandidateContacts | None = Field(description="Заполняется только после принятия приглашения")


class CandidateInvitationOut(InvitationBase):
    company_name: str
    company_industry: str
    company_description: str
    company_website: str
