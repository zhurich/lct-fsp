import random
import statistics

import pytest

from app.modules.assessment import adaptive, bank, drift
from app.modules.reference.data import SPECIALIZATIONS


def test_every_item_generates_valid_and_varied_questions():
    for item in bank.ITEMS.values():
        variants = set()
        for seed in range(40):
            question = item.generate(random.Random(seed))
            assert len(question.options) == 4, item.id
            assert len(set(question.options)) == 4, item.id
            assert 0 <= question.correct < 4
            variants.add((question.text, question.code, tuple(question.options)))
        # Один и тот же вариант задания не достаётся всем подряд.
        assert len(variants) >= 4, item.id


@pytest.mark.parametrize("specialization", SPECIALIZATIONS)
def test_pools_are_large_enough_for_a_test(specialization):
    positions = range(adaptive.MAX_LENGTH)
    specialized = sum(adaptive.is_specialized(position) for position in positions)
    assert len(bank.pool(specialization, True)) >= 2 * specialized
    assert len(bank.pool(specialization, False)) >= 2 * (adaptive.MAX_LENGTH - specialized)


def simulate(true_theta: float, grade: str, rng: random.Random) -> tuple[float, int]:
    """Прогон теста для кандидата с известным уровнем: отвечает верно с вероятностью по модели.
    Возвращает оценку уровня и число заданий."""
    used, responses = set(), []
    while not adaptive.is_finished(responses, grade):
        pool = adaptive.position_pool("backend", len(responses), used)
        item = adaptive.pick_item(pool, adaptive.GRADE_CUTS[grade], {}, (), rng)
        used.add(item.id)
        responses.append((item.a, item.b, rng.random() < adaptive.probability(true_theta, item.a, item.b)))
    return adaptive.estimate(responses)[0], len(responses)


def test_decision_is_reliable_away_from_the_cut_and_borderline_candidates_get_more_items():
    rng = random.Random(7)
    runs = {
        (true_theta, grade): [simulate(true_theta, grade, rng) for _ in range(150)]
        for true_theta in (-1.5, 0.5, 1.5)
        for grade in ("junior", "senior")
    }
    mean = lambda key, index: statistics.mean(run[index] for run in runs[key])  # noqa: E731
    passed = lambda key: statistics.mean(run[0] >= adaptive.GRADE_CUTS[key[1]] for run in runs[key])  # noqa: E731
    for grade in ("junior", "senior"):
        assert mean((-1.5, grade), 0) < mean((0.5, grade), 0) - 0.8 < mean((1.5, grade), 0) - 1
    # Граница junior — −1, senior — +1: кандидат на грейд выше границы проходит, на грейд ниже — нет.
    assert passed((0.5, "junior")) > 0.95 and passed((1.5, "junior")) > 0.95
    assert passed((-1.5, "senior")) < 0.05 and passed((0.5, "senior")) < 0.25
    # Очевидный случай заканчивается на минимальной длине, пограничный получает дополнительные задания.
    assert mean((1.5, "junior"), 1) < adaptive.MIN_LENGTH + 1
    assert mean((-1.5, "junior"), 1) > mean((1.5, "junior"), 1) + 3
    assert all(adaptive.MIN_LENGTH <= length <= adaptive.MAX_LENGTH for key in runs for _, length in runs[key])


def test_drifted_items_are_replaced_by_parameterized_ones():
    own = {item.id for item in bank.pool("backend", True)}
    picked = adaptive.position_pool("backend", 1, set())
    assert {item.id for item in picked} == own
    # Снятые с выдачи задания не предлагаются, пока остаётся из чего выбирать…
    flagged = set(sorted(own)[:3])
    assert not {item.id for item in adaptive.position_pool("backend", 1, set(), flagged)} & flagged
    # …а когда профильных почти не осталось, позицию занимает общее задание с генерируемым условием.
    replaced = adaptive.position_pool("backend", 1, set(), own)
    assert replaced and all(item.scope == "common" for item in replaced)


def _attempt(theta_common: bool, special_correct: bool) -> list[dict]:
    """Попытка в том виде, в каком она хранится: шесть общих заданий и одно профильное."""
    common = [
        {"item_id": f"common.x.{index}", "a": 1.0, "b": 0.0, "correct": 0, "answer": 0 if theta_common else 1}
        for index in range(6)
    ]
    return [*common, {"item_id": "backend.0", "a": 1.0, "b": 1.0, "correct": 0, "answer": 0 if special_correct else 1}]


def test_drift_flags_item_solved_more_often_than_the_anchor_level_predicts():
    # Слабые по общим заданиям кандидаты поголовно решают трудное профильное задание — признак утечки.
    leaked = drift.analyze([_attempt(False, True) for _ in range(drift.MIN_SHOWN)])
    assert [(row.item_id, row.flagged) for row in leaked] == [("backend.0", True)]
    assert leaked[0].observed == 1 and leaked[0].expected < 0.5
    # Того же превышения на малом числе ответов для вывода недостаточно.
    assert not drift.analyze([_attempt(False, True) for _ in range(drift.MIN_SHOWN - 1)])[0].flagged
    # Сильные кандидаты решают его закономерно; общие задания под проверку не попадают.
    honest = drift.analyze([_attempt(True, index % 4 != 0) for index in range(60)])
    assert [(row.item_id, row.flagged) for row in honest] == [("backend.0", False)]


def test_score_scale_matches_grade_cuts():
    assert adaptive.grade_of(-2.5) is None
    assert [adaptive.grade_of(theta) for theta in (-2, -0.5, 0, 1.2)] == ["intern", "junior", "middle", "senior"]
    assert [adaptive.to_score(cut) for cut in adaptive.GRADE_CUTS.values()] == [0.2, 0.35, 0.5, 0.65]
