from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db, utcnow
from app.core.deps import current_candidate, current_employer
from app.core.schemas import PathId
from app.modules.assessment.models import Assessment, AttemptStatus, CandidateCategory
from app.modules.auth.models import User
from app.modules.candidates.models import CandidateProfile
from app.modules.employers.models import Company
from app.modules.invitations.models import PENDING, Invitation, InvitationStatus
from app.modules.invitations.schemas import (
    CandidateContacts,
    CandidateInvitationOut,
    EmployerInvitationOut,
    InvitationIn,
)

router = APIRouter(tags=["Приглашения"])


def _base_fields(invitation: Invitation) -> dict:
    return {
        "id": invitation.id,
        "title": invitation.title,
        "message": invitation.message,
        "salary_from": invitation.salary_from,
        "salary_to": invitation.salary_to,
        "contact": invitation.contact,
        "status": invitation.status,
        "created_at": invitation.created_at,
        "responded_at": invitation.responded_at,
    }


def _for_employer(db: Session, invitation: Invitation) -> EmployerInvitationOut:
    category = db.get(CandidateCategory, invitation.candidate_id)
    contacts = None
    # Единственное место, где работодателю отдаются контакты кандидата.
    if invitation.status == InvitationStatus.accepted:
        profile = db.get(CandidateProfile, invitation.candidate_id)
        contacts = CandidateContacts(
            full_name=profile.full_name,
            email=db.get(User, invitation.candidate_id).email,
            phone=profile.phone,
            telegram=profile.telegram,
        )
    return EmployerInvitationOut(
        **_base_fields(invitation),
        candidate_id=invitation.candidate_id,
        specialization=category.specialization if category else None,
        grade=category.grade if category else None,
        contacts=contacts,
    )


def _for_candidate(db: Session, invitation: Invitation) -> CandidateInvitationOut:
    company = db.get(Company, invitation.employer_id)
    return CandidateInvitationOut(
        **_base_fields(invitation),
        company_name=company.name,
        company_industry=company.industry,
        company_description=company.description,
        company_website=company.website,
    )


@router.post(
    "/employer/invitations",
    response_model=EmployerInvitationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Пригласить кандидата: предложение, зарплатная вилка и способ связи",
    responses={
        404: {"description": "Кандидат не найден в банке"},
        409: {"description": "Не заполнено название компании либо кандидат уже приглашён"},
    },
)
def create_invitation(
    data: InvitationIn,
    user: User = Depends(current_employer),
    db: Session = Depends(get_db),
):
    company = db.get(Company, user.id)
    if company is None or not company.name.strip():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Укажите название компании в разделе «Компания» — кандидат увидит его в приглашении",
        )
    profile = db.get(CandidateProfile, data.candidate_id)
    # Пригласить можно любого, кто виден в выдаче: с категорией либо с заявленным, но не подтверждённым
    # грейдом.
    tested = db.get(CandidateCategory, data.candidate_id) or db.scalar(
        select(Assessment.id)
        .where(Assessment.user_id == data.candidate_id, Assessment.status == AttemptStatus.failed)
        .limit(1)
    )
    if profile is None or not profile.is_published or not tested:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Кандидат не найден")
    existing = db.scalar(
        select(Invitation).where(
            Invitation.employer_id == user.id,
            Invitation.candidate_id == data.candidate_id,
            Invitation.status != InvitationStatus.declined,
        )
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Вы уже пригласили этого кандидата")
    invitation = Invitation(employer_id=user.id, **data.model_dump())
    db.add(invitation)
    try:
        db.commit()
    except IntegrityError:
        # Такое же приглашение только что создал параллельный запрос: сработал уникальный индекс.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Вы уже пригласили этого кандидата") from None
    return _for_employer(db, invitation)


@router.get(
    "/employer/invitations",
    response_model=list[EmployerInvitationOut],
    summary="Отправленные приглашения и их статусы",
)
def employer_invitations(user: User = Depends(current_employer), db: Session = Depends(get_db)):
    invitations = db.scalars(
        select(Invitation).where(Invitation.employer_id == user.id).order_by(Invitation.id.desc())
    )
    return [_for_employer(db, invitation) for invitation in invitations]


@router.get(
    "/candidate/invitations",
    response_model=list[CandidateInvitationOut],
    summary="Входящие приглашения; новые после выдачи помечаются просмотренными",
)
def candidate_invitations(user: User = Depends(current_candidate), db: Session = Depends(get_db)):
    invitations = db.scalars(
        select(Invitation).where(Invitation.candidate_id == user.id).order_by(Invitation.id.desc())
    ).all()
    # Ответ собирается до смены статуса, чтобы кандидат один раз увидел приглашение как новое.
    result = [_for_candidate(db, invitation) for invitation in invitations]
    for invitation in invitations:
        if invitation.status == InvitationStatus.sent:
            invitation.status = InvitationStatus.viewed
    db.commit()
    return result


def _respond(db: Session, user: User, invitation_id: int, new_status: InvitationStatus) -> CandidateInvitationOut:
    invitation = db.get(Invitation, invitation_id)
    # Чужое приглашение неотличимо от несуществующего.
    if invitation is None or invitation.candidate_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Приглашение не найдено")
    if invitation.status not in PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "На это приглашение уже дан ответ")
    invitation.status = new_status
    invitation.responded_at = utcnow()
    db.commit()
    return _for_candidate(db, invitation)


_RESPOND_ERRORS = {
    404: {"description": "Приглашение не найдено"},
    409: {"description": "На приглашение уже дан ответ"},
}


@router.post(
    "/candidate/invitations/{invitation_id}/accept",
    response_model=CandidateInvitationOut,
    summary="Принять приглашение: контакты кандидата открываются работодателю",
    responses=_RESPOND_ERRORS,
)
def accept(invitation_id: PathId, user: User = Depends(current_candidate), db: Session = Depends(get_db)):
    return _respond(db, user, invitation_id, InvitationStatus.accepted)


@router.post(
    "/candidate/invitations/{invitation_id}/decline",
    response_model=CandidateInvitationOut,
    summary="Отклонить приглашение",
    responses=_RESPOND_ERRORS,
)
def decline(invitation_id: PathId, user: User = Depends(current_candidate), db: Session = Depends(get_db)):
    return _respond(db, user, invitation_id, InvitationStatus.declined)
