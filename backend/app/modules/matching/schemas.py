from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.schemas import InputModel, Money, Tag
from app.modules.invitations.models import InvitationStatus
from app.modules.reference.data import GRADES, SPECIALIZATIONS, WORK_FORMATS


class ScorePart(BaseModel):
    key: str
    label: str
    value: float = Field(description="Оценка составляющей, 0…1")


class FspAchievement(BaseModel):
    event: str
    discipline: str
    level: str
    place: int | None = Field(description="null — участие без призового места")
    date: str
    team: bool = Field(default=False, description="Командный результат")


class CandidateCard(BaseModel):
    """Обезличенная карточка кандидата: без имени и контактов."""

    candidate_id: int
    verified: bool = Field(
        description="true — грейд подтверждён тестом; false — заявлен, но последний тест на него не пройден"
    )
    specialization: str
    grade: str = Field(description="Подтверждённый грейд; для неподтверждённых — заявленный")
    test_score: float = Field(description="Балл теста 0…1: подтвердившего категорию либо последнего непройденного")
    category_assigned_at: datetime = Field(description="Дата этого теста")
    stack: list[str]
    matched_stack: list[str] = Field(description="Технологии из запроса, которые есть у кандидата")
    experience_years: float | None = Field(description="null — кандидат скрыл стаж")
    city: str
    work_formats: list[str]
    about: str
    fsp_linked: bool = Field(description="Привязан ли ФСП ID; false — нейтральное состояние, не недостаток")
    fsp_achievements: list[FspAchievement]
    fsp_rank: str | None = Field(description="Спортивный разряд из реестра ФСП")
    score: float | None = Field(
        description="Итоговая оценка 0…100, по которой отсортирована выдача; null — грейд не подтверждён"
    )
    breakdown: list[ScorePart] = Field(description="Из чего сложилась оценка")
    reasons: list[str] = Field(description="Почему кандидат в подборке")
    invitation_status: InvitationStatus | None = Field(description="Статус приглашения от текущего работодателя")


class ParseIn(InputModel):
    text: str = Field(min_length=1, max_length=5000)


class ParsedNeedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    specialization: str | None
    grade: str | None
    stack: list[str]
    work_formats: list[str]
    salary_from: int | None
    salary_to: int | None
    notes: list[str] = Field(description="Что и по каким признакам распознано")


class NeedIn(InputModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(default="", max_length=5000, description="Исходное описание потребности")
    specialization: str
    grade: str
    stack: list[Tag] = Field(default_factory=list, max_length=30)
    work_formats: list[str] = Field(default_factory=list, max_length=10)
    salary_from: Money | None = None
    salary_to: Money | None = None

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
        if self.salary_from and self.salary_to and self.salary_to < self.salary_from:
            raise ValueError("Верхняя граница зарплаты меньше нижней")
        return self


class NeedOut(NeedIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class CategoryCount(BaseModel):
    specialization: str
    grade: str
    exact: bool = Field(description="true — категория из запроса, false — смежный грейд")
    count: int = Field(description="Сколько кандидатов категории доступно в банке")


class MatchesOut(BaseModel):
    need: NeedOut
    categories: list[CategoryCount] = Field(description="Рекомендованные категории под потребность")
    total: int = Field(description="Размер подборки до уточняющих фильтров (кандидаты с подтверждённым грейдом)")
    candidates: list[CandidateCard]
    unverified: list[CandidateCard] = Field(
        description="Кандидаты той же специализации, заявившие запрошенный или смежный грейд, но не "
        "подтвердившие его тестом: показываются после подборки, без оценки"
    )
