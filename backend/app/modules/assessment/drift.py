"""Мониторинг дрейфа заданий: признак того, что ответы на задание разошлись между кандидатами.

Общие задания параметризованы — числа и код в них каждый раз новые, заучить ответ нельзя. Профильные
(ситуационные вопросы и термины) имеют постоянный текст и со временем могут утечь. Поэтому уровень
кандидата оценивается отдельно, только по общим заданиям попытки («якорная» оценка), и по ней считается,
как часто кандидаты должны были ответить на профильное задание верно. Если его решают заметно чаще
ожидаемого, задание снимается с выдачи, пока его не перепишут.

Модуль не зависит от БД: его же использует симуляция в scripts/validate_testing.py.
"""

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from app.modules.assessment import adaptive

# Меньше ответов — выводов не делаем.
MIN_SHOWN = 30
# Доля верных ответов выше ожидаемой больше чем на 15 п.п. …
EXCESS = 0.15
# … и это превышение не объясняется случайностью (число стандартных отклонений).
Z_SCORE = 2.5
# Якорная оценка считается не меньше чем по стольким общим заданиям.
MIN_ANCHOR = 5


@dataclass
class ItemDrift:
    item_id: str
    shown: int
    # Доля верных ответов: наблюдаемая и ожидаемая по модели для отвечавших кандидатов.
    observed: float
    expected: float
    flagged: bool


def is_anchor(item_id: str) -> bool:
    return item_id.startswith("common.")


def anchor_theta(questions: list[dict]) -> float | None:
    """Оценка уровня только по общим заданиям попытки; None — их слишком мало."""
    responses = [
        (question["a"], question["b"], question["answer"] == question["correct"])
        for question in questions
        if "answer" in question and is_anchor(question["item_id"])
    ]
    return adaptive.estimate(responses)[0] if len(responses) >= MIN_ANCHOR else None


def analyze(attempts: Iterable[list[dict]]) -> list[ItemDrift]:
    """Отчёт по профильным заданиям; attempts — задания попыток в том виде, в каком они хранятся в БД."""
    answers: dict[str, list[tuple[float, bool]]] = defaultdict(list)
    for questions in attempts:
        theta = anchor_theta(questions)
        if theta is None:
            continue
        for question in questions:
            if "answer" in question and not is_anchor(question["item_id"]):
                expected = adaptive.probability(theta, question["a"], question["b"])
                answers[question["item_id"]].append((expected, question["answer"] == question["correct"]))
    report = []
    for item_id, rows in sorted(answers.items()):
        shown = len(rows)
        observed = sum(correct for _, correct in rows) / shown
        expected = sum(p for p, _ in rows) / shown
        deviation = math.sqrt(sum(p * (1 - p) for p, _ in rows)) / shown
        excess = observed - expected
        flagged = shown >= MIN_SHOWN and excess > EXCESS and excess > Z_SCORE * deviation
        report.append(ItemDrift(item_id, shown, observed, expected, flagged))
    return report
