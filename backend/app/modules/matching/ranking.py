"""Ранжирование кандидатов под потребность работодателя.

Итоговая оценка = соответствие потребности (вес 85) + сила подтверждённого профиля (вес не больше 15):
сила профиля упорядочивает кандидатов с равным соответствием, но не перевешивает разницу в одном
требовании — грейде, формате работы или одной технологии из требуемого стека. Для этого её вес
ограничен «ценой» одной технологии: чем длиннее требуемый стек, тем меньше весит сила профиля
(см. strength_share). Верхняя граница веса подобрана по валидации (scripts/validate_matching.py): при
большей доле силы профиля в топ чаще попадали кандидаты, сильные сами по себе, но хуже подходящие под запрос.
Соответствие: грейд, покрытие требуемого стека, формат работы (учитываются только заданные в запросе).
Сила профиля: балл теста, достижения ФСП, актуальность (давность теста или последнего ответа на
задание работодателя).
Каждая составляющая возвращается вместе с оценкой — из них строится объяснение «почему в подборке».
Кандидат, не подтвердивший заявленный грейд, оценки не получает (см. describe_unverified): он остаётся в
выдаче с пометкой, но всегда ниже подтверждённых.

Модуль не обращается к БД: на вход — запрос и данные кандидата, поэтому его же использует валидация.
"""

from dataclasses import dataclass, field
from datetime import datetime

from app.modules.fsp.registry import fsp_strength
from app.modules.reference.data import GRADES, SPECIALIZATIONS, WORK_FORMATS
from app.modules.reference.skills import normalize_skill, skill_key

FIT_SHARE = 0.85
FIT_WEIGHTS = {"grade": 0.4, "stack": 0.45, "format": 0.15}
STRENGTH_WEIGHTS = {"test": 0.6, "fsp": 0.25, "fresh": 0.15}
# Кандидат смежного грейда попадает в подборку, но с половинным соответствием по грейду.
ADJACENT_GRADE_FIT = 0.5
# Какую часть «цены» одного требования может дать сила профиля: меньше единицы, чтобы не перевесить его.
STRENGTH_CAP = 0.9


def strength_share(requirements: "Requirements", fit_keys: set[str]) -> float:
    """Вес силы профиля в оценке под конкретный запрос.

    Обычно это 15%, но не больше 90% вклада самого мелкого требования запроса: одной технологии стека,
    формата работы или шага грейда. Так кандидат с полным покрытием стека всегда выше кандидата того же
    грейда и формата, которому не хватает технологии, каким бы сильным ни был профиль второго.
    """
    weights = sum(FIT_WEIGHTS[key] for key in fit_keys)
    steps = []
    if "grade" in fit_keys:
        steps.append(FIT_WEIGHTS["grade"] * (1 - ADJACENT_GRADE_FIT))
    if "stack" in fit_keys:
        steps.append(FIT_WEIGHTS["stack"] / len({skill_key(skill) for skill in requirements.stack}))
    if "format" in fit_keys:
        steps.append(FIT_WEIGHTS["format"])
    return min(1 - FIT_SHARE, STRENGTH_CAP * FIT_SHARE * min(steps) / weights)


@dataclass
class Requirements:
    specialization: str | None = None
    grade: str | None = None
    stack: list[str] = field(default_factory=list)
    work_formats: list[str] = field(default_factory=list)


@dataclass
class CandidateData:
    specialization: str
    grade: str
    test_score: float
    assigned_at: datetime
    stack: list[str]
    work_formats: list[str]
    fsp_achievements: list[dict]
    # Ответы на регулярные задания работодателей: дата последнего и выставленные оценки (1–5).
    last_answer_at: datetime | None = None
    answer_ratings: list[int] = field(default_factory=list)
    answers_total: int = 0


@dataclass
class UnverifiedData:
    """Кандидат без категории: грейд заявлен, но последний тест на него не пройден."""

    specialization: str
    claimed_grade: str
    # Балл непройденного теста и порог заявленного грейда, 0…1.
    attempt_score: float
    pass_score: float
    attempted_at: datetime
    stack: list[str]
    work_formats: list[str]
    fsp_achievements: list[dict]


@dataclass
class Match:
    # Итоговая оценка 0…100; None — грейд не подтверждён, оценка не выставляется.
    score: float | None
    matched_stack: list[str]
    # Составляющие оценки для показа: ключ, подпись, значение 0…1.
    breakdown: list[dict]
    reasons: list[str]


def _freshness(last_activity: datetime, now: datetime) -> float:
    """1 в первые 90 дней после последней активности (тест или ответ на задание работодателя),
    затем линейно снижается до 0,3 к году."""
    days = (now - last_activity).days
    if days <= 90:
        return 1.0
    return max(0.3, 1.0 - 0.7 * (days - 90) / 275)


def _grade_distance(requirements: Requirements, grade: str) -> int | None:
    """Расстояние между грейдом кандидата и запрошенным; None — грейд в запросе не задан."""
    if not requirements.grade:
        return None
    grades = list(GRADES)
    return abs(grades.index(grade) - grades.index(requirements.grade))


def _match_stack(requirements: Requirements, stack: list[str], reasons: list[str]) -> tuple[list[str], float | None]:
    """Технологии запроса, которые есть у кандидата, и доля покрытия; None — стек в запросе не задан."""
    wanted = {skill_key(skill): normalize_skill(skill) for skill in requirements.stack}
    own = {skill_key(skill) for skill in stack}
    matched = [name for key, name in wanted.items() if key in own]
    if not wanted:
        return matched, None
    missing = [name for key, name in wanted.items() if key not in own]
    if matched:
        reasons.append(
            f"Стек: {len(matched)} из {len(wanted)} — {', '.join(matched)}"
            + (f"; нет: {', '.join(missing)}" if missing else "")
        )
    else:
        reasons.append("Требуемых технологий в стеке кандидата нет")
    return matched, len(matched) / len(wanted)


def describe_unverified(requirements: Requirements, candidate: UnverifiedData) -> tuple[Match, tuple] | None:
    """Карточка кандидата с неподтверждённым грейдом и ключ порядка среди таких же; None — не подходит.

    Отбор тот же, что у подтверждённых: специализация и заявленный грейд не дальше смежного. Оценки нет:
    заявленный грейд ничем не подкреплён, и сравнивать его с подтверждённым числом было бы нечестно.
    """
    if requirements.specialization and candidate.specialization != requirements.specialization:
        return None
    if (_grade_distance(requirements, candidate.claimed_grade) or 0) > 1:
        return None
    grade = GRADES[candidate.claimed_grade]["name"]
    reasons = [
        f"Грейд «{grade}» заявлен, но не подтверждён: тест от {candidate.attempted_at:%d.%m.%Y} не пройден — "
        f"балл {candidate.attempt_score * 100:.0f} из 100 при пороге {candidate.pass_score * 100:.0f}"
    ]
    matched, coverage = _match_stack(requirements, candidate.stack, reasons)
    if candidate.fsp_achievements:
        prizes = sum(1 for item in candidate.fsp_achievements if item["place"])
        reasons.append(
            f"Достижения ФСП: соревнований — {len(candidate.fsp_achievements)}, призовых мест — {prizes}"
        )
    order = (coverage or 0.0, candidate.attempt_score)
    return Match(score=None, matched_stack=matched, breakdown=[], reasons=reasons), order


def rank(requirements: Requirements, candidate: CandidateData, now: datetime) -> Match | None:
    """Оценка кандидата под запрос; None — кандидат не подходит по категории."""
    if requirements.specialization and candidate.specialization != requirements.specialization:
        return None
    category = f"{SPECIALIZATIONS[candidate.specialization]} · {GRADES[candidate.grade]['name']}"
    reasons = []
    fit: dict[str, float] = {}

    distance = _grade_distance(requirements, candidate.grade)
    if distance is None:
        reasons.append(f"Категория «{category}»")
    elif distance > 1:
        return None
    else:
        fit["grade"] = 1.0 if distance == 0 else ADJACENT_GRADE_FIT
        if distance == 0:
            reasons.append(f"Категория «{category}» совпадает с запросом")
        else:
            reasons.append(f"Категория «{category}» — смежный грейд к запрошенному")

    matched, coverage = _match_stack(requirements, candidate.stack, reasons)
    if coverage is not None:
        fit["stack"] = coverage

    # Формат сравнивается, только если его указали обе стороны: пустое поле — не отказ.
    if requirements.work_formats and candidate.work_formats:
        common = [code for code in requirements.work_formats if code in candidate.work_formats]
        fit["format"] = 1.0 if common else 0.0
        if common:
            reasons.append("Подходит формат работы: " + ", ".join(WORK_FORMATS[code].lower() for code in common))
        else:
            reasons.append("Формат работы не совпадает с пожеланиями кандидата")

    strength = {
        "test": candidate.test_score,
        "fsp": fsp_strength(candidate.fsp_achievements, now.date()),
        "fresh": _freshness(max(candidate.assigned_at, candidate.last_answer_at or candidate.assigned_at), now),
    }
    reasons.append(f"Тест на грейд пройден, балл {candidate.test_score * 100:.0f} из 100")
    if candidate.fsp_achievements:
        prizes = sum(1 for item in candidate.fsp_achievements if item["place"])
        reasons.append(
            f"Достижения ФСП: соревнований — {len(candidate.fsp_achievements)}, призовых мест — {prizes}"
        )

    if candidate.answers_total:
        rated = candidate.answer_ratings
        average = f", средняя оценка работодателей {sum(rated) / len(rated):.1f} из 5" if rated else ""
        reasons.append(f"Отвечал на задания работодателей: {candidate.answers_total}{average}")

    strength_value = sum(STRENGTH_WEIGHTS[key] * value for key, value in strength.items())
    # Запрос без требований (просмотр банка) ранжируется только по силе профиля.
    total = strength_value
    if fit:
        # Веса нормируются по заданным составляющим: незаполненное требование не занижает оценку.
        fit_value = sum(FIT_WEIGHTS[key] * value for key, value in fit.items()) / sum(FIT_WEIGHTS[key] for key in fit)
        share = strength_share(requirements, set(fit))
        # Нормировка сохраняет шкалу 0…100: идеальный кандидат получает 100 при любой длине стека.
        total = (FIT_SHARE * fit_value + share * strength_value) / (FIT_SHARE + share)

    labels = {
        "grade": "Грейд",
        "stack": "Стек",
        "format": "Формат работы",
        "test": "Тест",
        "fsp": "Достижения ФСП",
        "fresh": "Актуальность профиля",
    }
    return Match(
        score=round(total * 100, 1),
        matched_stack=matched,
        breakdown=[
            {"key": key, "label": labels[key], "value": round(value, 2)} for key, value in {**fit, **strength}.items()
        ],
        reasons=reasons,
    )
