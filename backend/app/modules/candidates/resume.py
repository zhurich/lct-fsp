"""Разбор резюме из PDF: текстовый слой → поля профиля.

Работает на правилах и словарях, как и разбор потребности работодателя (общие словарь технологий и
признаки специализации и грейда). Результат — черновик: кандидат проверяет поля и сохраняет профиль сам.
Категорию резюме не определяет — её даёт только тест. Точка расширения под языковую модель —
функция parse_resume: достаточно вернуть тот же ParsedResume.
"""

import io
import re
from dataclasses import dataclass, field

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.modules.matching.parser import GRADE_HINTS, parse_need
from app.modules.reference.data import GRADES, SPECIALIZATIONS

MAX_PAGES = 10


@dataclass
class ParsedResume:
    full_name: str = ""
    phone: str = ""
    telegram: str = ""
    city: str = ""
    about: str = ""
    specialization: str | None = None
    # Грейд со слов кандидата: в профиль не записывается, подставляется в опрос перед тестом.
    claimed_grade: str | None = None
    stack: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    soft_skills: list[str] = field(default_factory=list)
    experience_years: float | None = None
    work_formats: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class ResumeError(ValueError):
    """Файл не удалось прочитать как резюме; текст ошибки показывается пользователю."""


def extract_text(data: bytes) -> str:
    if not data.startswith(b"%PDF"):
        raise ResumeError("Это не PDF-файл")
    try:
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages[:MAX_PAGES])
    except (PyPdfError, ValueError, KeyError) as error:
        raise ResumeError("Не удалось прочитать PDF: файл повреждён или защищён паролем") from error
    if len(text.strip()) < 30:
        raise ResumeError("В файле нет текстового слоя (похоже на скан). Заполните профиль вручную")
    return text


_NAME = re.compile(r"^[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?(?: [А-ЯЁ][а-яё]+){1,2}$")
_NOT_NAME = re.compile(r"резюме|разработчик|инженер|аналитик|тестировщик|опыт|образование|контакты|навыки", re.I)
_PHONE = re.compile(r"(?:\+7|\b8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}\b")
_TELEGRAM = re.compile(r"(?:t\.me/|(?:telegram|телеграм|tg)\s*[:\-—]?\s*)@?([A-Za-z]\w{3,31})|(?<![\w.])@([A-Za-z]\w{3,31})\b", re.I)
# «г.» считается указанием города только в начале строки или после запятой: иначе это «5 г.» из стажа.
_CITY = re.compile(
    r"(?:город|проживает|место проживания|локация|(?:^|[,;(][ 	]*)г\.)[ 	]*[:\-—]?[ 	]*([А-ЯЁ][а-яё]+(?:[ -][А-ЯЁ][а-яё]+)?)",
    re.M,
)
_CITIES = [
    "Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань", "Нижний Новгород", "Челябинск",
    "Самара", "Омск", "Ростов-на-Дону", "Уфа", "Красноярск", "Воронеж", "Пермь", "Волгоград", "Краснодар",
    "Тюмень", "Томск", "Иннополис", "Калининград", "Владивосток", "Иркутск", "Ярославль", "Тула",
]
_EXPERIENCE = re.compile(
    r"(?:опыт\w*(?:\s+работы)?|стаж)\D{0,25}?(\d+(?:[.,]\d+)?)\s*(?:лет|года|год|г\.)(?:\s*(\d+)\s*мес)?", re.I
)
_PERIOD = re.compile(r"((?:19|20)\d\d)\s*(?:г\.?)?\s*[-–—]\s*((?:19|20)\d\d|наст\w*|н\.\s?в\.?|по сей|сейчас|present|now)", re.I)
# Заголовки разделов резюме: периоды учёбы в стаж не входят.
_STUDY_SECTION = re.compile(
    r"^\W*(?:образовани\w*|обучени\w*|уч[её]б\w*|курсы|повышение квалификации|сертификат\w*|education|courses)\b", re.I
)
_OTHER_SECTION = re.compile(
    r"^\W*(?:опыт\w*|места? работы|трудов\w+|карьер\w*|проект\w*|навык\w*|о себе|обо мне|контакт\w*"
    r"|experience|employment|projects|skills|about)\b",
    re.I,
)
_STUDY_LINE = re.compile(
    r"университет|институт|академи\w+|колледж|техникум|\bвуз\b|\bшкол\w+|бакалавр\w*|магистр\w*|специалитет"
    r"|аспирант\w*|факультет\w*|кафедр\w+|студент\w*|\bкурс\w*|university|college|bachelor|master'?s",
    re.I,
)
_NO_EXPERIENCE = re.compile(
    r"(?:опыт\w*(?:\s+работы)?\s*[:\-—]?\s*(?:отсутствует|нет\b)|без\s+опыта|нет\s+опыта|no\s+experience)", re.I
)
_ABOUT = re.compile(r"(?:^|\n)\s*(?:о себе|обо мне|about)\s*:?\s*\n?(.+?)(?:\n\s*\n|\n[А-ЯЁA-Z][^\n]{0,30}:?\s*\n|\Z)", re.I | re.S)

# Основа слова → название для профиля.
_ROLES = {
    r"тимлид|team ?lead|руководител\w+ (?:команд|групп)": "Тимлид",
    r"техлид|tech ?lead": "Техлид",
    r"архитектор": "Архитектор",
    r"наставник|ментор|mentor": "Наставник",
    r"код[- ]?ревью|code review": "Ревьюер",
    r"scrum[- ]мастер|скрам[- ]мастер": "Scrum-мастер",
    r"разработчик|developer|программист": "Разработчик",
    r"тестировщик|qa[- ]инженер": "Тестировщик",
    r"аналитик": "Аналитик",
    r"devops|девопс": "DevOps-инженер",
}
_SOFT_SKILLS = {
    r"коммуникабельн|коммуникативн|умение договариваться": "Коммуникабельность",
    r"работ\w+ в команде|командн\w+ (?:работ|игрок)": "Работа в команде",
    r"ответственн": "Ответственность",
    r"самоорганиз|самостоятельн": "Самостоятельность",
    r"обучаем|быстро (?:учусь|обучаюсь)": "Обучаемость",
    r"внимательн\w+ к детал|внимание к детал": "Внимание к деталям",
    r"стрессоустойчив": "Стрессоустойчивость",
    r"инициативн|проактивн": "Инициативность",
    r"аналитическ\w+ (?:мышлени|склад)": "Аналитическое мышление",
    r"тайм[- ]менеджмент|управлени\w+ временем": "Тайм-менеджмент",
    r"наставничеств|менторств": "Наставничество",
}


def _by_dictionary(text: str, dictionary: dict[str, str]) -> list[str]:
    return [name for pattern, name in dictionary.items() if re.search(pattern, text, re.I)]


def _work_lines(text: str) -> list[str]:
    """Строки резюме без раздела об образовании и без строк об учёбе."""
    lines, studying = [], False
    for line in re.split(r"[\n;]", text):
        if _STUDY_SECTION.match(line):
            studying = True
        elif _OTHER_SECTION.match(line):
            studying = False
        if not studying and not _STUDY_LINE.search(line):
            lines.append(line)
    return lines


def _experience(text: str, current_year: int) -> float | None:
    """Стаж: явное указание («опыт работы 3 года 5 месяцев») либо сумма периодов работы по годам.

    Периоды учёбы в стаж не входят: годы считаются только по строкам вне раздела об образовании."""
    stated = _EXPERIENCE.search(text)
    if stated:
        return round(float(stated.group(1).replace(",", ".")) + int(stated.group(2) or 0) / 12, 1)
    years = set()
    for start, end in _PERIOD.findall("\n".join(_work_lines(text))):
        finish = int(end) if end.isdigit() else current_year
        # Периоды могут пересекаться (совмещение, проекты), поэтому считаются уникальные годы.
        years.update(range(int(start), min(finish, current_year)))
    if years:
        return float(len(years))
    return 0.0 if _NO_EXPERIENCE.search(text) else None


def parse_resume(text: str, current_year: int) -> ParsedResume:
    resume = ParsedResume()
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # ФИО — одна из первых строк: два-три слова с заглавной буквы без служебных слов.
    resume.full_name = next((line for line in lines[:10] if _NAME.match(line) and not _NOT_NAME.search(line)), "")
    phone = _PHONE.search(text)
    resume.phone = re.sub(r"\s+", " ", phone.group()).strip() if phone else ""
    without_emails = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", " ", text)
    telegram = _TELEGRAM.search(without_emails)
    resume.telegram = f"@{telegram.group(1) or telegram.group(2)}" if telegram else ""
    city = _CITY.search(text)
    # Известный город надёжнее, чем слово после «город:».
    resume.city = next((name for name in _CITIES if name in text), city.group(1) if city else "")
    about = _ABOUT.search(text)
    resume.about = " ".join(about.group(1).split())[:600] if about else ""

    # Специализация, грейд, стек и формат работы распознаются теми же правилами, что и в потребности.
    need = parse_need(text)
    resume.specialization = need.specialization
    resume.stack, resume.work_formats = need.stack, need.work_formats
    resume.roles = _by_dictionary(text, _ROLES)
    resume.soft_skills = _by_dictionary(text, _SOFT_SKILLS)
    resume.experience_years = _experience(text, current_year)
    # Грейд берётся только из заголовка резюме: ниже по тексту названия грейдов относятся к прошлым
    # местам работы и подопечным. Если в заголовке его нет — оценивается по стажу.
    headline = " ".join(lines[:6]).lower()
    named = [code for code, pattern in GRADE_HINTS.items() if re.search(pattern, headline)]
    if named:
        resume.claimed_grade = named[0]
    elif resume.experience_years is not None:
        years = resume.experience_years
        resume.claimed_grade = "senior" if years >= 3 else "middle" if years >= 1 else "junior"

    found = {
        "ФИО": resume.full_name,
        "Телефон": resume.phone,
        "Telegram": resume.telegram,
        "Город": resume.city,
        "Специализация": SPECIALIZATIONS.get(resume.specialization, ""),
        "Заявленный грейд": GRADES[resume.claimed_grade]["name"] if resume.claimed_grade else "",
        "Стаж": f"{resume.experience_years:g} г." if resume.experience_years is not None else "",
        "Стек": ", ".join(resume.stack),
        "Роли": ", ".join(resume.roles),
        "Софт-скиллы": ", ".join(resume.soft_skills),
    }
    resume.notes = [f"{label}: {value}" for label, value in found.items() if value]
    missing = [label for label, value in found.items() if not value]
    if missing:
        resume.notes.append("Не распознано: " + ", ".join(missing).lower() + " — заполните вручную")
    return resume
