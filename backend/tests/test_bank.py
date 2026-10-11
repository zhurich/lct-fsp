"""Проверка банка заданий без участия человека: ответы верны, генераторы воспроизводимы и разнообразны.

Ответ каждого задания пересчитывается здесь заново — исполнением того кода или выражения, которое видит
кандидат, — и сравнивается с вариантом, который банк считает верным.
"""

import hashlib
import os
import random
import re
import subprocess
import sys
from itertools import product
from pathlib import Path

from app.modules.assessment import bank

SEEDS = range(60)


def _instances(prefix: str):
    for item in bank.ITEMS.values():
        if item.id.startswith(prefix):
            for seed in SEEDS:
                yield item.id, seed, item.generate(random.Random(seed))


def _answer(question: bank.Question) -> str:
    return question.options[question.correct]


def _executed(code: str, variable: str):
    scope: dict = {}
    exec(code, scope)  # noqa: S102 — код из собственного банка заданий
    return scope[variable]


def test_code_reading_answers_match_executed_code():
    checked = 0
    for prefix, variable in (("common.loop.", "s"), ("common.containers.", "x")):
        for item_id, seed, question in _instances(prefix):
            assert _answer(question) == str(_executed(question.code, variable)), (item_id, seed)
            checked += 1
    for item_id, seed, question in _instances("common.recursion."):
        argument = re.search(r"f\((\d+)\)", question.text).group(1)
        assert _answer(question) == str(_executed(f"{question.code}\nresult = f({argument})", "result")), (item_id, seed)
        checked += 1
    assert checked == 12 * len(SEEDS)


def test_boolean_answers_match_truth_table():
    for item_id, seed, question in _instances("common.boolean."):
        names = re.search(r"переменные ([a-c, ]+) принимают", question.text).group(1).split(", ")
        true_rows = sum(
            bool(eval(question.code, {}, dict(zip(names, values))))  # noqa: S307 — выражение из банка заданий
            for values in product([True, False], repeat=len(names))
        )
        assert _answer(question) == str(true_rows), (item_id, seed)


def test_number_answers_match_evaluated_expression():
    for item_id, seed, question in _instances("common.numbers."):
        if binary := re.search(r"двоичное число ([01]+)", question.text):
            expected = int(binary.group(1), 2)
        elif hexadecimal := re.search(r"шестнадцатеричное число (0x[0-9A-F]+)", question.text):
            expected = int(hexadecimal.group(1), 16)
        elif expression := re.search(r"выражения (\(\d+ \^ \d+\) & \d+)\?", question.text):
            expected = eval(expression.group(1))  # noqa: S307 — выражение из банка заданий
        else:
            # Дополнительный код: те же биты, прочитанные как число без знака.
            value, bits = map(int, re.search(r"Число −(\d+) записано в (\d+)-битном", question.text).groups())
            expected = 2**bits - value
        assert _answer(question) == str(expected), (item_id, seed)


def test_parameterized_items_have_many_distinct_instances():
    # Пересказать «вопрос и ответ» бесполезно, только если у шаблона много разных экземпляров.
    counts = {}
    for item in bank.ITEMS.values():
        if item.scope == "common":
            instances = (item.generate(random.Random(seed)) for seed in range(1500))
            counts[item.id] = len({(q.text, q.code, _answer(q)) for q in instances})
    assert len(counts) == 28
    assert min(counts.values()) >= 30, min(counts, key=counts.get)
    assert sorted(counts.values())[len(counts) // 2] >= 100


_DIGEST = """
import hashlib, random
from app.modules.assessment import bank
digest = hashlib.sha256()
for item in bank.ITEMS.values():
    for seed in range(20):
        question = item.generate(random.Random(seed))
        digest.update(repr((item.id, question.text, question.code, question.options, question.correct)).encode())
print(digest.hexdigest())
"""


def test_generation_is_reproducible_across_processes():
    # Попытка хранит уже сгенерированное задание, но воспроизводимость нужна валидации: отчёт должен
    # повторяться при том же seed. Порядок обхода множеств зависит от PYTHONHASHSEED — проверяем, что
    # он не влияет на задания.
    backend = Path(__file__).resolve().parents[1]
    digests = set()
    for hash_seed in ("0", "1", "12345"):
        result = subprocess.run(
            [sys.executable, "-c", _DIGEST],
            cwd=backend,
            env={**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONPATH": str(backend)},
            capture_output=True,
            text=True,
            check=True,
        )
        digests.add(result.stdout.strip())
    assert len(digests) == 1 and len(next(iter(digests))) == hashlib.sha256().digest_size * 2
