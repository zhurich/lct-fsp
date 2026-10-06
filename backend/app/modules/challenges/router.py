"""Регулярные короткие задания от работодателей.

Кандидату предлагаются открытые задания по его специализации, на которые он ещё не отвечал. Ответ
обновляет актуальность профиля (в ранжировании учитывается дата последней активности), а оценённые
работодателями ответы показываются в подборке как свежий сигнал о кандидате. Работодатель видит ответы
обезличенно — с категорией кандидата, но без имени и контактов — и может пригласить автора.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import current_candidate, current_employer
from app.core.schemas import InputModel, PathId
from app.modules.assessment.models import CandidateCategory
from app.modules.auth.models import User
from app.modules.candidates.models import CandidateProfile
from app.modules.candidates.privacy import mask_contacts
from app.modules.challenges.models import Challenge, ChallengeAnswer
from app.modules.employers.models import Company
from app.modules.reference.data import SPECIALIZATIONS

router = APIRouter(tags=["Регулярные задания"])

MIN_ANSWER_LENGTH = 50


class ChallengeIn(InputModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=20, max_length=5000, description="Условие: задача или ситуация из практики команды")
    specialization: str
    is_open: bool = True

    @field_validator("specialization")
    @classmethod
    def known_specialization(cls, value: str) -> str:
        if value not in SPECIALIZATIONS:
            raise ValueError("Неизвестная специализация")
        return value


class EmployerChallengeOut(ChallengeIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    answers_total: int = 0
    answers_unrated: int = 0


class AnswerOut(BaseModel):
    """Ответ глазами работодателя: обезличен, как карточка в подборке."""

    id: int
    candidate_id: int
    grade: str | None = Field(description="Подтверждённый грейд автора; null — категории нет")
    test_score: float | None
    in_bank: bool = Field(description="Можно ли пригласить автора: профиль опубликован и категория подтверждена")
    text: str
    rating: int | None
    created_at: datetime


class RatingIn(BaseModel):
    rating: int = Field(ge=1, le=5)


class CandidateChallengeOut(BaseModel):
    id: int
    title: str
    text: str
    specialization: str
    company_name: str
    created_at: datetime


class AnswerIn(InputModel):
    text: str = Field(min_length=MIN_ANSWER_LENGTH, max_length=5000, description="Решение или подход к решению")


class MyAnswerOut(BaseModel):
    id: int
    challenge_title: str
    company_name: str
    text: str
    rating: int | None
    created_at: datetime


def _own_challenge(
    challenge_id: PathId, user: User = Depends(current_employer), db: Session = Depends(get_db)
) -> Challenge:
    challenge = db.get(Challenge, challenge_id)
    if challenge is None or challenge.employer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Задание не найдено")
    return challenge


def _for_employer(db: Session, challenge: Challenge) -> EmployerChallengeOut:
    ratings = db.scalars(select(ChallengeAnswer.rating).where(ChallengeAnswer.challenge_id == challenge.id)).all()
    result = EmployerChallengeOut.model_validate(challenge)
    result.answers_total = len(ratings)
    result.answers_unrated = sum(rating is None for rating in ratings)
    return result


@router.get("/employer/challenges", response_model=list[EmployerChallengeOut], summary="Задания компании")
def employer_challenges(user: User = Depends(current_employer), db: Session = Depends(get_db)):
    challenges = db.scalars(select(Challenge).where(Challenge.employer_id == user.id).order_by(Challenge.id.desc()))
    return [_for_employer(db, challenge) for challenge in challenges]


@router.post(
    "/employer/challenges",
    response_model=EmployerChallengeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Опубликовать задание для кандидатов специализации",
    responses={409: {"description": "Не заполнено название компании"}},
)
def create_challenge(data: ChallengeIn, user: User = Depends(current_employer), db: Session = Depends(get_db)):
    company = db.get(Company, user.id)
    if company is None or not company.name.strip():
        raise HTTPException(status.HTTP_409_CONFLICT, "Укажите название компании в разделе «Компания»")
    challenge = Challenge(employer_id=user.id, **data.model_dump())
    db.add(challenge)
    db.commit()
    return _for_employer(db, challenge)


@router.put(
    "/employer/challenges/{challenge_id}",
    response_model=EmployerChallengeOut,
    summary="Изменить или закрыть задание",
    responses={404: {"description": "Задание не найдено"}},
)
def update_challenge(data: ChallengeIn, challenge: Challenge = Depends(_own_challenge), db: Session = Depends(get_db)):
    for field, value in data.model_dump().items():
        setattr(challenge, field, value)
    db.commit()
    return _for_employer(db, challenge)


@router.get(
    "/employer/challenges/{challenge_id}/answers",
    response_model=list[AnswerOut],
    summary="Ответы кандидатов на задание (обезличенные)",
    responses={404: {"description": "Задание не найдено"}},
)
def challenge_answers(challenge: Challenge = Depends(_own_challenge), db: Session = Depends(get_db)):
    answers = db.scalars(
        select(ChallengeAnswer).where(ChallengeAnswer.challenge_id == challenge.id).order_by(ChallengeAnswer.id.desc())
    )
    result = []
    for answer in answers:
        category = db.get(CandidateCategory, answer.candidate_id)
        profile = db.get(CandidateProfile, answer.candidate_id)
        result.append(
            AnswerOut(
                id=answer.id,
                candidate_id=answer.candidate_id,
                grade=category.grade if category else None,
                test_score=category.score if category else None,
                in_bank=bool(category and profile and profile.is_published),
                # Ответ показывается обезличенно, поэтому контакты из его текста вырезаются.
                text=mask_contacts(answer.text),
                rating=answer.rating,
                created_at=answer.created_at,
            )
        )
    return result


@router.put(
    "/employer/answers/{answer_id}/rating",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Оценить ответ от 1 до 5",
    responses={404: {"description": "Ответ не найден"}},
)
def rate_answer(
    answer_id: PathId, data: RatingIn, user: User = Depends(current_employer), db: Session = Depends(get_db)
):
    answer = db.get(ChallengeAnswer, answer_id)
    challenge = db.get(Challenge, answer.challenge_id) if answer else None
    if challenge is None or challenge.employer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ответ не найден")
    answer.rating = data.rating
    db.commit()


def _specialization(db: Session, user_id: int) -> str | None:
    """Специализация кандидата: из подтверждённой категории, а до теста — из профиля."""
    category = db.get(CandidateCategory, user_id)
    profile = db.get(CandidateProfile, user_id)
    return category.specialization if category else profile.specialization if profile else None


@router.get(
    "/candidate/challenges",
    response_model=list[CandidateChallengeOut],
    summary="Задания по специализации кандидата, на которые он ещё не отвечал",
)
def candidate_challenges(user: User = Depends(current_candidate), db: Session = Depends(get_db)):
    specialization = _specialization(db, user.id)
    if specialization is None:
        return []
    answered = select(ChallengeAnswer.challenge_id).where(ChallengeAnswer.candidate_id == user.id)
    rows = db.execute(
        select(Challenge, Company)
        .join(Company, Company.user_id == Challenge.employer_id)
        .where(Challenge.is_open, Challenge.specialization == specialization, Challenge.id.not_in(answered))
        .order_by(Challenge.id.desc())
    )
    return [
        CandidateChallengeOut(
            id=challenge.id,
            title=challenge.title,
            text=challenge.text,
            specialization=challenge.specialization,
            company_name=company.name,
            created_at=challenge.created_at,
        )
        for challenge, company in rows
    ]


@router.post(
    "/candidate/challenges/{challenge_id}/answer",
    status_code=status.HTTP_201_CREATED,
    response_model=MyAnswerOut,
    summary="Ответить на задание: решение или подход к нему",
    responses={404: {"description": "Задание не найдено или закрыто"}, 409: {"description": "Ответ уже отправлен"}},
)
def answer_challenge(
    challenge_id: PathId, data: AnswerIn, user: User = Depends(current_candidate), db: Session = Depends(get_db)
):
    challenge = db.get(Challenge, challenge_id)
    # Задание другой специализации кандидату не предлагалось — для него оно неотличимо от несуществующего.
    if challenge is None or not challenge.is_open or challenge.specialization != _specialization(db, user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Задание не найдено или уже закрыто")
    exists = db.scalar(
        select(func.count()).select_from(ChallengeAnswer).where(
            ChallengeAnswer.challenge_id == challenge_id, ChallengeAnswer.candidate_id == user.id
        )
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Вы уже ответили на это задание")
    answer = ChallengeAnswer(challenge_id=challenge_id, candidate_id=user.id, text=data.text)
    db.add(answer)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Вы уже ответили на это задание") from None
    return _mine(db, answer, challenge)


def _mine(db: Session, answer: ChallengeAnswer, challenge: Challenge) -> MyAnswerOut:
    return MyAnswerOut(
        id=answer.id,
        challenge_title=challenge.title,
        company_name=db.get(Company, challenge.employer_id).name,
        text=answer.text,
        rating=answer.rating,
        created_at=answer.created_at,
    )


@router.get("/candidate/answers", response_model=list[MyAnswerOut], summary="Свои ответы и оценки работодателей")
def my_answers(user: User = Depends(current_candidate), db: Session = Depends(get_db)):
    rows = db.execute(
        select(ChallengeAnswer, Challenge)
        .join(Challenge, Challenge.id == ChallengeAnswer.challenge_id)
        .where(ChallengeAnswer.candidate_id == user.id)
        .order_by(ChallengeAnswer.id.desc())
    )
    return [_mine(db, answer, challenge) for answer, challenge in rows]
