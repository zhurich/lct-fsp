from fastapi import APIRouter
from pydantic import BaseModel

from app.modules.reference.data import GRADES, SPECIALIZATIONS, WORK_FORMATS
from app.modules.reference.skills import SKILLS

router = APIRouter(prefix="/reference", tags=["Справочники"])


class Item(BaseModel):
    code: str
    name: str
    description: str | None = None


class ReferenceOut(BaseModel):
    specializations: list[Item]
    grades: list[Item]
    work_formats: list[Item]
    skills: list[str]


@router.get("", response_model=ReferenceOut, summary="Специализации, грейды, форматы работы и словарь технологий")
def get_reference():
    return ReferenceOut(
        specializations=[Item(code=code, name=name) for code, name in SPECIALIZATIONS.items()],
        grades=[Item(code=code, **grade) for code, grade in GRADES.items()],
        work_formats=[Item(code=code, name=name) for code, name in WORK_FORMATS.items()],
        skills=list(SKILLS),
    )
