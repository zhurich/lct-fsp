"""Классический сценарий: работодатель публикует вакансию, кандидат откликается сам.

Дополняет основную механику (работодатель находит кандидата по категории), а не заменяет её: откликнуться
может только кандидат с подтверждённой тестом категорией, так что и здесь работодатель видит проверенный
уровень, а не только резюме.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db, utcnow
from app.core.deps import current_candidate, current_employer
from app.core.schemas import PathId
from app.modules.assessment.models import CandidateCategory
from app.modules.auth.models import User
from app.modules.candidates.models import CandidateProfile
from app.modules.candidates.privacy import visible_experience
from app.modules.employers.models import Company
from app.modules.invitations.models import PENDING, InvitationStatus
from app.modules.invitations.schemas import CandidateContacts
from app.modules.vacancies.models import Application, Vacancy
from app.modules.vacancies.schemas import (
    ApplicationOut,
    ApplyIn,
    CandidateVacancyOut,
    EmployerVacancyOut,
    MyApplicationOut,
    VacancyIn,
)

router = APIRouter(tags=["Вакансии и отклики"])

_NOT_FOUND = {404: {"description": "Вакансия не найдена"}}


def _own_vacancy(vacancy_id: PathId, user: User = Depends(current_employer), db: Session = Depends(get_db)) -> Vacancy:
    vacancy = db.get(Vacancy, vacancy_id)
    if vacancy is None or vacancy.employer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вакансия не найдена")
    return vacancy


def _for_employer(db: Session, vacancy: Vacancy) -> EmployerVacancyOut:
    statuses = db.scalars(select(Application.status).where(Application.vacancy_id == vacancy.id)).all()
    result = EmployerVacancyOut.model_validate(vacancy)
    result.applications_total = len(statuses)
    result.applications_new = sum(item == InvitationStatus.sent for item in statuses)
    return result


@router.get("/employer/vacancies", response_model=list[EmployerVacancyOut], summary="Вакансии компании")
def employer_vacancies(user: User = Depends(current_employer), db: Session = Depends(get_db)):
    vacancies = db.scalars(select(Vacancy).where(Vacancy.employer_id == user.id).order_by(Vacancy.id.desc()))
    return [_for_employer(db, vacancy) for vacancy in vacancies]


@router.post(
    "/employer/vacancies",
    response_model=EmployerVacancyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Опубликовать вакансию",
    responses={409: {"description": "Не заполнено название компании"}},
)
def create_vacancy(data: VacancyIn, user: User = Depends(current_employer), db: Session = Depends(get_db)):
    company = db.get(Company, user.id)
    if company is None or not company.name.strip():
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Укажите название компании в разделе «Компания» — оно показывается в вакансии"
        )
    vacancy = Vacancy(employer_id=user.id, **data.model_dump())
    db.add(vacancy)
    db.commit()
    return _for_employer(db, vacancy)


@router.put(
    "/employer/vacancies/{vacancy_id}",
    response_model=EmployerVacancyOut,
    summary="Изменить вакансию, закрыть или открыть заново",
    responses=_NOT_FOUND,
)
def update_vacancy(data: VacancyIn, vacancy: Vacancy = Depends(_own_vacancy), db: Session = Depends(get_db)):
    for field, value in data.model_dump().items():
        setattr(vacancy, field, value)
    db.commit()
    return _for_employer(db, vacancy)


@router.get(
    "/employer/vacancies/{vacancy_id}/applications",
    response_model=list[ApplicationOut],
    summary="Отклики на вакансию; новые после выдачи помечаются просмотренными",
    responses=_NOT_FOUND,
)
def vacancy_applications(vacancy: Vacancy = Depends(_own_vacancy), db: Session = Depends(get_db)):
    applications = db.scalars(
        select(Application).where(Application.vacancy_id == vacancy.id).order_by(Application.id.desc())
    ).all()
    result = []
    for application in applications:
        profile = db.get(CandidateProfile, application.candidate_id)
        category = db.get(CandidateCategory, application.candidate_id)
        result.append(
            ApplicationOut(
                id=application.id,
                candidate_id=application.candidate_id,
                specialization=category.specialization,
                grade=category.grade,
                test_score=category.score,
                stack=profile.stack,
                # Настройки приватности действуют и здесь: отклик раскрывает контакты, но не скрытые поля.
                experience_years=visible_experience(profile),
                message=application.message,
                status=application.status,
                created_at=application.created_at,
                # Кандидат откликнулся сам — это и есть его согласие раскрыть контакты этому работодателю.
                contacts=CandidateContacts(
                    full_name=profile.full_name,
                    email=db.get(User, application.candidate_id).email,
                    phone=profile.phone,
                    telegram=profile.telegram,
                ),
            )
        )
    # Ответ собран до смены статуса, чтобы работодатель один раз увидел отклик как новый.
    for application in applications:
        if application.status == InvitationStatus.sent:
            application.status = InvitationStatus.viewed
    db.commit()
    return result


def _respond(db: Session, user: User, application_id: int, new_status: InvitationStatus) -> None:
    application = db.get(Application, application_id)
    vacancy = db.get(Vacancy, application.vacancy_id) if application else None
    if vacancy is None or vacancy.employer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Отклик не найден")
    if application.status not in PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "На этот отклик уже дан ответ")
    application.status = new_status
    application.responded_at = utcnow()
    db.commit()


_RESPOND_ERRORS = {404: {"description": "Отклик не найден"}, 409: {"description": "На отклик уже дан ответ"}}


@router.post(
    "/employer/applications/{application_id}/accept",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Принять отклик",
    responses=_RESPOND_ERRORS,
)
def accept_application(application_id: PathId, user: User = Depends(current_employer), db: Session = Depends(get_db)):
    _respond(db, user, application_id, InvitationStatus.accepted)


@router.post(
    "/employer/applications/{application_id}/decline",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отклонить отклик",
    responses=_RESPOND_ERRORS,
)
def decline_application(application_id: PathId, user: User = Depends(current_employer), db: Session = Depends(get_db)):
    _respond(db, user, application_id, InvitationStatus.declined)


@router.get(
    "/candidate/vacancies",
    response_model=list[CandidateVacancyOut],
    summary="Открытые вакансии; подходящие категории кандидата идут первыми",
)
def candidate_vacancies(
    specialization: str | None = None,
    grade: str | None = None,
    user: User = Depends(current_candidate),
    db: Session = Depends(get_db),
):
    query = select(Vacancy, Company).join(Company, Company.user_id == Vacancy.employer_id).where(Vacancy.is_open)
    if specialization:
        query = query.where(Vacancy.specialization == specialization)
    if grade:
        query = query.where(Vacancy.grade == grade)
    category = db.get(CandidateCategory, user.id)
    applied = dict(
        db.execute(select(Application.vacancy_id, Application.status).where(Application.candidate_id == user.id)).all()
    )
    result = [
        CandidateVacancyOut(
            **VacancyIn.model_validate(vacancy, from_attributes=True).model_dump(),
            id=vacancy.id,
            created_at=vacancy.created_at,
            company_name=company.name,
            company_industry=company.industry,
            company_description=company.description,
            fits_category=bool(
                category and (category.specialization, category.grade) == (vacancy.specialization, vacancy.grade)
            ),
            application_status=applied.get(vacancy.id),
        )
        for vacancy, company in db.execute(query.order_by(Vacancy.id.desc()))
    ]
    result.sort(key=lambda item: item.fits_category, reverse=True)
    return result


@router.post(
    "/candidate/vacancies/{vacancy_id}/apply",
    status_code=status.HTTP_201_CREATED,
    response_model=MyApplicationOut,
    summary="Откликнуться на вакансию: контакты кандидата открываются этому работодателю",
    responses={
        404: {"description": "Вакансия не найдена или закрыта"},
        409: {"description": "Категория ещё не подтверждена тестом либо отклик уже отправлен"},
    },
)
def apply(vacancy_id: PathId, data: ApplyIn, user: User = Depends(current_candidate), db: Session = Depends(get_db)):
    vacancy = db.get(Vacancy, vacancy_id)
    if vacancy is None or not vacancy.is_open:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вакансия не найдена или уже закрыта")
    if db.get(CandidateCategory, user.id) is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Сначала пройдите тест: работодатель увидит в отклике вашу подтверждённую категорию"
        )
    exists = db.scalar(
        select(func.count()).select_from(Application).where(
            Application.vacancy_id == vacancy_id, Application.candidate_id == user.id
        )
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Вы уже откликнулись на эту вакансию")
    application = Application(vacancy_id=vacancy_id, candidate_id=user.id, message=data.message)
    db.add(application)
    try:
        db.commit()
    except IntegrityError:
        # Отклик только что создал параллельный запрос: сработало ограничение уникальности.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Вы уже откликнулись на эту вакансию") from None
    return _mine(db, application, vacancy)


def _mine(db: Session, application: Application, vacancy: Vacancy) -> MyApplicationOut:
    return MyApplicationOut(
        id=application.id,
        vacancy_id=vacancy.id,
        title=vacancy.title,
        company_name=db.get(Company, vacancy.employer_id).name,
        salary_from=vacancy.salary_from,
        salary_to=vacancy.salary_to,
        status=application.status,
        created_at=application.created_at,
        responded_at=application.responded_at,
    )


@router.get("/candidate/applications", response_model=list[MyApplicationOut], summary="Свои отклики и их статусы")
def my_applications(user: User = Depends(current_candidate), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Application, Vacancy)
        .join(Vacancy, Vacancy.id == Application.vacancy_id)
        .where(Application.candidate_id == user.id)
        .order_by(Application.id.desc())
    )
    return [_mine(db, application, vacancy) for application, vacancy in rows]
