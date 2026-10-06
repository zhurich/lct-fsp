"""Полная валидация: тестирование и подбор. Печатает отчёт и при --out сохраняет его в файл.

Запуск: python -m scripts.validate [--n 2000] [--seed 1] [--out ../docs/validation_report.md]
"""

import argparse
from pathlib import Path

from scripts import validate_matching, validate_testing
from scripts import utf8_output

HEADER = """# Результаты валидации

Отчёт собран автоматически командой `python -m scripts.validate --n {n} --seed {seed}` из каталога `backend`
и воспроизводится при том же значении seed. Методика — в описаниях модулей `scripts/synth.py`,
`scripts/validate_testing.py` и `scripts/validate_matching.py`.

Данные синтетические: у каждого кандидата есть скрытые истинный уровень и реальные навыки, а платформа
видит только заявленные им грейд и стек и его ответы на задания. Все показатели — сравнение выводов
платформы со скрытой истиной. Ответы на задания генерируются по модели IRT, поэтому отчёт проверяет
алгоритмы теста и подбора и их устойчивость к ошибкам калибровки и нечестным резюме, но не заменяет
калибровку заданий на реальных ответах.

"""

if __name__ == "__main__":
    utf8_output()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=2000, help="число синтетических кандидатов в каждом расчёте")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, help="файл для сохранения отчёта в формате Markdown")
    args = parser.parse_args()

    report = (
        HEADER.format(n=args.n, seed=args.seed)
        + validate_testing.render(validate_testing.run(args.n, args.seed))
        + "\n"
        + validate_matching.render(validate_matching.run(args.n, args.seed))
    )
    print(report)
    if args.out:
        args.out.write_text(report, encoding="utf-8")
