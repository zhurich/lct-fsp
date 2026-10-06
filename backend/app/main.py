import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError

from app.core.db import Base, engine
from app.core.errors import validation_error_handler
from app.modules.assessment.router import router as assessment_router
from app.modules.auth.router import router as auth_router
from app.modules.challenges.router import router as challenges_router
from app.modules.candidates.router import router as candidates_router
from app.modules.employers.router import router as employers_router
from app.modules.fsp.router import mock_router as fsp_id_router
from app.modules.fsp.router import router as fsp_router
from app.modules.invitations.router import router as invitations_router
from app.modules.matching.router import router as matching_router
from app.modules.reference.router import router as reference_router
from app.modules.vacancies.router import router as vacancies_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title="ФСП Карьера — API",
    description="Платформа подбора ИТ-специалистов с обратной механикой: работодатель сам выходит на кандидата.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.add_exception_handler(RequestValidationError, validation_error_handler)

api = APIRouter(prefix="/api")
api.include_router(auth_router)
api.include_router(reference_router)
api.include_router(candidates_router)
api.include_router(employers_router)
api.include_router(assessment_router)
api.include_router(fsp_router)
api.include_router(fsp_id_router)
api.include_router(matching_router)
api.include_router(invitations_router)
api.include_router(vacancies_router)
api.include_router(challenges_router)


@api.get("/health", tags=["Служебное"], summary="Проверка доступности")
def health():
    return {"status": "ok"}


app.include_router(api)
