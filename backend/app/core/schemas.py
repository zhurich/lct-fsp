"""Общие типы входных данных API: одинаковые границы для одинаковых по смыслу полей."""

from typing import Annotated

from fastapi import Path
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Верхняя граница идентификатора — 32-битное целое, как у первичных ключей в PostgreSQL.
MAX_ID = 2**31 - 1
# Идентификатор в пути: значение вне диапазона отклоняется до обращения к базе.
PathId = Annotated[int, Path(ge=1, le=MAX_ID)]
BodyId = Annotated[int, Field(ge=1, le=MAX_ID)]
# Денежная сумма в рублях.
Money = Annotated[int, Field(gt=0, le=100_000_000)]
# Один элемент списка: технология, роль, навык.
Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class InputModel(BaseModel):
    """Тело запроса: пробелы по краям строк отбрасываются до проверки длины, поэтому строка из одних
    пробелов считается пустой."""

    model_config = ConfigDict(str_strip_whitespace=True)
