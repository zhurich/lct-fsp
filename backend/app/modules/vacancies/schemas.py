from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.schemas import InputModel, Money, Tag
from app.modules.invitations.models import InvitationStatus
from app.modules.invitations.schemas import CandidateContacts
from app.modules.reference.data import GRADES, SPECIALIZATIONS, WORK_FORMATS


class VacancyIn(InputModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    specialization: str
    grade: str
    stack: list[Tag] = Field(default_factory=list, max_length=30)
    work_formats: list[str] = Field(default_factory=list, max_length=10)
    salary_from: Money = Field(description="Зарплата от, ₽ — обязательна")
    salary_to: Money = Field(description="Зарплата до, ₽ — обязательна")
    is_open: bool = True

    @field_validator("specialization")
    @classmethod
    def known_specialization(cls, value: str) -> str:
        if value not in SPECIALIZATIONS:
            raise ValueError("Неизвестная специализация")
        return value

    @field_validator("grade")
    @classmethod
    def known_grade(cls, value: str) -> str:
        if value not in GRADES:
            raise ValueError("Неизвестный грейд")
        return value

    @field_validator("work_formats")
    @classmethod
    def known_work_formats(cls, value: list[str]) -> list[str]:
        if any(item not in WORK_FORMATS for item in value):
            raise ValueError("Неизвестный формат работы")
        return value

    @model_validator(mode="after")
    def salary_range(self):
        if self.salary_to < self.salary_from:
            raise ValueError("Верхняя граница зарплаты меньше нижней")
        return self


class EmployerVacancyOut(VacancyIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    applications_total: int = 0
    applications_new: int = Field(default=0, description="Отклики, которые работодатель ещё не открывал")


class CandidateVacancyOut(VacancyIn):
    id: int
    created_at: datetime
    company_name: str
    company_industry: str
    company_description: str
    fits_category: bool = Field(description="Совпадает ли вакансия с подтверждённой категорией кандидата")
    application_status: InvitationStatus | None = Field(description="Статус отклика кандидата; null — не откликался")


class ApplyIn(InputModel):
    message: str = Field(default="", max_length=3000, description="Сопроводительное сообщение")


class ApplicationOut(BaseModel):
    """Отклик глазами работодателя: кандидат откликнулся сам, поэтому контакты открыты сразу."""

    id: int
    candidate_id: int
    specialization: str
    grade: str
    test_score: float
    stack: list[str]
    experience_years: float | None = Field(description="null — кандидат скрыл стаж")
    message: str
    status: InvitationStatus
    created_at: datetime
    contacts: CandidateContacts


class MyApplicationOut(BaseModel):
    id: int
    vacancy_id: int
    title: str
    company_name: str
    salary_from: int
    salary_to: int
    status: InvitationStatus
    created_at: datetime
    responded_at: datetime | None
