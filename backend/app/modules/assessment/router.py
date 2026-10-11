import random
from dataclasses import asdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.core.config import settings
from app.core.db import get_db, utcnow
from app.core.deps import current_candidate
from app.core.schemas import PathId
from app.modules.assessment import adaptive, drift
from app.modules.assessment.models import Assessment, AttemptStatus, CandidateCategory, ItemExposure, ItemFlag
from app.modules.assessment.schemas import (
    ActiveAttemptOut,
    AnswerIn,
    AssessmentState,
    AttemptOut,
    GradeAvailability,
    StartIn,
)
from app.modules.auth.models import User
from app.modules.candidates.router import get_or_create_profile
from app.modules.reference.data import GRADES, SPECIALIZATIONS

router = APIRouter(prefix="/candidate/assessment", tags=["Тестирование и категория"])


def _attempt_fields(attempt: Assessment) -> dict:
    # У просроченной попытки оценки уровня нет: она не доведена до конца.
    completed = attempt.finished_at is not None and adaptive.is_complete(attempt.questions)
    return {
        "id": attempt.id,
        "specialization": attempt.specialization,
        "grade": attempt.grade,
        "status": attempt.status,
        "score": attempt.score,
        "estimated_grade": adaptive.grade_of(attempt.theta) if completed else None,
        "correct_count": attempt.correct_count,
        # У завершённой попытки — сколько заданий было выдано, у идущей — предел длины теста.
        "total": len(attempt.questions) if attempt.finished_at else adaptive.MAX_LENGTH,
        "started_at": attempt.started_at,
        "expires_at": attempt.expires_at,
        "finished_at": attempt.finished_at,
    }


def _active_attempt(db: Session, user_id: int, now: datetime) -> Assessment | None:
    """Незавершённая попытка; просроченная закрывается как проваленная."""
    attempt = db.scalar(
        select(Assessment).where(Assessment.user_id == user_id, Assessment.status == AttemptStatus.in_progress)
    )
    if attempt and attempt.expires_at < now:
        attempt.status = AttemptStatus.failed
        attempt.correct_count = sum(
            "answer" in question and question["answer"] == question["correct"] for question in attempt.questions
        )
        attempt.score = 0
        attempt.finished_at = attempt.expires_at
        db.commit()
        return None
    return attempt


def _category_lock(category: CandidateCategory | None, now: datetime) -> datetime | None:
    """До какого момента подтверждённую категорию нельзя менять; None — можно уже сейчас."""
    if category is None:
        return None
    until = category.assigned_at + timedelta(days=settings.grade_change_cooldown_days)
    return until if until > now else None


def _serve_next(db: Session, attempt: Assessment) -> None:
    """Подбирает следующее задание у границы заявленного грейда и добавляет его в попытку."""
    rng = random.Random()
    used = {question["item_id"] for question in attempt.questions}
    flagged = set(db.scalars(select(ItemFlag.item_id)))
    candidates = adaptive.position_pool(attempt.specialization, len(attempt.questions), used, flagged)
    earlier = db.scalars(
        select(Assessment.questions).where(Assessment.user_id == attempt.user_id, Assessment.id != attempt.id)
    )
    seen = {question["item_id"] for questions in earlier for question in questions}
    exposure = dict(db.execute(select(ItemExposure.item_id, ItemExposure.shown)).all())
    item = adaptive.pick_item(candidates, adaptive.GRADE_CUTS[attempt.grade], exposure, seen, rng)

    _count_exposure(db, item.id)
    # JSON-колонка не отслеживает изменения на месте, поэтому список заменяется целиком.
    attempt.questions = [
        *attempt.questions,
        {"item_id": item.id, "a": item.a, "b": item.b, **asdict(item.generate(rng))},
    ]


def _count_exposure(db: Session, item_id: str) -> None:
    """Увеличивает счётчик показов одним запросом к базе: параллельные тесты не теряют показы."""
    increment = update(ItemExposure).where(ItemExposure.item_id == item_id).values(shown=ItemExposure.shown + 1)
    if db.execute(increment).rowcount:
        return
    try:
        with db.begin_nested():
            db.add(ItemExposure(item_id=item_id, shown=1))
    except IntegrityError:
        # Строку только что создал параллельный запрос.
        db.execute(increment)


def _grade_locks(db: Session, user_id: int, now: datetime) -> dict[str, dict[str, datetime]]:
    """Для каждой специализации — когда грейд станет доступен для новой попытки; грейда нет в словаре —
    доступен сейчас.

    Действуют два ограничения: подтверждённую категорию нельзя менять чаще, чем раз в
    grade_change_cooldown_days (это закрывает и все остальные специализации), а после провала этот грейд и
    грейды выше закрыты на retake_cooldown_days — только в той специализации, по которой был тест: провал
    по одному направлению ничего не говорит об уровне в другом. Грейды ниже остаются доступны — понижение
    добровольное. Исключение из первого ограничения — предложение повысить грейд после уверенно
    пройденного теста.
    """
    grades = list(GRADES)
    locks: dict[str, dict[str, datetime]] = {specialization: {} for specialization in SPECIALIZATIONS}
    category = db.get(CandidateCategory, user_id)
    until = _category_lock(category, now)
    if until:
        for specialization in locks:
            locks[specialization] = dict.fromkeys(grades, until)
        if category.upgrade_offer:
            # Уверенный результат открывает одну досрочную попытку на следующий грейд.
            locks[category.specialization].pop(grades[grades.index(category.grade) + 1], None)
    retake = timedelta(days=settings.retake_cooldown_days)
    failed = db.scalars(
        select(Assessment).where(
            Assessment.user_id == user_id,
            Assessment.status == AttemptStatus.failed,
            Assessment.finished_at > now - retake,
        )
    )
    for attempt in failed:
        until = attempt.finished_at + retake
        own = locks.setdefault(attempt.specialization, {})
        for grade in grades[grades.index(attempt.grade) :]:
            own[grade] = max(own.get(grade, until), until)
    return locks


def _availability(locks: dict[str, datetime]) -> list[GradeAvailability]:
    return [GradeAvailability(grade=grade, available_from=locks.get(grade)) for grade in GRADES]


def _state(db: Session, user_id: int) -> AssessmentState:
    now = utcnow()
    active = _active_attempt(db, user_id, now)
    locks = _grade_locks(db, user_id, now)
    history = db.scalars(
        select(Assessment)
        .where(Assessment.user_id == user_id, Assessment.status != AttemptStatus.in_progress)
        .order_by(Assessment.id.desc())
    ).all()
    category = db.get(CandidateCategory, user_id)
    # «Своя» специализация — подтверждённая, а без категории — та, по которой был последний тест.
    own = category.specialization if category else history[0].specialization if history else None
    return AssessmentState(
        category=category,
        active=ActiveAttemptOut(
            **_attempt_fields(active),
            position=len(active.questions),
            min_total=adaptive.MIN_LENGTH,
            question=active.questions[-1],
        )
        if active
        else None,
        history=[AttemptOut(**_attempt_fields(attempt)) for attempt in history],
        grades=_availability(locks.get(own, {})),
        grades_by_specialization={specialization: _availability(own_locks) for specialization, own_locks in locks.items()},
        demo_mode=settings.demo_mode,
    )


@router.get("", response_model=AssessmentState, summary="Категория, текущий тест и история попыток")
def get_state(user: User = Depends(current_candidate), db: Session = Depends(get_db)):
    return _state(db, user.id)


@router.post(
    "",
    response_model=AssessmentState,
    status_code=status.HTTP_201_CREATED,
    summary="Опрос и начало теста на выбранный грейд",
    responses={409: {"description": "Тест уже идёт либо грейд пока недоступен"}},
)
def start(data: StartIn, user: User = Depends(current_candidate), db: Session = Depends(get_db)):
    now = utcnow()
    if _active_attempt(db, user.id, now):
        raise HTTPException(status.HTTP_409_CONFLICT, "Сначала завершите начатый тест")
    category = db.get(CandidateCategory, user.id)
    # Досрочная попытка повышения относится только к подтверждённой специализации.
    category_locked = _category_lock(category, now)
    if category_locked and data.specialization != category.specialization:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Сменить специализацию можно будет {category_locked:%d.%m.%Y}",
        )
    locked_until = _grade_locks(db, user.id, now)[data.specialization].get(data.grade)
    if locked_until:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Тест на этот грейд по этой специализации будет доступен {locked_until:%d.%m.%Y}",
        )
    if category:
        # Предложение повысить грейд одноразово.
        category.upgrade_offer = False
    # Ответы опроса сохраняются в профиле: по стеку работодатель затем фильтрует подборку.
    profile = get_or_create_profile(db, user)
    profile.specialization = data.specialization
    profile.stack = data.stack
    attempt = Assessment(
        user_id=user.id,
        specialization=data.specialization,
        grade=data.grade,
        questions=[],
        theta=adaptive.start_theta(data.grade),
        started_at=now,
        expires_at=now + timedelta(minutes=settings.test_duration_min),
    )
    db.add(attempt)
    try:
        db.flush()
        _serve_next(db, attempt)
        db.commit()
    except IntegrityError:
        # Параллельный запрос успел начать тест первым: уникальный индекс не дал создать вторую попытку.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Сначала завершите начатый тест") from None
    return _state(db, user.id)


@router.post(
    "/{attempt_id}/answer",
    response_model=AssessmentState,
    summary="Ответить на текущее задание: выдаётся следующее либо тест завершается с присвоением категории",
    responses={
        404: {"description": "Попытка не найдена"},
        409: {"description": "Тест завершён, время истекло либо ответ дан не на текущее задание"},
        422: {"description": "Такого варианта ответа в задании нет"},
    },
)
def answer(
    attempt_id: PathId,
    data: AnswerIn,
    user: User = Depends(current_candidate),
    db: Session = Depends(get_db),
):
    attempt = db.get(Assessment, attempt_id)
    if attempt is None or attempt.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Попытка не найдена")
    now = utcnow()
    if attempt.status != AttemptStatus.in_progress or _active_attempt(db, user.id, now) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Тест уже завершён или время истекло")
    # Номер задания защищает от повторной отправки: ответ не должен попасть на следующее задание.
    if data.position != len(attempt.questions):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ответ дан не на текущее задание")
    # Вариант сверяется с выданным заданием до изменения попытки: ошибочный номер не «сжигает» задание.
    if data.answer is not None and data.answer >= len(attempt.questions[-1]["options"]):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Такого варианта ответа в задании нет")

    questions = [*attempt.questions[:-1], {**attempt.questions[-1], "answer": data.answer}]
    try:
        attempt.questions = questions
        responses = [
            (question["a"], question["b"], question["answer"] == question["correct"]) for question in questions
        ]
        attempt.theta, attempt.se = adaptive.estimate(responses)
        if adaptive.is_finished(responses, attempt.grade):
            _finish(db, attempt, now)
            _flag_drifted(db, attempt)
        else:
            _serve_next(db, attempt)
        db.commit()
    except StaleDataError:
        # На это задание одновременно пришёл другой ответ и был сохранён первым.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ответ дан не на текущее задание") from None
    return _state(db, user.id)


@router.post(
    "/reset",
    response_model=AssessmentState,
    summary="Демо-режим: удалить свои попытки и категорию, чтобы пройти тест заново",
    responses={404: {"description": "Стенд работает не в демо-режиме"}},
)
def reset(user: User = Depends(current_candidate), db: Session = Depends(get_db)):
    # Сроки пересдачи — часть механики, поэтому на рабочем стенде обойти их нельзя. На стенде проверки
    # эксперту нужно пройти тест несколько раз подряд и сравнить результаты.
    if not settings.demo_mode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сброс попыток доступен только в демо-режиме")
    db.execute(delete(Assessment).where(Assessment.user_id == user.id))
    db.execute(delete(CandidateCategory).where(CandidateCategory.user_id == user.id))
    db.commit()
    return _state(db, user.id)


def _flag_drifted(db: Session, attempt: Assessment) -> None:
    """После завершённого теста сверяет профильные задания его специализации с ожидаемой решаемостью
    и снимает с выдачи те, ответы на которые, судя по статистике, разошлись."""
    finished = db.scalars(
        select(Assessment.questions).where(
            Assessment.specialization == attempt.specialization,
            Assessment.finished_at.is_not(None),
            Assessment.id != attempt.id,
        )
    ).all()
    known = set(db.scalars(select(ItemFlag.item_id)))
    for item in drift.analyze([*finished, attempt.questions]):
        if item.flagged and item.item_id not in known:
            db.add(ItemFlag(item_id=item.item_id, shown=item.shown, observed=item.observed, expected=item.expected))


def _finish(db: Session, attempt: Assessment, now: datetime) -> None:
    grades = list(GRADES)
    attempt.correct_count = sum(question["answer"] == question["correct"] for question in attempt.questions)
    attempt.score = adaptive.to_score(attempt.theta)
    attempt.finished_at = now
    if attempt.theta < adaptive.GRADE_CUTS[attempt.grade]:
        # Имеющаяся категория при провале сохраняется: грейд принудительно не понижается.
        attempt.status = AttemptStatus.failed
        return
    attempt.status = AttemptStatus.passed
    higher = grades[grades.index(attempt.grade) + 1 :]
    category = db.get(CandidateCategory, attempt.user_id) or CandidateCategory(user_id=attempt.user_id)
    category.specialization = attempt.specialization
    category.grade = attempt.grade
    category.score = attempt.score
    category.upgrade_offer = bool(higher) and attempt.theta >= adaptive.GRADE_CUTS[higher[0]]
    category.assigned_at = now
    db.add(category)
