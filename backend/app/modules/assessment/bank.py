"""Банк заданий: параметризованные шаблоны с заранее заданными параметрами IRT.

Задание банка (Item) — не готовый текст, а генератор: числа, структура кода и набор вариантов ответа
выбираются случайно при каждой выдаче. Поэтому пересказ «вопроса и ответа» другому кандидату бесполезен,
а сложность остаётся сопоставимой: она закреплена за шаблоном и уровнем (параметр b), а не за конкретными
числами. Общие шаблоны проверяют базовое инженерное мышление, профильные — специализацию: это ситуационные
вопросы (bank_spec.py) и задания на термины (bank_glossary.py).
"""

import random
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from itertools import product

from app.modules.assessment.bank_glossary import GLOSSARIES
from app.modules.assessment.bank_spec import SPEC_QUESTIONS


@dataclass
class Question:
    text: str
    options: list[str]
    correct: int
    code: str | None = None


@dataclass(frozen=True)
class Item:
    id: str
    # "common" либо код специализации.
    scope: str
    # Параметры IRT: различающая способность и сложность на шкале θ (см. adaptive.py).
    a: float
    b: float
    generate: Callable[[random.Random], Question]


def _question(rng: random.Random, text: str, answer, wrong, code: str | None = None) -> Question:
    """Собирает задание с четырьмя вариантами: верный ответ и первые три отличных от него из wrong."""
    options = [str(answer)]
    for value in wrong:
        if str(value) not in options:
            options.append(str(value))
        if len(options) == 4:
            break
    rng.shuffle(options)
    return Question(text=text, options=options, correct=options.index(str(answer)), code=code)


def _numeric(rng: random.Random, text: str, answer: int, traps=(), code: str | None = None) -> Question:
    """Числовое задание: сначала «ловушки» (типичные ошибки), затем соседние с ответом значения."""
    near = [answer + delta for delta in (-3, -2, -1, 1, 2, 3) if answer + delta >= 0]
    rng.shuffle(near)
    return _question(rng, text, answer, [trap for trap in traps if trap >= 0] + near, code)


def _run(code: str, variable: str):
    """Выполняет код задания и возвращает значение переменной.

    Ответ вычисляется из того же текста, который видит кандидат, поэтому не может с ним разойтись.
    Код берётся только из шаблонов этого модуля, пользовательский ввод сюда не попадает.
    """
    scope: dict = {"deque": deque}
    exec(code, scope)
    return scope[variable]


def _loop(rng: random.Random, level: int) -> Question:
    if level == 0:
        n, start, step = rng.randint(5, 12), rng.randint(0, 3), rng.choice([1, 1, 2])
        loop = f"range({start}, {n + 1})" if step == 1 else f"range({start}, {n + 1}, {step})"
        code = f"s = 0\nfor i in {loop}:\n    s += i"
        traps = [sum(range(start, n, step)), n]
    elif level == 1:
        n, k = rng.randint(8, 24), rng.choice([2, 3, 4, 5])
        code = f"s = 0\nfor i in range(1, {n + 1}):\n    if i % {k} == 0:\n        s += i"
        traps = [n // k, n * (n + 1) // 2]
    elif level == 2:
        n, k = rng.randint(12, 30), rng.choice([3, 4, 5, 7])
        code = (
            f"s = 0\nfor i in range(1, {n + 1}):\n    if i % {k} == 0:\n        s += i\n"
            f"    elif i % 2 == 0:\n        s -= 1"
        )
        traps = [sum(i for i in range(1, n + 1) if i % k == 0), sum(i for i in range(1, n + 1) if i % k == 0) - n // 2]
    else:
        n, k = rng.randint(5, 11), rng.choice([2, 3, 4, 5, 6])
        code = (
            f"s = 0\nfor i in range(1, {n + 1}):\n    for j in range(i, {n + 1}):\n"
            f"        if (i * j) % {k} == 0:\n            s += 1"
        )
        traps = [sum(1 for i in range(1, n + 1) for j in range(1, n + 1) if (i * j) % k == 0), n * (n + 1) // 2]
    return _numeric(rng, "Чему равно значение s после выполнения кода?", _run(code, "s"), traps, code)


_COMPLEXITIES = ["O(1)", "O(log n)", "O(log² n)", "O(n)", "O(n log n)", "O(n²)", "O(2ⁿ)"]
# Структуры по уровням: (внешний цикл, тело) → сложность. Внешний цикл: n — линейный, log — с умножением
# счётчика, half — с делением. Тело: 1 — одна операция, c — цикл до константы, n — линейный цикл,
# log — логарифмический, i — цикл до счётчика внешнего.
_LOOP_STRUCTURES: list[list[tuple[str | None, str, str]]] = [
    [(None, "c", "O(1)"), ("n", "1", "O(n)"), ("n", "c", "O(n)"), ("n", "n", "O(n²)")],
    [("log", "1", "O(log n)"), ("half", "1", "O(log n)"), ("log", "c", "O(log n)"), ("n", "i", "O(n²)")],
    [
        ("n", "log", "O(n log n)"),
        ("log", "n", "O(n log n)"),
        ("half", "n", "O(n log n)"),
        ("log", "log", "O(log² n)"),
        # Внутренний цикл идёт до счётчика, который растёт или убывает геометрически: сумма — O(n).
        ("log", "i", "O(n)"),
        ("half", "i", "O(n)"),
    ],
]
# Рекурсивные функции: тело после базового случая → сложность. {f} — имя функции, {c} — константа.
_RECURSIONS = [
    ("return {f}(n - 1) + {f}(n - 1)", "O(2ⁿ)"),
    ("return {f}(n // 2) + {f}(n // 2)", "O(n)"),
    ("return {f}(n // 2) + {c}", "O(log n)"),
    ("return {f}(n - 1) + {c}", "O(n)"),
    ("{acc} = 0\n    for i in range(n):\n        {acc} += 1\n    return {f}(n // 2) + {f}(n // 2)", "O(n log n)"),
    ("{acc} = 0\n    for i in range(n):\n        {acc} += 1\n    return {f}(n - 1)", "O(n²)"),
]


def _indent(code: str) -> str:
    return "\n".join("    " + line for line in code.split("\n"))


def _complexity(rng: random.Random, level: int) -> Question:
    """Фрагмент собирается из структуры и случайных имён и констант: дословно заучить его нельзя,
    а ответ определяется только структурой."""
    outer_var, inner_var = rng.sample(["i", "j", "k", "p", "q"], 2)
    acc = rng.choice(["cnt", "total", "ops", "steps"])
    c = rng.randint(2, 5)
    if level == 3:
        body, answer = rng.choice(_RECURSIONS)
        name = rng.choice(["f", "g", "solve", "walk"])
        code = f"def {name}(n):\n    if n <= 1:\n        return 1\n    " + body.format(f=name, c=c, acc=acc)
    else:
        outer, inner, answer = rng.choice(_LOOP_STRUCTURES[level])
        body = {
            "1": f"{acc} += 1",
            "c": f"for {inner_var} in range({c * rng.randint(2, 20)}):\n    {acc} += 1",
            "n": f"for {inner_var} in range(n):\n    {acc} += 1",
            "log": f"{inner_var} = 1\nwhile {inner_var} < n:\n    {acc} += 1\n    {inner_var} *= {rng.randint(2, 4)}",
            "i": f"for {inner_var} in range({outer_var}):\n    {acc} += 1",
        }[inner]
        code = {
            None: body,
            "n": f"for {outer_var} in range(n):\n{_indent(body)}",
            "log": f"{outer_var} = 1\nwhile {outer_var} < n:\n{_indent(body)}\n    {outer_var} *= {c}",
            "half": f"{outer_var} = n\nwhile {outer_var} > 0:\n{_indent(body)}\n    {outer_var} //= {c}",
        }[outer]
        # Счётчик объявлен в самом фрагменте: показанный код выполняется как есть, если задать n.
        code = f"{acc} = 0\n{code}"
    wrong = [item for item in _COMPLEXITIES if item != answer]
    rng.shuffle(wrong)
    return _question(rng, "Какова временная сложность фрагмента (n — размер входных данных)?", answer, wrong, code)


def _numbers(rng: random.Random, level: int) -> Question:
    if level == 0:
        x = rng.randint(5, 127)
        return _numeric(rng, f"Чему равно двоичное число {x:b} в десятичной системе?", x, [x * 2, x // 2])
    if level == 1:
        x = rng.randint(32, 255)
        return _numeric(
            rng,
            f"Чему равно шестнадцатеричное число 0x{x:X} в десятичной системе?",
            x,
            [(x >> 4) * 10 + (x & 15), (x >> 4) + (x & 15)],
        )
    if level == 2:
        a, b, mask = rng.randint(16, 63), rng.randint(16, 63), rng.choice([7, 15, 31])
        return _numeric(
            rng,
            f"Чему равно значение выражения ({a} ^ {b}) & {mask}? (^ — побитовое исключающее ИЛИ, & — побитовое И)",
            (a ^ b) & mask,
            [(a | b) & mask, (a & b) & mask, a ^ b],
        )
    k = rng.randint(2, 100)
    return _numeric(
        rng,
        f"Число −{k} записано в 8-битном дополнительном коде. Чему равны те же 8 бит, прочитанные как беззнаковое число?",
        256 - k,
        [255 - k, 128 + k, 128 - k],
    )


def _search(rng: random.Random, level: int) -> Question:
    if level == 0:
        n = rng.randint(20, 90)
        return _numeric(
            rng,
            f"В неотсортированном массиве из {n} элементов значение ищут перебором. "
            "Сколько элементов придётся проверить в худшем случае?",
            n,
            [n // 2, n - 1, n.bit_length()],
        )
    if level == 3:
        n = rng.randint(300, 5000)
        steps = next(k for k in range(1, 20) if 3**k >= n)
        return _numeric(
            rng,
            f"Диапазон из {n} значений за один шаг делят на три равные части и узнают, в какой из них искомое. "
            "Какого наименьшего числа шагов гарантированно хватит, чтобы найти значение?",
            steps,
            [n.bit_length(), n // 3],
        )
    n = rng.randint(100, 1000) if level == 1 else rng.randint(10_000, 1_000_000)
    return _numeric(
        rng,
        f"Бинарный поиск по отсортированному массиву из {n} элементов. "
        "Сколько элементов придётся сравнить с искомым в худшем случае?",
        n.bit_length(),
        [n // 2, n.bit_length() * 2],
    )


def _containers(rng: random.Random, level: int) -> Question:
    """Стек (уровень 0), очередь (1), двусторонняя очередь (2) и она же со сдвигом (3)."""
    pushes = ["append", "appendleft"] if level >= 2 else ["append"]
    pops = [["pop()"], ["pop(0)"], ["pop()", "popleft()"], ["pop()", "popleft()"]][level]
    values = rng.sample(range(1, 30), 4 + level)
    lines = ["from collections import deque", "d = deque()"] if level >= 2 else ["d = []"]
    size = 0
    for index, value in enumerate(values):
        lines.append(f"d.{rng.choice(pushes)}({value})")
        size += 1
        if size >= 2 and index < len(values) - 1 and rng.random() < 0.5:
            lines.append(f"x = d.{rng.choice(pops)}")
            size -= 1
    if level == 3:
        lines.append(f"d.rotate({rng.randint(1, 2)})")
    lines.append(f"x = d.{rng.choice(pops)}")
    code = "\n".join(lines)
    answer = _run(code, "x")
    wrong = [value for value in values if value != answer]
    rng.shuffle(wrong)
    return _question(rng, "Чему равно x после выполнения кода?", answer, wrong, code)


def _recursion(rng: random.Random, level: int) -> Question:
    c = rng.randint(1, 4)
    if level == 0:
        n = rng.randint(3, 6)
        body = f"    if n == 0:\n        return {rng.randint(1, 5)}\n    return f(n - 1) + {c}"
    elif level == 1:
        n = rng.randint(3, 5)
        body = f"    if n == 0:\n        return {rng.randint(0, 3)}\n    return {rng.choice([2, 3])} * f(n - 1) + {c}"
    elif level == 2:
        n = rng.randint(5, 8)
        body = f"    if n < 2:\n        return n + {c}\n    return f(n - 1) + f(n - 2) + {rng.randint(0, 2)}"
    else:
        n = rng.randint(8, 15)
        body = f"    if n <= 1:\n        return {rng.randint(1, 3)}\n    return f(n // 2) + f(n - 2) + {c}"
    code = f"def f(n):\n{body}"
    answer = _run(f"{code}\nresult = f({n})", "result")
    return _numeric(rng, f"Что вернёт вызов f({n})?", answer, [_run(f"{code}\nresult = f({n - 1})", "result")], code)


# Уровень → (число переменных, число бинарных операций, допустимые операции).
_BOOLEAN_LEVELS = [
    (2, 1, ["and", "or"]),
    (2, 2, ["and", "or", "!="]),
    (3, 2, ["and", "or", "!="]),
    (3, 4, ["and", "or", "!=", "=="]),
]


def _boolean_expression(rng: random.Random, names: list[str], operations: int, operators: list[str]) -> str:
    """Случайное выражение, в котором участвует каждая переменная; вложенность задаётся скобками."""
    leaves = names + [rng.choice(names) for _ in range(operations + 1 - len(names))]
    rng.shuffle(leaves)
    leaves = [f"(not {name})" if rng.random() < 0.35 else name for name in leaves]
    expression, compound = leaves[0], False
    for leaf in leaves[1:]:
        part = f"({expression})" if compound else expression
        expression = rng.choice([f"{part} {rng.choice(operators)} {leaf}", f"{leaf} {rng.choice(operators)} {part}"])
        compound = True
    return f"not ({expression})" if rng.random() < 0.2 else expression


def _boolean(rng: random.Random, level: int) -> Question:
    count, operations, operators = _BOOLEAN_LEVELS[level]
    names = ["a", "b", "c"][:count]
    combinations = list(product([False, True], repeat=count))
    while True:
        expression = _boolean_expression(rng, names, max(operations, count - 1), operators)
        answer = sum(bool(eval(expression, dict(zip(names, values)))) for values in combinations)
        # Тождественно истинные и ложные выражения не берутся: ответ на них угадывается без разбора.
        if 0 < answer < len(combinations):
            break
    wrong = [value for value in range(len(combinations) + 1) if value != answer]
    rng.shuffle(wrong)
    return _question(
        rng,
        f"Логические переменные {', '.join(names)} принимают значения True и False. "
        f"Для скольких наборов значений из {len(combinations)} возможных выражение истинно?",
        answer,
        wrong,
        expression,
    )


def _statement(rng: random.Random, text: str, right: list[str], wrong: list[str]) -> Question:
    return _question(rng, text, rng.choice(right), rng.sample(wrong, 3))


def _glossary(rng: random.Random, pairs: list[tuple[str, str]], reverse: bool) -> Question:
    """Термин → определение либо определение → термин; неверные варианты — из того же глоссария."""
    (term, definition), *others = rng.sample(pairs, 4)
    if reverse:
        return _question(rng, f"Как называется: {definition}?", term, [other for other, _ in others])
    return _question(rng, f"Что означает «{term}»?", definition, [other for _, other in others])


# Поправка сложности шаблона относительно базовой сложности уровня (уровень 0…3 → b = −1,5…+1,5).
_COMMON_TEMPLATES = {
    "loop": (_loop, 0.0),
    "complexity": (_complexity, 0.2),
    "numbers": (_numbers, -0.1),
    "search": (_search, 0.0),
    "containers": (_containers, -0.2),
    "recursion": (_recursion, 0.1),
    "boolean": (_boolean, 0.1),
}


def _build_items() -> dict[str, Item]:
    items = [
        Item(f"common.{name}.{level}", "common", 1.2, level - 1.5 + shift, partial(template, level=level))
        for name, (template, shift) in _COMMON_TEMPLATES.items()
        for level in range(4)
    ]
    for specialization, questions in SPEC_QUESTIONS.items():
        for number, (level, text, right, wrong) in enumerate(questions):
            # Задания одного уровня разводятся по сложности, чтобы не давать одинаковую информацию.
            shift = 0.2 if number % 2 else -0.2
            items.append(
                Item(
                    f"{specialization}.{number}",
                    specialization,
                    1.0,
                    level - 1.5 + shift,
                    partial(_statement, text=text, right=right, wrong=wrong),
                )
            )
        # Задания на термины: базовый глоссарий — уровень junior, продвинутый — middle и выше.
        # Обратная форма (по определению назвать термин) немного сложнее прямой.
        for family, difficulty in (("basic", -1.0), ("advanced", 0.5)):
            for reverse in (False, True):
                items.append(
                    Item(
                        f"{specialization}.terms.{family}.{'name' if reverse else 'meaning'}",
                        specialization,
                        1.0,
                        difficulty + 0.3 * reverse,
                        partial(_glossary, pairs=GLOSSARIES[specialization][family], reverse=reverse),
                    )
                )
    return {item.id: item for item in items}


ITEMS = _build_items()


def pool(specialization: str, specialized: bool) -> list[Item]:
    """Профильные задания специализации либо общие для всех."""
    scope = specialization if specialized else "common"
    return [item for item in ITEMS.values() if item.scope == scope]
