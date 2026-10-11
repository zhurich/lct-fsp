"""Валидация механики тестирования симуляцией кандидатов с известным уровнем.

Запуск: python -m scripts.validate_testing [--n 2000] [--seed 1]
        python -m scripts.validate_testing --db   # статистика заданий по реальным попыткам из базы

Что проверяется: точность оценки уровня и решения «прошёл / не прошёл», повторяемость результата,
разделение слабых и сильных, устойчивость к угадыванию и к утечке заданий (в том числе работа мониторинга
дрейфа, который снимает утёкшие задания с выдачи), равномерность показов.
Ответы кандидатов генерируются по модели IRT, поэтому симуляция проверяет алгоритм теста и его
чувствительность к ошибкам калибровки, но не качество формулировок самих заданий — для этого служит
режим --db, который считает те же показатели заданий по реальным ответам.
"""

import argparse
import random
import statistics
from collections import defaultdict

from app.modules.assessment import adaptive, bank, drift
from scripts import synth
from scripts.synth import GRADE_LIST, Person, TestRun
from scripts import utf8_output


def _share(flags) -> float:
    flags = list(flags)
    return sum(flags) / len(flags) if flags else 0.0


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _auc(lower: list[float], upper: list[float]) -> float:
    """Вероятность того, что случайный кандидат старшей группы получит балл выше, чем младшей."""
    wins = sum((high > low) + 0.5 * (high == low) for high in upper for low in lower)
    return wins / (len(upper) * len(lower))


def accuracy(people: list[Person], params: synth.TrueParams, rng: random.Random) -> dict:
    """Один тест на заявленный грейд для каждого: насколько оценка и решение совпадают с истиной."""
    runs = [
        synth.run_test(person.specialization, person.claimed_grade, synth.honest(person.theta, params, rng), rng)
        for person in people
    ]
    truth = [person.theta >= adaptive.GRADE_CUTS[person.claimed_grade] for person in people]
    errors = [run.theta - person.theta for run, person in zip(runs, people)]
    clear = [abs(person.theta - adaptive.GRADE_CUTS[person.claimed_grade]) >= 0.5 for person in people]
    estimated = [adaptive.grade_of(run.theta) for run in runs]
    position = lambda grade: GRADE_LIST.index(grade) if grade else -1  # noqa: E731
    return {
        "correlation": statistics.correlation([run.theta for run in runs], [person.theta for person in people]),
        "rmse": statistics.mean(error**2 for error in errors) ** 0.5,
        "bias": statistics.mean(errors),
        "se": statistics.mean(run.se for run in runs),
        "length": statistics.mean(len(run.questions) for run in runs),
        "shortest": _share(len(run.questions) == adaptive.MIN_LENGTH for run in runs),
        "longest": _share(len(run.questions) == adaptive.MAX_LENGTH for run in runs),
        "grade_exact": _share(grade == person.true_grade for grade, person in zip(estimated, people)),
        "grade_adjacent": _share(
            abs(position(grade) - position(person.true_grade)) <= 1 for grade, person in zip(estimated, people)
        ),
        "decision": _share(run.passed == real for run, real in zip(runs, truth)),
        "decision_clear": _share(run.passed == real for run, real, far in zip(runs, truth, clear) if far),
        "false_pass": _share(run.passed for run, real in zip(runs, truth) if not real),
        "false_fail": _share(not run.passed for run, real in zip(runs, truth) if real),
    }


def consistency(people: list[Person], params: synth.TrueParams, rng: random.Random) -> dict:
    """Два независимых прохождения одним и тем же кандидатом: совпадают ли решение и грейд."""
    first, second = [], []
    for person in people:
        for runs in (first, second):
            runs.append(
                synth.run_test(
                    person.specialization, person.claimed_grade, synth.honest(person.theta, params, rng), rng
                )
            )
    return {
        "reliability": statistics.correlation([run.theta for run in first], [run.theta for run in second]),
        "same_decision": _share(a.passed == b.passed for a, b in zip(first, second)),
        "same_grade": _share(adaptive.grade_of(a.theta) == adaptive.grade_of(b.theta) for a, b in zip(first, second)),
        "score_gap": statistics.mean(abs(a.theta - b.theta) for a, b in zip(first, second)) * 15,
    }


def certification(people: list[Person], params: synth.TrueParams, rng: random.Random) -> dict:
    """Итог пути «заявленный грейд → при провале ниже»: присвоенная категория против истинного грейда."""
    exposure: dict[str, int] = {}
    position = lambda grade: GRADE_LIST.index(grade) if grade else -1  # noqa: E731
    diffs, attempts, scores = [], [], defaultdict(list)
    for person in people:
        runs = synth.certify(person, params, rng, exposure)
        attempts.append(len(runs))
        final = synth.category_of(runs)
        assigned = final.grade if final else None
        diffs.append(position(assigned) - position(person.true_grade))
        if person.true_grade:
            scores[person.true_grade].append(runs[0].theta)
    tests = sum(attempts)
    rates = {scope: [] for scope in ("common", "specialized")}
    for item in bank.ITEMS.values():
        # Доля тестов, в которых встретилось задание; профильные считаются по тестам своей специализации.
        relevant = tests if item.scope == "common" else tests / 7
        rates["common" if item.scope == "common" else "specialized"].append(exposure.get(item.id, 0) / relevant)
    return {
        "exact": _share(diff == 0 for diff in diffs),
        "over": _share(diff > 0 for diff in diffs),
        "over_two": _share(diff > 1 for diff in diffs),
        "under": _share(diff < 0 for diff in diffs),
        "attempts": statistics.mean(attempts),
        "separation": {
            f"{low} → {high}": _auc(scores[low], scores[high]) for low, high in zip(GRADE_LIST, GRADE_LIST[1:])
        },
        "mean_score": {grade: adaptive.to_score(statistics.mean(scores[grade])) * 100 for grade in GRADE_LIST},
        "exposure": {scope: (statistics.median(values), max(values)) for scope, values in rates.items()},
    }


def guessing(params: synth.TrueParams, rng: random.Random, runs: int = 400) -> dict[str, float]:
    """Доля прошедших тест среди отвечающих наугад."""
    guess = lambda item, question: rng.randrange(4)  # noqa: E731
    return {grade: _share(synth.run_test("backend", grade, guess, rng).passed for _ in range(runs)) for grade in GRADE_LIST}


def variants(rng: random.Random, samples: int = 300) -> dict:
    """Разнообразие вариантов: сколько разных формулировок даёт задание и как часто два кандидата,
    получившие одно и то же задание, видят его в одинаковом виде."""
    result = {}
    for scope in ("common", "specialized"):
        distinct, collisions = [], []
        for item in bank.ITEMS.values():
            if (item.scope == "common") != (scope == "common"):
                continue
            generated = [item.generate(rng) for _ in range(samples)]
            keys = [(q.text, q.code, tuple(sorted(q.options))) for q in generated]
            distinct.append(len(set(keys)))
            collisions.append(_share(a == b for a, b in zip(keys[::2], keys[1::2])))
        result[scope] = (min(distinct), statistics.median(distinct), statistics.mean(collisions))
    return result


_LEAK_GRADE, _LEAK_SPECIALIZATION = "middle", "backend"
# Списывающий кандидат — на грейд ниже границы, на которую сдаёт.
_CHEATER_THETA = adaptive.GRADE_CUTS[_LEAK_GRADE] - 1.0


def _leaked_answers(tests: int, params: synth.TrueParams, rng: random.Random) -> dict[tuple, str]:
    """Что можно вынести из чужих тестов: условие задания → верный ответ."""
    memory: dict[tuple, str] = {}
    for _ in range(tests):
        donor = synth.run_test(_LEAK_SPECIALIZATION, _LEAK_GRADE, synth.honest(0.5, params, rng), rng)
        for question in donor.questions:
            memory[question["text"], question["code"]] = question["options"][question["correct"]]
    return memory


def _cheater(memory: dict[tuple, str], params: synth.TrueParams, rng: random.Random, recognized: list[bool]):
    """Заученный ответ помогает, только если задание пришло в том же виде (тот же текст и код) и верный
    вариант есть среди предложенных; иначе кандидат отвечает сам."""
    own = synth.honest(_CHEATER_THETA, params, rng)

    def respond(item, question):
        known = memory.get((question.text, question.code))
        recognized.append(known in question.options)
        return question.options.index(known) if known in question.options else own(item, question)

    return respond


def _cheater_runs(
    memory: dict[tuple, str], params: synth.TrueParams, rng: random.Random, runs: int, flagged=()
) -> tuple[list[TestRun], float]:
    recognized: list[bool] = []
    respond = _cheater(memory, params, rng, recognized)
    tests = [
        synth.run_test(_LEAK_SPECIALIZATION, _LEAK_GRADE, respond, rng, flagged=flagged) for _ in range(runs)
    ]
    return tests, _share(recognized)


def leak(params: synth.TrueParams, rng: random.Random, cheaters: int = 400) -> list[dict]:
    """Утечка: слабый кандидат заучил ответы из K чужих тестов на тот же грейд и специализацию.

    Для сравнения: при едином наборе заданий достаточно одного утёкшего теста, чтобы пройти с
    вероятностью 100%.
    """
    rows = []
    for leaked in (0, 10, 50, 200):
        tests, recognized = _cheater_runs(_leaked_answers(leaked, params, rng), params, rng, cheaters)
        rows.append({"leaked": leaked, "recognized": recognized, "pass_rate": _share(run.passed for run in tests)})
    return rows


def monitoring(people: list[Person], params: synth.TrueParams, rng: random.Random, cheaters: int = 400) -> dict:
    """Мониторинг дрейфа (drift.py) в двух режимах.

    Без утечки: каждый кандидат честно проходит один тест — сколько заданий снято с выдачи напрасно.
    С утечкой: к честным попыткам по одной специализации добавляются попытки списывающих, знающих ответы
    из 200 чужих тестов; мониторинг снимает задания, после чего прогоняется новая волна списывающих.
    """
    honest = [
        (
            person.specialization,
            synth.run_test(
                person.specialization, person.claimed_grade, synth.honest(person.theta, params, rng), rng
            ).questions,
        )
        for person in people
    ]
    clean = drift.analyze(questions for _, questions in honest)
    checked = [row for row in clean if row.shown >= drift.MIN_SHOWN]

    memory = _leaked_answers(200, params, rng)
    before, _ = _cheater_runs(memory, params, rng, cheaters)
    own = [questions for specialization, questions in honest if specialization == _LEAK_SPECIALIZATION]
    report = drift.analyze([*own, *(run.questions for run in before)])
    flagged = {row.item_id for row in report if row.flagged}
    after, recognized = _cheater_runs(memory, params, rng, cheaters, flagged)
    return {
        "checked": len(checked),
        "false_flags": sum(row.flagged for row in checked),
        "honest_tests": len(own),
        "cheater_tests": cheaters,
        "flagged": len(flagged),
        "pool": len(bank.pool(_LEAK_SPECIALIZATION, True)),
        "pass_before": _share(run.passed for run in before),
        "pass_after": _share(run.passed for run in after),
        "recognized_after": recognized,
    }


def item_stats(attempts: list[list[dict]], thetas: list[float]) -> list[dict]:
    """Показатели заданий по ответам: доля верных и индекс дискриминации D — разность долей верных
    ответов между сильной (верхние 27% по итоговой оценке) и слабой (нижние 27%) группами."""
    ordered = sorted(thetas)
    low_cut, high_cut = ordered[int(len(ordered) * 0.27)], ordered[int(len(ordered) * 0.73)]
    stats: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for questions, theta in zip(attempts, thetas):
        group = "low" if theta <= low_cut else "high" if theta >= high_cut else "mid"
        for question in questions:
            if "answer" in question:
                stats[question["item_id"]][group].append(question["answer"] == question["correct"])
    rows = []
    for item_id, groups in sorted(stats.items()):
        answers = [flag for flags in groups.values() for flag in flags]
        both = groups["low"] and groups["high"]
        rows.append(
            {
                "item": item_id,
                "shown": len(answers),
                "correct": _share(answers),
                "discrimination": _share(groups["high"]) - _share(groups["low"]) if both else None,
            }
        )
    return rows


def run(n: int = 2000, seed: int = 1) -> dict:
    rng = random.Random(seed)
    people = [synth.make_person(rng) for _ in range(n)]
    ideal, realistic = synth.nominal_params(), synth.perturbed_params(rng)
    return {
        "n": n,
        "accuracy": {"ideal": accuracy(people, ideal, rng), "realistic": accuracy(people, realistic, rng)},
        "consistency": consistency(people, realistic, rng),
        "certification": certification(people, realistic, rng),
        "guessing": guessing(realistic, rng),
        "variants": variants(rng),
        "leak": leak(realistic, rng),
        "monitoring": monitoring(people, realistic, rng),
    }


def render(result: dict) -> str:
    ideal, real = result["accuracy"]["ideal"], result["accuracy"]["realistic"]
    again, cert, watch = result["consistency"], result["certification"], result["monitoring"]
    lines = [
        "## Тестирование",
        "",
        f"Симуляция {result['n']} кандидатов с известным уровнем. «Идеальная калибровка» — истинная сложность "
        "заданий равна назначенной; «реалистичная» — отличается от неё (сдвиг сложности со стандартным "
        "отклонением 0,4 грейда, разброс различающей способности ±25%). Остальные показатели — для реалистичной.",
        "",
        f"Тест переменной длины: от {adaptive.MIN_LENGTH} до {adaptive.MAX_LENGTH} заданий, в среднем "
        f"{real['length']:.1f}. На наименьшей длине заканчивают {_pct(real['shortest'])} тестов (результат "
        f"очевиден), до наибольшей доходят {_pct(real['longest'])} (кандидат у самой границы грейда).",
        "",
        "### Точность оценки (один тест на заявленный грейд)",
        "",
        "| Показатель | Идеальная калибровка | Реалистичная |",
        "|---|---|---|",
    ]
    rows = [
        ("Корреляция оценки с истинным уровнем", "correlation", "{:.2f}"),
        ("Ошибка оценки (RMSE), в грейдах", "rmse", "{:.2f}"),
        ("Смещение оценки, в грейдах", "bias", "{:+.2f}"),
        ("Грейд по результату совпал с истинным", "grade_exact", "pct"),
        ("…или отличается не более чем на один", "grade_adjacent", "pct"),
        ("Верное решение «прошёл / не прошёл»", "decision", "pct"),
        ("…для кандидатов не ближе 0,5 грейда к границе", "decision_clear", "pct"),
        ("Прошли, хотя уровень ниже заявленного", "false_pass", "pct"),
        ("Не прошли, хотя уровень соответствует", "false_fail", "pct"),
    ]
    for label, key, fmt in rows:
        show = _pct if fmt == "pct" else fmt.format
        lines.append(f"| {label} | {show(ideal[key])} | {show(real[key])} |")
    lines += [
        "",
        "### Повторяемость (два независимых прохождения)",
        "",
        f"- Корреляция оценок двух прохождений (надёжность): {again['reliability']:.2f}",
        f"- Одинаковое решение «прошёл / не прошёл»: {_pct(again['same_decision'])}",
        f"- Одинаковый грейд по результату: {_pct(again['same_grade'])}",
        f"- Среднее расхождение балла: {again['score_gap']:.0f} из 100",
        "",
        "### Итог категоризации (заявленный грейд; при провале — грейд ниже, при уверенном результате — выше)",
        "",
        f"- Категория совпала с истинным грейдом: {_pct(cert['exact'])}",
        f"- Категория выше истинного грейда: {_pct(cert['over'])} (на два грейда и больше — {_pct(cert['over_two'])})",
        f"- Категория ниже истинного грейда или не присвоена: {_pct(cert['under'])}",
        f"- Среднее число попыток на кандидата: {cert['attempts']:.2f}",
        "",
        "### Разделение слабых и сильных",
        "",
        "Средний балл теста по истинному грейду: "
        + ", ".join(f"{grade} — {score:.0f}" for grade, score in cert["mean_score"].items())
        + ".",
        "",
        "Вероятность того, что кандидат старшего грейда наберёт больше кандидата соседнего младшего (AUC): "
        + ", ".join(f"{pair} — {value:.2f}" for pair, value in cert["separation"].items())
        + ".",
        "",
        "### Угадывание",
        "",
        "Доля прошедших среди отвечающих наугад: "
        + ", ".join(f"{grade} — {_pct(rate)}" for grade, rate in result["guessing"].items())
        + ".",
        "",
        "### Устойчивость к распространению заданий",
        "",
        "| Задания | Разных вариантов из 300 выдач (мин. / медиана) | Два кандидата видят задание одинаково |",
        "|---|---|---|",
    ]
    for scope, label in (("common", "Общие (параметризованные)"), ("specialized", "Профильные")):
        low, median, collision = result["variants"][scope]
        lines.append(f"| {label} | {low} / {median:.0f} | {_pct(collision)} |")
    lines += [
        "",
        "Слабый кандидат (на грейд ниже границы) заучил ответы из K чужих тестов на тот же грейд:",
        "",
        "| Утёкших тестов | Узнано заданий в своём тесте | Прошли тест |",
        "|---|---|---|",
    ]
    for row in result["leak"]:
        lines.append(f"| {row['leaked']} | {_pct(row['recognized'])} | {_pct(row['pass_rate'])} |")
    lines += [
        "",
        "Для сравнения: при едином наборе заданий одного утёкшего теста достаточно, чтобы пройти наверняка.",
        "",
        "### Мониторинг дрейфа",
        "",
        "Задание снимается с выдачи, если его решают заметно чаще, чем следует из уровня кандидатов по "
        f"общим (генерируемым) заданиям: не меньше {drift.MIN_SHOWN} ответов, превышение больше "
        f"{drift.EXCESS * 100:.0f} п.п. и больше {drift.Z_SCORE} стандартного отклонения.",
        "",
        f"- Без утечки: из {watch['checked']} профильных заданий с достаточным числом ответов снято напрасно — "
        f"{watch['false_flags']}",
        f"- С утечкой 200 тестов ({watch['honest_tests']} честных попыток и {watch['cheater_tests']} попыток "
        f"списывающих по одной специализации): снято {watch['flagged']} из {watch['pool']} профильных заданий",
        f"- Списывающие проходят тест: до мониторинга — {_pct(watch['pass_before'])}, после — "
        f"{_pct(watch['pass_after'])} (узнают {_pct(watch['recognized_after'])} заданий)",
        "",
        "### Показы заданий",
        "",
    ]
    for scope, label in (("common", "общее"), ("specialized", "профильное")):
        median, highest = cert["exposure"][scope]
        lines.append(f"- {label.capitalize()} задание встречается в {_pct(median)} тестов (медиана), максимум — {_pct(highest)}")
    return "\n".join(lines) + "\n"


def from_db() -> str:
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.assessment.models import Assessment

    with SessionLocal() as db:
        finished = db.scalars(select(Assessment).where(Assessment.finished_at.is_not(None))).all()
    complete = [attempt for attempt in finished if adaptive.is_complete(attempt.questions)]
    if len(complete) < 20:
        return f"Завершённых попыток в базе: {len(complete)} — для статистики заданий нужно хотя бы 20."
    rows = item_stats([attempt.questions for attempt in complete], [attempt.theta for attempt in complete])
    # Ожидаемая решаемость и признак дрейфа считаются только для профильных заданий (см. drift.py).
    drifted = {row.item_id: row for row in drift.analyze(attempt.questions for attempt in complete)}
    lines = [
        f"Попыток: {len(complete)}",
        "",
        "| Задание | Показов | Верных | Ожидалось | Дискриминация D | Дрейф |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        d = "—" if row["discrimination"] is None else f"{row['discrimination']:+.2f}"
        watch = drifted.get(row["item"])
        expected = _pct(watch.expected) if watch else "—"
        mark = "снять с выдачи" if watch and watch.flagged else ""
        lines.append(f"| {row['item']} | {row['shown']} | {_pct(row['correct'])} | {expected} | {d} | {mark} |")
    return "\n".join(lines)


if __name__ == "__main__":
    utf8_output()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=2000, help="число синтетических кандидатов")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--db", action="store_true", help="статистика заданий по реальным попыткам из базы")
    args = parser.parse_args()
    print(from_db() if args.db else render(run(args.n, args.seed)))
