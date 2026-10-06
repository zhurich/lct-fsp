"""Синтетические кандидаты с известным «истинным» уровнем и прогон теста для них.

Эталонной разметки на хакатоне нет, поэтому она задаётся генератором: у каждого кандидата есть скрытые
истинный уровень θ и набор технологий, которыми он действительно владеет, и наблюдаемые данные — заявленные
грейд и стек, которые могут быть завышены. Платформа видит только наблюдаемое и ответы на задания; качество
измеряется сравнением её выводов со скрытой истиной.
"""

import math
import random
from collections.abc import Callable, Collection
from dataclasses import dataclass, field

from app.modules.assessment import adaptive, bank
from app.modules.assessment.bank import Item, Question
from app.modules.fsp.registry import MockRegistry
from app.modules.reference.data import GRADES, SPECIALIZATIONS
from app.modules.reference.skills import SKILLS

GRADE_LIST = list(GRADES)
_SPEC_SKILLS = {
    code: [name for name, (_, specs) in SKILLS.items() if code in specs] for code in SPECIALIZATIONS
}
_CITIES = ["Москва", "Санкт-Петербург", "Казань", "Новосибирск", "Екатеринбург", "Нижний Новгород", "Самара"]


@dataclass
class Person:
    specialization: str
    theta: float
    # Скрытая истина.
    true_grade: str | None
    skills: list[str]
    # То, что кандидат сообщает о себе.
    claimed_grade: str
    claimed_stack: list[str]
    experience_years: float
    work_formats: list[str]
    city: str
    fsp_id: str | None = None
    fsp_achievements: list[dict] = field(default_factory=list)


def make_person(rng: random.Random, specialization: str | None = None, inflation: float = 0.35) -> Person:
    """inflation — доля кандидатов, завышающих грейд в самооценке."""
    specialization = specialization or rng.choice(list(SPECIALIZATIONS))
    theta = max(-2.6, min(2.6, rng.gauss(0, 1.1)))
    true_grade = adaptive.grade_of(theta)
    level = GRADE_LIST.index(true_grade) if true_grade else 0

    pool = _SPEC_SKILLS[specialization]
    skills = rng.sample(pool, min(len(pool), rng.randint(3, 5) + level))
    # В резюме часть навыков пропущена, а у трети кандидатов есть «приписки» — технологии, которыми не владеют.
    claimed_stack = [skill for skill in skills if rng.random() < 0.9]
    if rng.random() < 0.35:
        extra = [skill for skill in pool if skill not in skills]
        claimed_stack += rng.sample(extra, min(len(extra), rng.randint(1, 2)))
    rng.shuffle(claimed_stack)
    # Самооценка грейда: по умолчанию 60% точны, 35% завышают (из них каждый седьмой — на два грейда),
    # 5% занижают.
    shift = rng.choices([0, 1, 2, -1], [0.95 - inflation, inflation * 6 / 7, inflation / 7, 0.05])[0]
    claimed_grade = GRADE_LIST[max(0, min(3, level + shift))]

    person = Person(
        specialization=specialization,
        theta=theta,
        true_grade=true_grade,
        skills=skills,
        claimed_grade=claimed_grade,
        claimed_stack=claimed_stack,
        experience_years=[0, 0.5, 2, 5][level] + round(rng.random() * [0.5, 0.5, 1.5, 4][level], 1),
        work_formats=rng.sample(["office", "hybrid", "remote"], rng.randint(1, 3)),
        city=rng.choice(_CITIES),
    )
    # Участников ФСП среди сильных кандидатов больше, но история соревнований есть не у всех.
    if rng.random() < max(0.05, min(0.5, 0.2 + 0.1 * theta)):
        number = rng.randrange(1, 999_999)
        number += number % 7 == 0
        person.fsp_id = f"FSP-{number:06d}"
        person.fsp_achievements = MockRegistry().fetch(person.fsp_id) or []
    return person


# Истинные параметры заданий: {item_id: (a, b)}. В тесте используются номинальные из банка; расхождение
# между ними моделирует неидеальную калибровку.
TrueParams = dict[str, tuple[float, float]]


def nominal_params() -> TrueParams:
    return {item.id: (item.a, item.b) for item in bank.ITEMS.values()}


def perturbed_params(rng: random.Random, b_sd: float = 0.4, a_sigma: float = 0.25) -> TrueParams:
    """Реалистичный сценарий: настоящая сложность задания отличается от назначенной экспертом."""
    return {
        item.id: (item.a * math.exp(rng.gauss(0, a_sigma)), item.b + rng.gauss(0, b_sd))
        for item in bank.ITEMS.values()
    }


Respond = Callable[[Item, Question], int]


def honest(theta: float, params: TrueParams, rng: random.Random) -> Respond:
    """Кандидат отвечает сам: верно с вероятностью по модели, иначе выбирает один из неверных вариантов."""

    def respond(item: Item, question: Question) -> int:
        a, b = params[item.id]
        if rng.random() < adaptive.probability(theta, a, b):
            return question.correct
        return rng.choice([index for index in range(4) if index != question.correct])

    return respond


@dataclass
class TestRun:
    grade: str
    theta: float
    se: float
    passed: bool
    # В том же виде, в каком попытка хранится в БД.
    questions: list[dict]

    @property
    def item_ids(self) -> list[str]:
        return [question["item_id"] for question in self.questions]


def run_test(
    specialization: str,
    grade: str,
    respond: Respond,
    rng: random.Random,
    exposure: dict[str, int] | None = None,
    seen: Collection[str] = (),
) -> TestRun:
    """Полный адаптивный тест теми же функциями, что и в приложении, без БД и веб-слоя."""
    exposure = exposure if exposure is not None else {}
    theta, se, questions, responses = adaptive.start_theta(grade), 0.0, [], []
    for position in range(adaptive.TEST_LENGTH):
        used = {question["item_id"] for question in questions}
        pool = [
            item for item in bank.pool(specialization, adaptive.is_specialized(position)) if item.id not in used
        ]
        item = adaptive.pick_item(pool, theta, exposure, seen, rng)
        exposure[item.id] = exposure.get(item.id, 0) + 1
        question = item.generate(rng)
        answer = respond(item, question)
        questions.append(
            {
                "item_id": item.id,
                "a": item.a,
                "b": item.b,
                "text": question.text,
                "code": question.code,
                "options": question.options,
                "correct": question.correct,
                "answer": answer,
            }
        )
        responses.append((item.a, item.b, answer == question.correct))
        theta, se = adaptive.estimate(responses)
    return TestRun(grade, theta, se, theta >= adaptive.GRADE_CUTS[grade], questions)


def certify(person: Person, params: TrueParams, rng: random.Random, exposure: dict[str, int] | None = None) -> list[TestRun]:
    """Путь кандидата на платформе по тем же правилам, что и в приложении.

    Тест на заявленный грейд; при провале — на грейд ниже, и так далее. После пройденного теста, если
    результат дотягивает до следующего грейда, кандидат пользуется предложением досрочно сдать на него.
    Возвращает все попытки; категория — грейд последней пройденной. Сроки между попытками не моделируются.
    """
    runs: list[TestRun] = []
    seen: set[str] = set()

    def attempt(grade: str) -> TestRun:
        run = run_test(person.specialization, grade, honest(person.theta, params, rng), rng, exposure, seen)
        runs.append(run)
        seen.update(run.item_ids)
        return run

    level = GRADE_LIST.index(person.claimed_grade)
    while level >= 0 and not attempt(GRADE_LIST[level]).passed:
        level -= 1
    # Каждое предложение повышения одноразово: неудачная попытка оставляет достигнутую категорию.
    while 0 <= level < 3 and runs[-1].passed and runs[-1].theta >= adaptive.GRADE_CUTS[GRADE_LIST[level + 1]]:
        level += 1
        attempt(GRADE_LIST[level])
    return runs


def category_of(runs: list[TestRun]) -> TestRun | None:
    """Попытка, подтвердившая итоговую категорию; None — категория не присвоена."""
    passed = [run for run in runs if run.passed]
    return passed[-1] if passed else None
