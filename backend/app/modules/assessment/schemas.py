from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.schemas import InputModel, Tag
from app.modules.assessment.models import AttemptStatus
from app.modules.reference.data import GRADES, SPECIALIZATIONS


class StartIn(InputModel):
    """Опрос перед тестом: специализация, стек и предполагаемый грейд."""

    specialization: str
    grade: str
    stack: list[Tag] = Field(default_factory=list, max_length=50)

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


class AnswerIn(BaseModel):
    position: int = Field(ge=1, description="Номер задания, на которое даётся ответ (с 1)")
    answer: int | None = Field(
        ge=0, description="Номер выбранного варианта (с 0, меньше числа вариантов); null — пропустить задание"
    )


class QuestionOut(BaseModel):
    text: str
    code: str | None
    options: list[str]


class AttemptOut(BaseModel):
    id: int
    specialization: str
    grade: str
    status: AttemptStatus
    score: float | None = Field(description="Балл теста 0…1 по шкале IRT")
    estimated_grade: str | None = Field(description="Грейд, которому соответствует результат завершённого теста")
    correct_count: int | None
    total: int = Field(description="Сколько заданий выдано; у идущего теста — наибольшая возможная длина")
    started_at: datetime
    expires_at: datetime
    finished_at: datetime | None


class ActiveAttemptOut(AttemptOut):
    position: int = Field(description="Номер текущего задания (с 1)")
    min_total: int = Field(description="Наименьшая длина теста: раньше он не заканчивается")
    question: QuestionOut


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    specialization: str
    grade: str
    score: float
    upgrade_offer: bool
    assigned_at: datetime


class GradeAvailability(BaseModel):
    grade: str
    available_from: datetime | None = Field(description="null — тест на этот грейд можно начать сейчас")


class AssessmentState(BaseModel):
    category: CategoryOut | None
    active: ActiveAttemptOut | None
    history: list[AttemptOut]
    grades: list[GradeAvailability] = Field(
        description="Доступность грейдов по своей специализации: подтверждённой либо последнего теста"
    )
    grades_by_specialization: dict[str, list[GradeAvailability]] = Field(
        description="Доступность грейдов по каждой специализации: срок после провала действует только в ней"
    )
    demo_mode: bool = Field(description="true — стенд проверки: попытки можно сбросить и пройти тест заново")
