"""Разбор потребности работодателя из свободного текста в структуру.

Сейчас разбор выполняется правилами и словарями: это воспроизводимо, объяснимо и не требует внешних
сервисов. Точка расширения — функция parse_need: её можно заменить вызовом языковой модели, возвращающей
тот же ParsedNeed; правила при этом остаются запасным вариантом и проверкой результата модели.
"""

import re
from dataclasses import dataclass, field

from app.modules.reference.data import GRADES, SPECIALIZATIONS, WORK_FORMATS
from app.modules.reference.skills import SKILLS, extract_skills


@dataclass
class ParsedNeed:
    specialization: str | None = None
    grade: str | None = None
    stack: list[str] = field(default_factory=list)
    work_formats: list[str] = field(default_factory=list)
    salary_from: int | None = None
    salary_to: int | None = None
    # Что и по каким признакам распознано — показывается работодателю.
    notes: list[str] = field(default_factory=list)


# Основы слов, по которым распознаётся специализация. «Аналитик данных» относится к data, поэтому
# общий признак «аналитик» у analyst проверяется с исключением.
_SPECIALIZATION_HINTS: dict[str, str] = {
    "backend": r"бэк[- ]?енд|бек[- ]?енд|back[- ]?end|серверн\w+ (?:разработ|част)",
    "frontend": r"фронт[- ]?енд|front[- ]?end|верстальщик|вёрстк|верстк",
    "mobile": r"мобильн|mobile|ios[- ]разработ|android[- ]разработ",
    "qa": r"тестировщик|\bqa\b|автотест|тестировани",
    "devops": r"devops|девопс|\bsre\b|инфраструктур|системн\w+ администратор",
    "data": r"data scien|дата[- ]?сайент|ml[- ]инженер|машинн\w+ обучени|data engineer|аналитик\w* данных|\bds\b",
    "analyst": r"системн\w+ аналитик|бизнес[- ]аналитик|аналитик(?!\w* данных)|сбор\w* требовани",
}
_FULLSTACK = r"фулл?[- ]?стек|full[- ]?stack"

GRADE_HINTS: dict[str, str] = {
    "intern": r"стаж[её]р|intern|trainee|без опыта",
    "junior": r"джун|junior|начинающ",
    "middle": r"мидл|миддл|middle",
    "senior": r"сеньор|синьор|senior|ведущ|тимлид|team ?lead|\blead\b|старш\w+ разработ",
}
_YEARS = re.compile(
    r"(?:от|более|не менее|минимум|опыт\w*(?:\s+работы)?)\s+(\d+)(?:\s*(?:до|[-–—])\s*\d+)?(?:[- ]?х)?\s*(?:лет|года|год)"
    r"|(\d+)\s*\+\s*(?:лет|года|год)"
)

# Грейд, названный как объект работы («наставничество junior-разработчиков», «ревью кода джунов»),
# описывает обязанности, а не требуемый уровень кандидата.
_JUNIOR_COLLEAGUE = r"(?:стаж[её]р\w*|intern\w*|trainee\w*|джун\w*|junior\w*|мидл\w*|миддл\w*|middle\w*)(?:[- ]разработчик\w*)?"
_GRADE_AS_OBJECT = re.compile(
    r"(?:наставни\w+|ментор\w*|обуч\w+|онбординг\w*|руковод\w+|управл\w+|курир\w+|ревью(?:\s+кода)?|развити\w+"
    r"|помо(?:щь|гать)|поддержк\w+|mentor\w*|coach\w*)"
    r"(?:\s+(?:и|для|над|с|команд\w+|групп\w+|наших|своих|младших|новых|of|for))*\s+"
    rf"{_JUNIOR_COLLEAGUE}(?:\s*(?:,|/|и|или|and)\s*{_JUNIOR_COLLEAGUE})*"
)

_FORMAT_HINTS: dict[str, str] = {
    "remote": r"удал[её]нн\w*|удал[её]нк\w*|remote",
    "office": r"офис\w*|office",
    "hybrid": r"гибрид\w*|hybrid",
}
# Отрицание формата: «не удалённая», «без удалёнки», «удалённая работа невозможна», «удалёнка не предусмотрена».
_NEGATION_BEFORE = r"(?:\bне|\bбез|\bнет|\bкроме|\bисключая|\bno|\bnot)\s+(?:\w+\s+){{0,2}}?(?:{fmt})"
_NEGATION_AFTER = (
    r"(?:{fmt})(?:\s+(?:работ\w+|формат\w*|режим\w*))?\s+(?:\w+\s+)?"
    r"(?:невозможн\w+|недоступн\w+|исключ\w+|отсутству\w+|запрещ\w+|нет\b"
    r"|не\s+(?:предусмотр\w+|рассматрива\w+|возможн\w+|предлага\w+|предполага\w+|подходит|доступн\w+))"
)
_ONLY = r"(?:только|исключительно|строго|only)\s+(?:в\s+|из\s+|на\s+)?(?:{fmt})"

_AMOUNT = r"(\d[\d ]*)\s*(тыс\.?|т\.\s?р\.?|k|к)?"
_SALARY_RANGE = re.compile(
    rf"(?:от\s+)?{_AMOUNT}\s*(?:руб\w*\.?|₽)?\s*(?:до|[-–—])\s*{_AMOUNT}(?!\s*(?:лет|года|год|%))", re.IGNORECASE
)
_SALARY_WORD = r"(?:зарплат\w+|з/п|зп|оклад\w*|вилк\w+|бюджет\w*|доход\w*)"
_SALARY_FROM = re.compile(rf"{_SALARY_WORD}\D{{0,15}}от\s+{_AMOUNT}", re.IGNORECASE)
# Только верхняя граница: «зарплата до 250 тыс.».
_SALARY_TO = re.compile(rf"{_SALARY_WORD}\D{{0,15}}до\s+{_AMOUNT}", re.IGNORECASE)


def _amount(digits: str, unit: str | None) -> int | None:
    """Сумма в рублях: «250 тыс» → 250000. Число без единицы и меньше 10 000 зарплатой не считается."""
    value = int(digits.replace(" ", ""))
    if unit or value < 1000:
        return value * 1000 if unit else None
    return value if value >= 10_000 else None


def _parse_salary(text: str) -> tuple[int | None, int | None]:
    for match in _SALARY_RANGE.finditer(text):
        low_digits, low_unit, high_digits, high_unit = match.groups()
        # «от 200 до 300 тыс»: единица при втором числе относится к обоим.
        low, high = _amount(low_digits, low_unit or high_unit), _amount(high_digits, high_unit)
        if low and high and low <= high:
            return low, high
    single = _SALARY_FROM.search(text)
    if single:
        return _amount(*single.groups()), None
    upper = _SALARY_TO.search(text)
    if upper:
        return None, _amount(*upper.groups())
    return None, None


def _parse_formats(text: str) -> list[str]:
    """Форматы работы из текста с учётом отрицаний и слова «только»."""
    found, only = [], []
    for code, fmt in _FORMAT_HINTS.items():
        negated = "|".join(pattern.format(fmt=fmt) for pattern in (_NEGATION_BEFORE, _NEGATION_AFTER))
        # Отрицаемые упоминания вырезаются: формат остаётся, если назван ещё и без отрицания.
        rest = re.sub(negated, " ", text)
        if re.search(fmt, rest):
            found.append(code)
        if re.search(_ONLY.format(fmt=fmt), rest):
            only.append(code)
    return only or found


def parse_need(text: str) -> ParsedNeed:
    need = ParsedNeed()
    lowered = text.lower()
    need.stack = extract_skills(text)

    # Специализация: явное упоминание весит больше, чем типичные для неё технологии.
    votes = dict.fromkeys(SPECIALIZATIONS, 0)
    explicit = [code for code, pattern in _SPECIALIZATION_HINTS.items() if re.search(pattern, lowered)]
    for code in explicit:
        votes[code] += 3
    if re.search(_FULLSTACK, lowered):
        votes["backend"] += 2
        votes["frontend"] += 2
    for skill in need.stack:
        for code in SKILLS[skill][1]:
            votes[code] += 1
    best = max(votes, key=votes.get)
    if votes[best] > 0:
        need.specialization = best
        reason = "названа в тексте" if best in explicit else "определена по стеку"
        need.notes.append(f"Специализация «{SPECIALIZATIONS[best]}» {reason}")
    else:
        need.notes.append("Специализацию определить не удалось — выберите её вручную")

    # Грейд: явное название важнее стажа; из нескольких названных берётся младший, старший попадёт
    # в подборку как смежный.
    requirements = _GRADE_AS_OBJECT.sub(" ", lowered)
    named = [code for code, pattern in GRADE_HINTS.items() if re.search(pattern, requirements)]
    years = _YEARS.search(lowered)
    if named:
        need.grade = min(named, key=list(GRADES).index)
        need.notes.append(f"Грейд «{GRADES[need.grade]['name']}» назван в тексте")
    elif years:
        count = int(years.group(1) or years.group(2))
        need.grade = "senior" if count >= 3 else "middle" if count >= 1 else "junior"
        need.notes.append(f"Грейд «{GRADES[need.grade]['name']}» определён по требуемому стажу: {count} г.")
    else:
        need.notes.append("Грейд в тексте не указан — выберите его вручную")

    if need.stack:
        need.notes.append(f"Стек: {', '.join(need.stack)}")
    need.work_formats = _parse_formats(lowered)
    if need.work_formats:
        need.notes.append("Формат работы: " + ", ".join(WORK_FORMATS[code].lower() for code in need.work_formats))
    need.salary_from, need.salary_to = _parse_salary(lowered)
    if need.salary_from:
        upper = f" – {need.salary_to:,}".replace(",", " ") if need.salary_to else ""
        need.notes.append(f"Зарплата: от {need.salary_from:,}{upper} ₽".replace(",", " "))
    elif need.salary_to:
        need.notes.append(f"Зарплата: до {need.salary_to:,} ₽".replace(",", " "))
    return need
