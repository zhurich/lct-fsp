"""Ответ на ошибки проверки входных данных: понятный пользователю текст на русском.

Стандартный обработчик FastAPI возвращает английские сообщения Pydantic и повторяет в ответе присланное
значение; для NaN и бесконечности это заканчивалось ошибкой сервера, потому что они не записываются в JSON.
"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# Подписи полей, как они названы в интерфейсе.
_LABELS = {
    "email": "Почта",
    "password": "Пароль",
    "title": "Название",
    "text": "Текст",
    "description": "Описание",
    "message": "Сообщение",
    "contact": "Способ связи",
    "specialization": "Специализация",
    "grade": "Грейд",
    "stack": "Стек",
    "roles": "Роли",
    "soft_skills": "Софт-скиллы",
    "work_formats": "Формат работы",
    "experience_years": "Стаж",
    "salary_expectation": "Ожидаемая зарплата",
    "salary_from": "Зарплата от",
    "salary_to": "Зарплата до",
    "full_name": "Имя",
    "phone": "Телефон",
    "telegram": "Telegram",
    "city": "Город",
    "about": "О себе",
    "name": "Название компании",
    "answer": "Вариант ответа",
    "rating": "Оценка",
    "fsp_id": "ФСП ID",
}

_NOT_A_NUMBER = "укажите число"
_MESSAGES = {
    "missing": "обязательное поле",
    "string_too_short": "слишком короткое значение (не меньше {min_length} симв.)",
    "string_too_long": "слишком длинное значение (не больше {max_length} симв.)",
    "too_long": "слишком много элементов (не больше {max_length})",
    "greater_than": "значение должно быть больше {gt}",
    "greater_than_equal": "значение должно быть не меньше {ge}",
    "less_than": "значение должно быть меньше {lt}",
    "less_than_equal": "значение должно быть не больше {le}",
    "int_parsing": _NOT_A_NUMBER,
    "int_type": _NOT_A_NUMBER,
    "int_from_float": "укажите целое число",
    "int_parsing_size": "слишком большое число",
    "float_parsing": _NOT_A_NUMBER,
    "float_type": _NOT_A_NUMBER,
    "finite_number": _NOT_A_NUMBER,
    "string_type": "укажите текст",
    "bool_type": "укажите «да» или «нет»",
    "bool_parsing": "укажите «да» или «нет»",
    "list_type": "укажите список",
    "enum": "недопустимое значение",
    "json_invalid": "тело запроса не является корректным JSON",
}


def _message(error: dict) -> str:
    kind = error["type"]
    if kind == "value_error":
        # Собственные проверки схем уже написаны по-русски; Pydantic добавляет к ним служебную приставку.
        return error["msg"].removeprefix("Value error, ")
    template = _MESSAGES.get(kind, "некорректное значение")
    try:
        text = template.format(**error.get("ctx", {}))
    except (KeyError, IndexError):
        text = "некорректное значение"
    # Имя поля — последний текстовый элемент пути (индексы списков пропускаются).
    field = next((part for part in reversed(error["loc"]) if isinstance(part, str)), None)
    if field in (None, "body", "query", "path"):
        return text[0].upper() + text[1:]
    return f"{_LABELS.get(field, field)}: {text}"


async def validation_error_handler(request: Request, error: RequestValidationError) -> JSONResponse:
    detail = [{"loc": list(item["loc"]), "msg": _message(item), "type": item["type"]} for item in error.errors()]
    return JSONResponse({"detail": detail}, status_code=422)
