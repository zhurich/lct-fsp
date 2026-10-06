"""Скрипты валидации запускаются и дают осмысленные показатели на малой выборке."""

import random

from scripts import synth, validate_matching, validate_testing


def test_testing_validation_runs_and_separates_levels():
    result = validate_testing.run(n=120, seed=3)
    assert result["accuracy"]["realistic"]["correlation"] > 0.6
    assert result["certification"]["over_two"] < 0.05
    # Угадать на middle и выше практически невозможно; утечка повышает шансы, но не гарантирует проход.
    assert result["guessing"]["middle"] < 0.05
    leaked = {row["leaked"]: row["pass_rate"] for row in result["leak"]}
    assert leaked[0] < leaked[200] < 1
    assert validate_testing.render(result).startswith("## Тестирование")


def test_matching_validation_beats_random_order():
    result = validate_matching.compare(n=400, seed=3, extra_queries=20, inflation=0.35)
    ranking = result["ranking"]
    assert ranking["platform"]["strict@10"] > 2 * ranking["random"]["strict@10"]
    assert ranking["platform"]["below@10"] < ranking["resume"]["below@10"]
    assert validate_matching.parser_quality()["specialization"] == 1.0


def test_certification_follows_platform_rules():
    rng = random.Random(5)
    params = synth.nominal_params()
    for _ in range(40):
        person = synth.make_person(rng)
        runs = synth.certify(person, params, rng)
        final = synth.category_of(runs)
        # Ни одно задание не повторяется между попытками, пока в банке хватает новых общих заданий.
        first_two = [item for run in runs[:2] for item in run.item_ids if item.startswith("common.")]
        assert len(first_two) == len(set(first_two))
        if final:
            assert final.theta >= -2
