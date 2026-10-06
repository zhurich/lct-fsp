import random
import statistics

import pytest

from app.modules.assessment import adaptive, bank
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
    positions = range(adaptive.TEST_LENGTH)
    specialized = sum(adaptive.is_specialized(position) for position in positions)
    assert len(bank.pool(specialization, True)) >= 2 * specialized
    assert len(bank.pool(specialization, False)) >= 2 * (adaptive.TEST_LENGTH - specialized)


def simulate(true_theta: float, grade: str, rng: random.Random) -> float:
    """Прогон теста для кандидата с известным уровнем: отвечает верно с вероятностью по модели."""
    theta, used, responses = adaptive.start_theta(grade), set(), []
    for position in range(adaptive.TEST_LENGTH):
        pool = [item for item in bank.pool("backend", adaptive.is_specialized(position)) if item.id not in used]
        item = adaptive.pick_item(pool, theta, {}, (), rng)
        used.add(item.id)
        responses.append((item.a, item.b, rng.random() < adaptive.probability(true_theta, item.a, item.b)))
        theta, _ = adaptive.estimate(responses)
    return theta


def test_estimate_separates_levels_and_does_not_depend_on_claimed_grade():
    rng = random.Random(7)
    means = {
        (true_theta, grade): statistics.mean(simulate(true_theta, grade, rng) for _ in range(150))
        for true_theta in (-1.5, 0.5, 1.5)
        for grade in ("junior", "senior")
    }
    for grade in ("junior", "senior"):
        assert means[-1.5, grade] < means[0.5, grade] - 1 < means[1.5, grade] - 1.5
    # Заявленный грейд задаёт только стартовые задания: оценка от него почти не зависит.
    for true_theta in (-1.5, 0.5, 1.5):
        assert abs(means[true_theta, "junior"] - means[true_theta, "senior"]) < 0.3
        assert abs(means[true_theta, "junior"] - true_theta) < 0.5


def test_score_scale_matches_grade_cuts():
    assert adaptive.grade_of(-2.5) is None
    assert [adaptive.grade_of(theta) for theta in (-2, -0.5, 0, 1.2)] == ["intern", "junior", "middle", "senior"]
    assert [adaptive.to_score(cut) for cut in adaptive.GRADE_CUTS.values()] == [0.2, 0.35, 0.5, 0.65]
