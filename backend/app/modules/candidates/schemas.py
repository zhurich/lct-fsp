from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.schemas import InputModel, Money, Tag
from app.modules.reference.data import SPECIALIZATIONS, WORK_FORMATS

# Что кандидат может скрыть от работодателя. Категория, балл теста и стек видны всегда — на них строится
# подбор; имя и контакты скрыты всегда, пока кандидат не примет приглашение.
HIDEABLE_FIELDS: dict[str, str] = {
    "city": "Город",
    "experience": "Стаж",
    "work_formats": "Формат работы",
    "about": "Раздел «О себе»",
    "fsp": "Достижения ФСП",
}


class CandidateProfileIn(InputModel):
    full_name: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=50)
    telegram: str = Field(default="", max_length=100)
    city: str = Field(default="", max_length=100)
    about: str = Field(default="", max_length=5000)
    specialization: str | None = None
    stack: list[Tag] = Field(default_factory=list, max_length=50)
    roles: list[Tag] = Field(default_factory=list, max_length=20)
    soft_skills: list[Tag] = Field(default_factory=list, max_length=20)
    # NaN и бесконечность проходят сравнения ge/le, поэтому запрещаются отдельно.
    experience_years: float = Field(default=0, ge=0, le=60, allow_inf_nan=False)
    work_formats: list[str] = Field(default_factory=list, max_length=10)
    salary_expectation: Money | None = None
    is_published: bool = False
    hidden_fields: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("specialization")
    @classmethod
    def known_specialization(cls, value: str | None) -> str | None:
        if value is not None and value not in SPECIALIZATIONS:
            raise ValueError("Неизвестная специализация")
        return value

    @field_validator("hidden_fields")
    @classmethod
    def known_hidden_fields(cls, value: list[str]) -> list[str]:
        if any(item not in HIDEABLE_FIELDS for item in value):
            raise ValueError("Неизвестное поле в настройках приватности")
        return value

    @field_validator("work_formats")
    @classmethod
    def known_work_formats(cls, value: list[str]) -> list[str]:
        if any(item not in WORK_FORMATS for item in value):
            raise ValueError("Неизвестный формат работы")
        return value


class CandidateProfileOut(CandidateProfileIn):
    model_config = ConfigDict(from_attributes=True)

    fsp_id: str | None
    fsp_achievements: list[dict]
    fsp_rank: str | None = Field(description="Спортивный разряд из реестра ФСП")
    fsp_synced_at: datetime | None


class ParsedResumeOut(BaseModel):
    """Черновик профиля, распознанный из резюме; сохраняется только после проверки кандидатом."""

    model_config = ConfigDict(from_attributes=True)

    full_name: str
    phone: str
    telegram: str
    city: str
    about: str
    specialization: str | None
    claimed_grade: str | None = Field(description="Грейд со слов кандидата; категорию определяет только тест")
    stack: list[str]
    roles: list[str]
    soft_skills: list[str]
    experience_years: float | None
    work_formats: list[str]
    notes: list[str] = Field(description="Что распознано и что нужно заполнить вручную")
