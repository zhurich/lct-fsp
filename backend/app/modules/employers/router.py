from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import current_employer
from app.modules.auth.models import User
from app.modules.employers.models import Company
from app.modules.employers.schemas import CompanyIn, CompanyOut

router = APIRouter(prefix="/employer", tags=["Кабинет работодателя"])


def get_or_create_company(db: Session, user: User) -> Company:
    company = db.get(Company, user.id)
    if company is None:
        try:
            with db.begin_nested():
                db.add(Company(user_id=user.id))
        except IntegrityError:
            # Профиль компании только что создал параллельный запрос.
            pass
        db.commit()
        company = db.get(Company, user.id)
    return company


@router.get("/company", response_model=CompanyOut, summary="Профиль компании")
def get_company(user: User = Depends(current_employer), db: Session = Depends(get_db)):
    return get_or_create_company(db, user)


@router.put("/company", response_model=CompanyOut, summary="Сохранить профиль компании")
def update_company(
    data: CompanyIn,
    user: User = Depends(current_employer),
    db: Session = Depends(get_db),
):
    company = get_or_create_company(db, user)
    for field, value in data.model_dump().items():
        setattr(company, field, value)
    db.commit()
    return company
