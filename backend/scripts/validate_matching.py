"""Валидация механики подбора на синтетическом банке кандидатов.

Запуск: python -m scripts.validate_matching [--n 3000] [--seed 1]

1. Разбор потребности: тексты вакансий с ручной разметкой (scripts/vacancies.py) → точность извлечения.
2. Подбор: для каждой вакансии строится выдача и считается доля релевантных кандидатов в топе.
   Релевантность определяется по скрытой истине (истинный грейд и реальные навыки кандидата), которую
   платформа не видит. Сравниваются три способа ранжирования:
   - случайный порядок внутри специализации;
   - «по резюме»: заявленный грейд и заявленный стек без тестирования — так работают обычные площадки;
   - платформа: категория, подтверждённая тестом, и ранжирование по соответствию и силе профиля.
"""

import argparse
import math
import random
import statistics
from datetime import datetime, timedelta, timezone

from app.modules.assessment import adaptive
from app.modules.matching.parser import parse_need
from app.modules.matching.ranking import CandidateData, Requirements, rank
from app.modules.reference.data import SPECIALIZATIONS
from app.modules.reference.skills import SKILLS
from scripts import synth
from scripts.synth import GRADE_LIST, Person
from scripts.vacancies import VACANCIES
from scripts import utf8_output

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
TOP = (5, 10)


def parser_quality() -> dict:
    """Разбор текстов вакансий против ручной разметки."""
    hits = {"specialization": 0, "grade": 0, "work_formats": 0, "salary": 0}
    found = expected = correct = 0
    for vacancy in VACANCIES:
        parsed, gold = parse_need(vacancy["text"]), vacancy["gold"]
        hits["specialization"] += parsed.specialization == gold["specialization"]
        hits["grade"] += parsed.grade == gold["grade"]
        hits["work_formats"] += set(parsed.work_formats) == set(gold["work_formats"])
        salary = (parsed.salary_from, parsed.salary_to) if parsed.salary_from else None
        hits["salary"] += salary == gold["salary"]
        found += len(parsed.stack)
        expected += len(gold["stack"])
        correct += len(set(parsed.stack) & set(gold["stack"]))
    return {
        "texts": len(VACANCIES),
        **{key: value / len(VACANCIES) for key, value in hits.items()},
        "stack_precision": correct / found,
        "stack_recall": correct / expected,
    }


def relevance(person: Person, need: Requirements) -> int:
    """Эталонная релевантность по скрытой истине: 2 — подходит, 1 — частично, 0 — нет."""
    if person.specialization != need.specialization or person.true_grade is None:
        return 0
    distance = abs(GRADE_LIST.index(person.true_grade) - GRADE_LIST.index(need.grade))
    coverage = len(set(person.skills) & set(need.stack)) / len(need.stack) if need.stack else 1.0
    if distance == 0 and coverage >= 2 / 3:
        return 2
    if (distance == 0 and coverage >= 1 / 3) or (distance == 1 and coverage >= 2 / 3):
        return 1
    return 0


def _metrics(ranked: list[tuple[int, bool]], ideal: list[int]) -> dict:
    """Показатели одной выдачи. ranked — пары (релевантность, истинный грейд ниже запрошенного) в порядке
    выдачи; ideal — релевантности в лучшем возможном порядке."""
    gain = lambda values: sum((2**rel - 1) / math.log2(index + 2) for index, rel in enumerate(values))  # noqa: E731
    relevances = [rel for rel, _ in ranked]
    result = {}
    for k in TOP:
        top = relevances[:k]
        result[f"strict@{k}"] = sum(rel == 2 for rel in top) / k
        result[f"any@{k}"] = sum(rel >= 1 for rel in top) / k
    result["below@10"] = sum(below for _, below in ranked[:10]) / 10
    result["ndcg@10"] = gain(relevances[:10]) / gain(ideal[:10]) if any(ideal) else 0.0
    return result


def _below(person: Person, need: Requirements) -> bool:
    """Кандидат слабее, чем нужно: истинный грейд ниже запрошенного."""
    return person.true_grade is None or GRADE_LIST.index(person.true_grade) < GRADE_LIST.index(need.grade)


def _queries(rng: random.Random, extra: int) -> list[Requirements]:
    """Запросы: разобранные тексты вакансий и случайные структурированные для статистической устойчивости."""
    queries = []
    for vacancy in VACANCIES:
        parsed = parse_need(vacancy["text"])
        queries.append(Requirements(parsed.specialization, parsed.grade, parsed.stack, parsed.work_formats))
    for _ in range(extra):
        specialization = rng.choice(list(SPECIALIZATIONS))
        pool = [name for name, (_, specs) in SKILLS.items() if specialization in specs]
        queries.append(Requirements(specialization, rng.choice(GRADE_LIST), rng.sample(pool, 3)))
    return queries


def compare(n: int, seed: int, extra_queries: int, inflation: float) -> dict:
    """Сравнение способов ранжирования на одном синтетическом банке."""
    rng = random.Random(seed)
    params = synth.perturbed_params(rng)
    people = [synth.make_person(rng, inflation=inflation) for _ in range(n)]

    # Банк платформы: только кандидаты, получившие категорию по тесту.
    bank: list[tuple[Person, CandidateData]] = []
    resume: list[tuple[Person, CandidateData]] = []
    for person in people:
        common = {
            "specialization": person.specialization,
            "assigned_at": NOW - timedelta(days=rng.randint(0, 300)),
            "stack": person.claimed_stack,
            "work_formats": person.work_formats,
        }
        # «По резюме»: грейд со слов кандидата, без балла теста и достижений.
        resume.append(
            (person, CandidateData(grade=person.claimed_grade, test_score=0.5, fsp_achievements=[], **common))
        )
        final = synth.category_of(synth.certify(person, params, rng))
        if final:
            data = CandidateData(
                grade=final.grade,
                test_score=adaptive.to_score(final.theta),
                fsp_achievements=person.fsp_achievements,
                **common,
            )
            bank.append((person, data))

    def ranking(pool, need) -> list[tuple[int, bool]]:
        scored = [
            (match.score, relevance(person, need), _below(person, need))
            for person, data in pool
            if (match := rank(need, data, NOW))
        ]
        # Равные оценки упорядочиваются случайно, чтобы порядок генерации не влиял на результат.
        rng.shuffle(scored)
        scored.sort(key=lambda row: row[0], reverse=True)
        return [(rel, below) for _, rel, below in scored]

    totals = {name: [] for name in ("random", "resume", "platform")}
    base_rates = []
    for need in _queries(rng, extra_queries):
        everyone = [
            (relevance(person, need), _below(person, need))
            for person in people
            if person.specialization == need.specialization
        ]
        ideal = sorted((rel for rel, _ in everyone), reverse=True)
        base_rates.append(sum(rel == 2 for rel, _ in everyone) / len(everyone))
        rng.shuffle(everyone)
        totals["random"].append(_metrics(everyone, ideal))
        totals["resume"].append(_metrics(ranking(resume, need), ideal))
        totals["platform"].append(_metrics(ranking(bank, need), ideal))
    return {
        "bank": len(bank),
        "queries": len(base_rates),
        "base_rate": statistics.mean(base_rates),
        "ranking": {
            name: {key: statistics.mean(row[key] for row in rows) for key in rows[0]} for name, rows in totals.items()
        },
    }


# Доли кандидатов, завышающих грейд в резюме, для анализа чувствительности.
INFLATION_LEVELS = (0.2, 0.35, 0.5, 0.65)


def run(n: int = 3000, seed: int = 1, extra_queries: int = 150) -> dict:
    return {
        "n": n,
        "parser": parser_quality(),
        "base": compare(n, seed, extra_queries, 0.35),
        "sensitivity": {level: compare(n, seed, extra_queries, level)["ranking"] for level in INFLATION_LEVELS},
    }


def render(result: dict) -> str:
    pct = lambda value: f"{value * 100:.0f}%"  # noqa: E731
    parser, base = result["parser"], result["base"]
    lines = [
        "## Подбор",
        "",
        "### Разбор потребности из текста",
        "",
        f"{parser['texts']} описаний вакансий с ручной разметкой (`backend/scripts/vacancies.py`):",
        "",
        f"- специализация определена верно: {pct(parser['specialization'])}",
        f"- грейд определён верно: {pct(parser['grade'])}",
        f"- стек: точность {pct(parser['stack_precision'])}, полнота {pct(parser['stack_recall'])}",
        f"- формат работы: {pct(parser['work_formats'])}",
        f"- зарплатная вилка (включая её отсутствие): {pct(parser['salary'])}",
        "",
        "Тексты писались вместе с правилами разбора, поэтому это проверка на согласованность, а не оценка "
        "на независимых данных: на произвольных текстах точность будет ниже.",
        "",
        "### Доля релевантных кандидатов в топе выдачи",
        "",
        f"Синтетический банк: {result['n']} кандидатов, из них {base['bank']} получили категорию по тесту. "
        f"Запросов: {base['queries']} (разобранные тексты вакансий и случайные сочетания специализации, "
        "грейда и трёх технологий). Релевантность считается по скрытой истине — истинному грейду и реальным "
        "навыкам: «подходит» — та же специализация и грейд и не менее 2/3 требуемого стека; «частично» — "
        f"смежный грейд либо от 1/3 стека. Подходящих в среднем {pct(base['base_rate'])} специализации. "
        "«Слабее запроса» — истинный грейд кандидата ниже запрошенного.",
        "",
        "| Способ ранжирования | Подходят в топ-5 | Подходят в топ-10 | Хотя бы частично в топ-10 | Слабее запроса в топ-10 | NDCG@10 |",
        "|---|---|---|---|---|---|",
    ]
    labels = {
        "random": "Случайный порядок в специализации",
        "resume": "По резюме: заявленные грейд и стек",
        "platform": "Платформа: категория по тесту и ранжирование",
    }
    for name, label in labels.items():
        row = base["ranking"][name]
        lines.append(
            f"| {label} | {pct(row['strict@5'])} | {pct(row['strict@10'])} | {pct(row['any@10'])} "
            f"| {pct(row['below@10'])} | {row['ndcg@10']:.2f} |"
        )
    lines += [
        "",
        "### Чувствительность к честности резюме",
        "",
        "Тот же расчёт при разной доле кандидатов, завышающих грейд в самооценке (в основной таблице — 35%):",
        "",
        "| Завышают грейд | Подходят в топ-10: резюме | Подходят в топ-10: платформа "
        "| Слабее запроса в топ-10: резюме | Слабее запроса в топ-10: платформа |",
        "|---|---|---|---|---|",
    ]
    for level, ranking in result["sensitivity"].items():
        lines.append(
            f"| {pct(level)} | {pct(ranking['resume']['strict@10'])} | {pct(ranking['platform']['strict@10'])} "
            f"| {pct(ranking['resume']['below@10'])} | {pct(ranking['platform']['below@10'])} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    utf8_output()
    args_parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args_parser.add_argument("--n", type=int, default=3000, help="число синтетических кандидатов")
    args_parser.add_argument("--seed", type=int, default=1)
    args = args_parser.parse_args()
    print(render(run(args.n, args.seed)))
