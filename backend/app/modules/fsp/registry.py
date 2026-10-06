"""Реестр достижений ФСП.

API и структура данных ФСП на хакатоне не предоставляются, поэтому здесь зафиксирован минимальный
контракт (FspRegistry) и его мок. Для реальной интеграции достаточно реализовать fetch() и rank() поверх
API реестра. Принадлежность ФСП ID пользователю подтверждается входом через ФСП ID (см. idp.py).
"""

import random
from datetime import date, timedelta
from typing import Protocol

# Уровень соревнования → название для показа. На оценку уровень не влияет: по позиции ФСП все
# соревнования равно важны, считаются их число и результат.
LEVELS: dict[str, str] = {
    "regional": "Региональный",
    "district": "Федеральный округ",
    "federal": "Всероссийский",
}


class FspRegistry(Protocol):
    def fetch(self, fsp_id: str) -> list[dict] | None:
        """Достижения участника; пустой список — участник без результатов, None — такого ID нет."""

    def rank(self, fsp_id: str) -> str | None:
        """Спортивный разряд или звание участника; None — разряда нет."""


_EVENTS = {
    "regional": ["Чемпионат субъекта РФ", "Первенство субъекта РФ", "Кубок региона"],
    "district": ["Чемпионат федерального округа", "Первенство федерального округа"],
    "federal": ["Чемпионат России", "Кубок России", "Всероссийские соревнования"],
}
_DISCIPLINES = [
    "Программирование алгоритмическое",
    "Программирование продуктовое",
    "Программирование систем информационной безопасности",
    "Программирование робототехники",
    "Программирование беспилотных авиационных систем",
]
_MOCK_TODAY = date(2026, 9, 1)


class MockRegistry:
    """Детерминированный мок: один и тот же ID вида FSP-123456 всегда даёт один и тот же набор достижений.

    Номера, кратные 7, в «реестре» отсутствуют; у части участников достижений нет — оба случая нужны,
    чтобы показать обработку профиля без истории ФСП.
    """

    def fetch(self, fsp_id: str) -> list[dict] | None:
        number = int(fsp_id.split("-")[1])
        if number % 7 == 0:
            return None
        rng = random.Random(number)
        achievements = []
        for _ in range(rng.choice([0, 1, 2, 2, 3, 4, 6])):
            level = rng.choice(["regional", "regional", "district", "federal"])
            achievements.append(
                {
                    "event": rng.choice(_EVENTS[level]),
                    "discipline": rng.choice(_DISCIPLINES),
                    "level": level,
                    # None — участие без призового места.
                    "place": rng.choice([1, 2, 3, None, None]),
                    "date": (_MOCK_TODAY - timedelta(days=rng.randint(30, 1500))).isoformat(),
                    # Командный результат: личный вклад участника реестр не выделяет.
                    "team": rng.choice([True, False]),
                }
            )
        return sorted(achievements, key=lambda item: item["date"], reverse=True)

    def rank(self, fsp_id: str) -> str | None:
        # Разряд выводится из тех же результатов, поэтому согласован с ними.
        places = {(item["level"], item["place"]) for item in self.fetch(fsp_id) or [] if item["place"]}
        if any(level == "federal" for level, _ in places):
            return "Кандидат в мастера спорта"
        if any(level == "district" for level, _ in places):
            return "I спортивный разряд"
        return "II спортивный разряд" if places else None


registry: FspRegistry = MockRegistry()

# Результат соревнования: победа и призовое место. Уровень и дисциплина на вес не влияют.
_RESULT_WEIGHT = {1: 0.4, 2: 0.3, 3: 0.3}
# Участие без места весит мало, а сумма участий ограничена: профиль нельзя «набить» одними явками.
_PARTICIPATION_WEIGHT = 0.08
_PARTICIPATION_CAP = 0.2


def fsp_strength(achievements: list[dict], today: date) -> float:
    """Вклад достижений ФСП в силу профиля, 0…1: учитываются число соревнований, результат и давность.

    Отсутствие достижений даёт 0 — это не штраф, а отсутствие надбавки.
    """
    prizes = participation = 0.0
    for item in achievements:
        recent = (today - date.fromisoformat(item["date"])).days <= 730
        factor = 1.0 if recent else 0.6
        if item["place"] in _RESULT_WEIGHT:
            prizes += _RESULT_WEIGHT[item["place"]] * factor
        else:
            participation += _PARTICIPATION_WEIGHT * factor
    return min(1.0, prizes + min(_PARTICIPATION_CAP, participation))
