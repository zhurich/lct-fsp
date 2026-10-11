from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db, utcnow
from app.core.deps import current_employer
from app.core.schemas import PathId
from app.modules.assessment import adaptive
from app.modules.assessment.models import Assessment, AttemptStatus, CandidateCategory
from app.modules.auth.models import User
from app.modules.candidates.models import CandidateProfile
from app.modules.candidates.privacy import mask_contacts, visible_experience
from app.modules.challenges.models import ChallengeAnswer
from app.modules.invitations.models import Invitation
from app.modules.matching.models import Need
from app.modules.matching.parser import parse_need
from app.modules.matching.ranking import (
    MIN_PEERS,
    CandidateData,
    Match,
    Requirements,
    UnverifiedData,
    describe_unverified,
    rank,
)
from app.modules.matching.schemas import (
    CandidateCard,
    CategoryCount,
    MatchesOut,
    NeedIn,
    NeedOut,
    ParsedNeedOut,
    ParseIn,
)
from app.modules.reference.data import GRADES
from app.modules.reference.skills import skill_key

router = APIRouter(prefix="/employer", tags=["Подбор кандидатов"])


def _card(profile: CandidateProfile, match: Match, invited: dict, **category) -> CandidateCard:
    """Обезличенная карточка: скрытые кандидатом сведения в неё не попадают."""
    hidden = set(profile.hidden_fields)
    return CandidateCard(
        candidate_id=profile.user_id,
        stack=profile.stack,
        matched_stack=match.matched_stack,
        experience_years=visible_experience(profile),
        city="" if "city" in hidden else profile.city,
        work_formats=[] if "work_formats" in hidden else profile.work_formats,
        # Контакты, вписанные в «О себе», работодатель до согласия не видит.
        about="" if "about" in hidden else mask_contacts(profile.about),
        fsp_linked=profile.fsp_id is not None and "fsp" not in hidden,
        fsp_achievements=[] if "fsp" in hidden else profile.fsp_achievements,
        fsp_rank=None if "fsp" in hidden else profile.fsp_rank,
        score=match.score,
        breakdown=match.breakdown,
        reasons=match.reasons,
        invitation_status=invited.get(profile.user_id),
        **category,
    )


def _find(db: Session, employer_id: int, requirements: Requirements) -> list[CandidateCard]:
    """Кандидаты под запрос: сначала с подтверждённой категорией по убыванию оценки, затем заявившие грейд,
    но не подтвердившие его тестом.

    В выдачу попадают только кандидаты с согласием на публикацию.
    """
    query = (
        select(CandidateProfile, CandidateCategory)
        .join(CandidateCategory, CandidateCategory.user_id == CandidateProfile.user_id)
        .where(CandidateProfile.is_published)
    )
    if requirements.specialization:
        query = query.where(CandidateCategory.specialization == requirements.specialization)
    # Последнее приглашение этого работодателя каждому кандидату.
    invited = {
        invitation.candidate_id: invitation.status
        for invitation in db.scalars(
            select(Invitation).where(Invitation.employer_id == employer_id).order_by(Invitation.id)
        )
    }
    # Ответы на регулярные задания: по ним считается актуальность профиля.
    answers: dict[int, list[ChallengeAnswer]] = {}
    for answer in db.scalars(select(ChallengeAnswer)):
        answers.setdefault(answer.candidate_id, []).append(answer)
    now = utcnow()
    cards = []
    rows = db.execute(query).all()
    # Баллы теста по категориям: в объяснении показывается место кандидата среди таких же.
    peers: dict[tuple[str, str], list[float]] = {}
    for _, category in rows:
        peers.setdefault((category.specialization, category.grade), []).append(category.score)
    # Стек хранится в JSON и сопоставляется в приложении: так запрос переносим между СУБД.
    for profile, category in rows:
        # Скрытые кандидатом сведения не показываются и не участвуют в оценке: работодатель не должен
        # видеть в объяснении то, что кандидат не раскрыл.
        hidden = set(profile.hidden_fields)
        own_answers = answers.get(profile.user_id, [])
        scores = peers[category.specialization, category.grade]
        match = rank(
            requirements,
            CandidateData(
                specialization=category.specialization,
                grade=category.grade,
                test_score=category.score,
                assigned_at=category.assigned_at,
                stack=profile.stack,
                work_formats=[] if "work_formats" in hidden else profile.work_formats,
                fsp_achievements=[] if "fsp" in hidden else profile.fsp_achievements,
                last_answer_at=max((answer.created_at for answer in own_answers), default=None),
                answer_ratings=[answer.rating for answer in own_answers if answer.rating],
                answers_total=len(own_answers),
                test_percentile=sum(score < category.score for score in scores) / (len(scores) - 1)
                if len(scores) >= MIN_PEERS
                else None,
            ),
            now,
        )
        if match is None:
            continue
        cards.append(
            _card(
                profile,
                match,
                invited,
                verified=True,
                specialization=category.specialization,
                grade=category.grade,
                test_score=category.score,
                category_assigned_at=category.assigned_at,
            )
        )
    cards.sort(key=lambda card: (card.score, card.test_score), reverse=True)
    return cards + _find_unverified(db, requirements, invited)


def _find_unverified(db: Session, requirements: Requirements, invited: dict) -> list[CandidateCard]:
    """Кандидаты без категории, сдававшие тест: показываются со статусом «грейд не подтверждён».

    Скрывать их нельзя — человек выпал бы из оборота до пересдачи; ставить в один ряд с подтверждёнными
    тоже: заявленный грейд ничем не подкреплён. Поэтому они идут отдельным списком после подтверждённых.
    """
    # Последний непройденный тест каждого кандидата: из него берётся заявленный грейд.
    attempts = {
        row.user_id: row
        for row in db.execute(
            select(
                Assessment.user_id,
                Assessment.specialization,
                Assessment.grade,
                Assessment.score,
                Assessment.finished_at,
            )
            .where(Assessment.status == AttemptStatus.failed)
            .order_by(Assessment.id)
        )
    }
    profiles = db.scalars(
        select(CandidateProfile)
        .outerjoin(CandidateCategory, CandidateCategory.user_id == CandidateProfile.user_id)
        .where(CandidateProfile.is_published, CandidateCategory.user_id.is_(None))
    )
    found = []
    for profile in profiles:
        attempt = attempts.get(profile.user_id)
        if attempt is None:
            continue
        hidden = set(profile.hidden_fields)
        described = describe_unverified(
            requirements,
            UnverifiedData(
                specialization=attempt.specialization,
                claimed_grade=attempt.grade,
                attempt_score=attempt.score or 0.0,
                pass_score=adaptive.to_score(adaptive.GRADE_CUTS[attempt.grade]),
                attempted_at=attempt.finished_at,
                stack=profile.stack,
                work_formats=[] if "work_formats" in hidden else profile.work_formats,
                fsp_achievements=[] if "fsp" in hidden else profile.fsp_achievements,
            ),
        )
        if described is None:
            continue
        match, order = described
        card = _card(
            profile,
            match,
            invited,
            verified=False,
            specialization=attempt.specialization,
            grade=attempt.grade,
            test_score=attempt.score or 0.0,
            category_assigned_at=attempt.finished_at,
        )
        found.append((order, card))
    found.sort(key=lambda item: item[0], reverse=True)
    return [card for _, card in found]


def _refine(
    cards: list[CandidateCard], grade: str | None, stack: list[str], fsp_only: bool, work_format: str | None
) -> list[CandidateCard]:
    """Уточняющие фильтры поверх готовой выдачи: оценки и порядок кандидатов не меняются."""
    required = {skill_key(item) for item in stack if item.strip()}
    return [
        card
        for card in cards
        if (not grade or card.grade == grade)
        and required <= {skill_key(item) for item in card.stack}
        and (not fsp_only or card.fsp_achievements)
        and (not work_format or work_format in card.work_formats)
    ]


_GRADE = Query(default=None, description="Только этот грейд")
_STACK = Query(default=[], description="Обязательные технологии (все); параметр можно повторять")
_FSP = Query(default=False, description="Только с подтверждёнными достижениями ФСП")
_FORMAT = Query(default=None, description="Только готовые к этому формату работы")


@router.get(
    "/candidates",
    response_model=list[CandidateCard],
    summary="Банк кандидатов: вся база с фильтрами, сортировка по силе подтверждённого профиля; "
    "в конце — кандидаты с неподтверждённым грейдом",
)
def search(
    specialization: str | None = None,
    grade: str | None = _GRADE,
    stack: list[str] = _STACK,
    fsp_only: bool = _FSP,
    work_format: str | None = _FORMAT,
    user: User = Depends(current_employer),
    db: Session = Depends(get_db),
):
    cards = _find(db, user.id, Requirements(specialization=specialization, stack=stack))
    return _refine(cards, grade, stack, fsp_only, work_format)


@router.post(
    "/needs/parse",
    response_model=ParsedNeedOut,
    summary="Разобрать текст потребности: специализация, грейд, стек, формат, зарплата",
)
def parse(data: ParseIn, user: User = Depends(current_employer)):
    return parse_need(data.text)


@router.get("/needs", response_model=list[NeedOut], summary="Сохранённые потребности")
def list_needs(user: User = Depends(current_employer), db: Session = Depends(get_db)):
    return db.scalars(select(Need).where(Need.employer_id == user.id).order_by(Need.id.desc())).all()


@router.post("/needs", response_model=NeedOut, status_code=status.HTTP_201_CREATED, summary="Сохранить потребность")
def create_need(data: NeedIn, user: User = Depends(current_employer), db: Session = Depends(get_db)):
    need = Need(employer_id=user.id, **data.model_dump())
    db.add(need)
    db.commit()
    return need


def _own_need(need_id: PathId, user: User = Depends(current_employer), db: Session = Depends(get_db)) -> Need:
    need = db.get(Need, need_id)
    # Чужая потребность неотличима от несуществующей.
    if need is None or need.employer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Потребность не найдена")
    return need


_NOT_FOUND = {404: {"description": "Потребность не найдена"}}


@router.put("/needs/{need_id}", response_model=NeedOut, summary="Изменить потребность", responses=_NOT_FOUND)
def update_need(data: NeedIn, need: Need = Depends(_own_need), db: Session = Depends(get_db)):
    for field, value in data.model_dump().items():
        setattr(need, field, value)
    db.commit()
    return need


@router.delete(
    "/needs/{need_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить потребность",
    responses=_NOT_FOUND,
)
def delete_need(need: Need = Depends(_own_need), db: Session = Depends(get_db)):
    db.delete(need)
    db.commit()


@router.get(
    "/needs/{need_id}/matches",
    response_model=MatchesOut,
    summary="Подборка под потребность: рекомендованные категории и ранжированные кандидаты с объяснением",
    responses=_NOT_FOUND,
)
def matches(
    grade: str | None = _GRADE,
    stack: list[str] = _STACK,
    fsp_only: bool = _FSP,
    work_format: str | None = _FORMAT,
    need: Need = Depends(_own_need),
    db: Session = Depends(get_db),
):
    cards = _find(
        db,
        need.employer_id,
        Requirements(
            specialization=need.specialization,
            grade=need.grade,
            stack=need.stack,
            work_formats=need.work_formats,
        ),
    )
    refined = _refine(cards, grade, stack, fsp_only, work_format)
    verified = [card for card in cards if card.verified]
    counts = {code: sum(card.grade == code for card in verified) for code in GRADES}
    grades = list(GRADES)
    position = grades.index(need.grade)
    categories = [
        CategoryCount(specialization=need.specialization, grade=code, exact=code == need.grade, count=counts[code])
        for code in grades[max(0, position - 1) : position + 2]
    ]
    return MatchesOut(
        need=need,
        categories=categories,
        total=len(verified),
        candidates=[card for card in refined if card.verified],
        unverified=[card for card in refined if not card.verified],
    )
