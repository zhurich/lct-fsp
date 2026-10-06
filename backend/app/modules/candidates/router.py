from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db, utcnow
from app.core.deps import current_candidate
from app.modules.auth.models import User
from app.modules.assessment.models import CandidateCategory
from app.modules.candidates.models import CandidateProfile
from app.modules.candidates.pdf import PdfUnavailable, build_profile_pdf
from app.modules.candidates.resume import ResumeError, extract_text, parse_resume
from app.modules.candidates.schemas import CandidateProfileIn, CandidateProfileOut, ParsedResumeOut

router = APIRouter(prefix="/candidate", tags=["Кабинет кандидата"])


def get_or_create_profile(db: Session, user: User) -> CandidateProfile:
    profile = db.get(CandidateProfile, user.id)
    if profile is None:
        try:
            # Точка сохранения: при неудаче откатывается только вставка, а не вся работа запроса.
            with db.begin_nested():
                db.add(CandidateProfile(user_id=user.id))
        except IntegrityError:
            # Профиль только что создал параллельный запрос того же кандидата.
            pass
        db.commit()
        profile = db.get(CandidateProfile, user.id)
    return profile


@router.get("/profile", response_model=CandidateProfileOut, summary="Свой профиль")
def get_profile(user: User = Depends(current_candidate), db: Session = Depends(get_db)):
    return get_or_create_profile(db, user)


@router.put("/profile", response_model=CandidateProfileOut, summary="Сохранить профиль")
def update_profile(
    data: CandidateProfileIn,
    user: User = Depends(current_candidate),
    db: Session = Depends(get_db),
):
    profile = get_or_create_profile(db, user)
    for field, value in data.model_dump().items():
        setattr(profile, field, value)
    db.commit()
    return profile


@router.post(
    "/profile/resume",
    response_model=ParsedResumeOut,
    summary="Распознать резюме из PDF: возвращает черновик полей профиля, ничего не сохраняя",
    responses={
        413: {"description": "Файл слишком большой"},
        422: {"description": "Файл не PDF, повреждён или не содержит текста"},
    },
)
def parse_resume_file(file: UploadFile, user: User = Depends(current_candidate)):
    limit = settings.resume_max_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Файл больше {settings.resume_max_mb} МБ")
    try:
        text = extract_text(data)
    except ResumeError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    # Файл резюме не сохраняется: из него берутся только поля, которые кандидат подтвердит в форме.
    return parse_resume(text, utcnow().year)


@router.get(
    "/profile/pdf",
    summary="Стандартизированный PDF-профиль кандидата",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}},
        503: {"description": "На сервере нет шрифта с кириллицей"},
    },
)
def profile_pdf(user: User = Depends(current_candidate), db: Session = Depends(get_db)):
    profile = get_or_create_profile(db, user)
    try:
        content = build_profile_pdf(profile, user.email, db.get(CandidateCategory, user.id))
    except PdfUnavailable as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="fsp-career-profile.pdf"'},
    )
