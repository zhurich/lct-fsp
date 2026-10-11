"""Адаптивное тестирование на трёхпараметрической модели IRT (3PL).

Вероятность верного ответа: P(θ) = c + (1 − c) / (1 + exp(−a·(θ − b))), где θ — уровень кандидата,
b — сложность задания, a — его различающая способность, c — вероятность угадать (4 варианта → 0,25).
Шкала θ привязана к грейдам: граница грейда с номером i лежит в точке i − 2 (стажёр −2 … senior +1).

Тест отвечает на вопрос «уровень кандидата не ниже границы заявленного грейда?», поэтому задания
подбираются по информации в точке этой границы, а длина теста зависит от того, насколько ответ очевиден.

Модуль не зависит от БД и веб-слоя, чтобы тем же кодом прогонять симуляции при валидации.
"""

import math
import random
from collections.abc import Collection, Mapping, Sequence

from app.modules.assessment import bank
from app.modules.assessment.bank import Item
from app.modules.reference.data import GRADES

GUESS = 0.25
# Длина теста переменная: после MIN_LENGTH заданий тест заканчивается, как только решение «уровень не ниже
# границы заявленного грейда» принято с уверенностью CONFIDENCE; кандидаты у самой границы получают
# дополнительные задания, но не больше MAX_LENGTH.
MIN_LENGTH = 12
MAX_LENGTH = 18
CONFIDENCE = 0.9
# Задание выбирается случайно из TOP_K самых информативных: это размывает показы по банку.
TOP_K = 4
# Нижняя граница грейда на шкале θ.
GRADE_CUTS: dict[str, float] = {grade: index - 2 for index, grade in enumerate(GRADES)}

_GRID = [step / 10 for step in range(-40, 41)]
# Априорное распределение уровня — N(0, 1.5²): слабое и не зависит от заявленного грейда,
# поэтому заявка влияет только на то, с каких заданий начинается тест, но не на оценку.
_PRIOR = [math.exp(-0.5 * (theta / 1.5) ** 2) for theta in _GRID]


def probability(theta: float, a: float, b: float) -> float:
    return GUESS + (1 - GUESS) / (1 + math.exp(-a * (theta - b)))


def information(theta: float, a: float, b: float) -> float:
    """Информация Фишера: насколько ответ на задание уточняет оценку при данном θ."""
    p = probability(theta, a, b)
    return a * a * ((p - GUESS) / (1 - GUESS)) ** 2 * (1 - p) / p


Responses = Sequence[tuple[float, float, bool]]


def _posterior(responses: Responses) -> list[float]:
    """Апостериорное распределение уровня на сетке по ответам [(a, b, верно ли)]."""
    weights = []
    for theta, prior in zip(_GRID, _PRIOR):
        likelihood = prior
        for a, b, correct in responses:
            p = probability(theta, a, b)
            likelihood *= p if correct else 1 - p
        weights.append(likelihood)
    total = sum(weights)
    return [weight / total for weight in weights]


def estimate(responses: Responses) -> tuple[float, float]:
    """Оценка уровня по ответам [(a, b, верно ли)]: среднее и стандартное отклонение апостериорного
    распределения на сетке (EAP). В отличие от максимума правдоподобия, определена и тогда, когда
    все ответы верны или все неверны."""
    weights = _posterior(responses)
    mean = sum(theta * weight for theta, weight in zip(_GRID, weights))
    variance = sum((theta - mean) ** 2 * weight for theta, weight in zip(_GRID, weights))
    return mean, math.sqrt(variance)


def pass_probability(responses: Responses, grade: str) -> float:
    """Апостериорная вероятность того, что уровень кандидата не ниже границы грейда."""
    cut = GRADE_CUTS[grade]
    return sum(weight for theta, weight in zip(_GRID, _posterior(responses)) if theta >= cut)


def is_finished(responses: Responses, grade: str) -> bool:
    """Пора ли заканчивать тест: достигнут предел длины либо решение по заявленному грейду уже уверенное."""
    if len(responses) >= MAX_LENGTH:
        return True
    if len(responses) < MIN_LENGTH:
        return False
    confidence = pass_probability(responses, grade)
    return confidence >= CONFIDENCE or confidence <= 1 - CONFIDENCE


def is_complete(questions: Sequence[dict]) -> bool:
    """Доведена ли попытка до конца: у прерванной по времени последнее задание осталось без ответа."""
    return bool(questions) and "answer" in questions[-1]


def start_theta(grade: str) -> float:
    """Оценка уровня до первого ответа — середина заявленного грейда."""
    return GRADE_CUTS[grade] + 0.5


def to_score(theta: float) -> float:
    """Балл теста 0…1 для показа и ранжирования; границы грейдов — 0,20 / 0,35 / 0,50 / 0,65."""
    return min(1.0, max(0.0, round(0.5 + 0.15 * theta, 2)))


def grade_of(theta: float) -> str | None:
    """Грейд, которому соответствует оценка; None — ниже границы младшего грейда."""
    reached = [grade for grade, cut in GRADE_CUTS.items() if theta >= cut]
    return reached[-1] if reached else None


def is_specialized(position: int) -> bool:
    """Баланс содержания: каждое третье задание — профильное, остальные — общеинженерные."""
    return position % 3 == 1


def position_pool(
    specialization: str, position: int, used: Collection[str], flagged: Collection[str] = ()
) -> list[Item]:
    """Задания, из которых выбирается очередное.

    flagged — профильные задания, снятые с выдачи мониторингом дрейфа (drift.py). Если неснятых профильных
    не хватает для выбора, позицию занимает общее параметризованное задание: его текст не заучить.
    """
    common = [item for item in bank.pool(specialization, False) if item.id not in used]
    if not is_specialized(position):
        return common
    own = [item for item in bank.pool(specialization, True) if item.id not in used and item.id not in flagged]
    return own if len(own) >= TOP_K else common


def pick_item(
    pool: Sequence[Item],
    point: float,
    exposure: Mapping[str, int],
    seen: Collection[str],
    rng: random.Random,
) -> Item:
    """Выбирает следующее задание из ещё не выданных в этой попытке.

    Задания, которые кандидат видел в прошлых попытках, исключаются, пока хватает новых. Из оставшихся
    берутся TOP_K самых информативных в точке point (граница заявленного грейда), и реже показанные всем
    получают больший шанс.
    """
    fresh = [item for item in pool if item.id not in seen]
    if len(fresh) < TOP_K:
        fresh = list(pool)
    ranked = sorted(fresh, key=lambda item: information(point, item.a, item.b), reverse=True)[:TOP_K]
    least = min(exposure.get(item.id, 0) for item in ranked)
    weights = [1 / (1 + exposure.get(item.id, 0) - least) for item in ranked]
    return rng.choices(ranked, weights)[0]
