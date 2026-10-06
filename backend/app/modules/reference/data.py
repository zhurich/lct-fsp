"""Справочники платформы. Категория кандидата = специализация × грейд."""

SPECIALIZATIONS: dict[str, str] = {
    "backend": "Бэкенд-разработка",
    "frontend": "Фронтенд-разработка",
    "mobile": "Мобильная разработка",
    "qa": "Тестирование (QA)",
    "devops": "DevOps и инфраструктура",
    "data": "Data Science и ML",
    "analyst": "Системная и бизнес-аналитика",
}

# Порядок ключей задаёт порядок грейдов: от младшего к старшему.
GRADES: dict[str, dict[str, str]] = {
    "intern": {"name": "Стажёр", "description": "Без коммерческого опыта"},
    "junior": {"name": "Junior", "description": "Опыт до 1 года"},
    "middle": {"name": "Middle", "description": "Опыт 1–3 года, самостоятельная работа"},
    "senior": {"name": "Senior", "description": "Опыт от 3 лет, проектирование и наставничество"},
}

WORK_FORMATS: dict[str, str] = {
    "office": "Офис",
    "hybrid": "Гибрид",
    "remote": "Удалённо",
}
