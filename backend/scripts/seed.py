"""Наполнение базы демонстрационными данными.

Запуск: python -m scripts.seed [--candidates 300] [--seed 7] [--reset]

Создаёт синтетических кандидатов (категория каждого получена честным прогоном адаптивного теста),
работодателей с потребностями из тестового набора вакансий, приглашения в разных статусах, опубликованные
вакансии с откликами и регулярные задания с ответами.
Без --reset работает только на пустой базе; --reset удаляет ВСЕ данные и создаёт схему заново.

Демо-входы (пароль у всех один, см. PASSWORD):
  demo-candidate@example.com — кандидат с категорией и входящими приглашениями
  demo-newcomer@example.com  — новый кандидат без теста, чтобы пройти путь с начала
                               (и demo-newcomer2 … demo-newcomer5 — такие же, по одной на проверяющего)
  demo-employer@example.com  — работодатель с потребностями и отправленными приглашениями
"""

import argparse
import random
import sys
from datetime import timedelta

from sqlalchemy import func, select

from app.core.db import Base, SessionLocal, engine, utcnow
from app.core.security import hash_password
from app.modules.assessment import adaptive
from app.modules.assessment.models import Assessment, AttemptStatus, CandidateCategory, ItemExposure
from app.modules.auth.models import Role, User
from app.modules.candidates.models import CandidateProfile
from app.modules.challenges.models import Challenge, ChallengeAnswer
from app.modules.employers.models import Company
from app.modules.fsp.registry import registry
from app.modules.invitations.models import Invitation, InvitationStatus
from app.modules.matching.models import Need
from app.modules.reference.data import SPECIALIZATIONS
from app.modules.vacancies.models import Application, Vacancy
from scripts import synth
from scripts.vacancies import VACANCIES
from scripts import utf8_output

PASSWORD = "demo12345"
# Чистые записи без теста: по одной на проверяющего.
NEWCOMERS = ["demo-newcomer@example.com", *(f"demo-newcomer{number}@example.com" for number in range(2, 6))]

_NAMES = {
    "m": (["Алексей", "Дмитрий", "Иван", "Максим", "Никита", "Павел", "Роман", "Тимур"],
          ["Иванов", "Смирнов", "Кузнецов", "Попов", "Соколов", "Новиков", "Морозов", "Волков", "Хасанов"]),
    "f": (["Анна", "Дарья", "Елена", "Ксения", "Мария", "Ольга", "Софья", "Алина"],
          ["Иванова", "Смирнова", "Кузнецова", "Попова", "Соколова", "Новикова", "Морозова", "Волкова", "Хасанова"]),
}
_CHALLENGES = [
    ("backend", "Медленный отчёт",
     "Отчёт по платежам за месяц строится 40 секунд, таблица — 60 млн строк. С чего начнёте разбор и какие "
     "решения рассмотрите?"),
    ("frontend", "Список на 10 000 строк",
     "Таблица с 10 000 строк тормозит при прокрутке и фильтрации. Как найдёте причину и что предложите?"),
    ("qa", "Нестабильный автотест",
     "Сквозной тест оформления заказа падает в одном запуске из пяти. Опишите план поиска причины."),
]
_ANSWERS = [
    "Сначала посмотрю план запроса и время по этапам. Проверю, есть ли индекс по дате и статусу, и не читается "
    "ли таблица целиком. Дальше — предрасчёт агрегатов по дням.",
    "Замерю, где теряется время: в базе или в приложении. Если в базе — секционирование по месяцам и "
    "материализованное представление; если в приложении — постраничная выгрузка.",
    "Начну с воспроизведения на копии данных и профилирования. Чаще всего виноваты отсутствие индекса или N+1 "
    "запросов при сборке отчёта.",
]

_COMPANIES = [
    ("ООО «Северный платёж»", "Финтех", "Платёжный сервис для малого бизнеса: эквайринг, сверка, выплаты."),
    ("АО «Логистика 24»", "Логистика", "Платформа управления доставкой для интернет-магазинов."),
    ("ООО «Медкарта»", "Медтех", "Электронная медицинская карта и запись к врачу для частных клиник."),
]


def _user(db, email: str, role: Role, password_hash: str) -> User:
    user = User(email=email, password_hash=password_hash, role=role, email_verified=True, consent_at=utcnow())
    db.add(user)
    db.flush()
    return user


def _candidate(db, rng: random.Random, email: str, password_hash: str, params, exposure, person=None) -> User:
    """Кандидат с профилем; категория — результат прогона теста для его скрытого уровня."""
    person = person or synth.make_person(rng)
    user = _user(db, email, Role.candidate, password_hash)
    first_names, last_names = _NAMES[rng.choice("mf")]
    spec_name = SPECIALIZATIONS[person.specialization].lower()
    db.add(
        CandidateProfile(
            user_id=user.id,
            full_name=f"{rng.choice(first_names)} {rng.choice(last_names)}",
            phone=f"+7 9{rng.randrange(10, 99)} {rng.randrange(100, 999)}-{rng.randrange(10, 99)}-{rng.randrange(10, 99)}",
            telegram=f"@{email.split('@')[0].replace('-', '_')}",
            city=person.city,
            about=f"Направление: {spec_name}. Работаю с {', '.join(person.claimed_stack[:4])}. "
                  f"Опыт — {person.experience_years:g} г.",
            specialization=person.specialization,
            stack=person.claimed_stack,
            experience_years=person.experience_years,
            work_formats=person.work_formats,
            is_published=True,
            fsp_id=person.fsp_id,
            fsp_achievements=person.fsp_achievements,
            fsp_rank=registry.rank(person.fsp_id) if person.fsp_id else None,
            fsp_synced_at=utcnow() if person.fsp_id else None,
        )
    )
    # Попытки разнесены в прошлое, чтобы в демо были и свежие, и давние подтверждения категории.
    finished = utcnow() - timedelta(days=rng.randint(1, 240))
    runs = synth.certify(person, params, rng, exposure)
    for run in runs:
        db.add(
            Assessment(
                user_id=user.id,
                specialization=person.specialization,
                grade=run.grade,
                status=AttemptStatus.passed if run.passed else AttemptStatus.failed,
                questions=run.questions,
                theta=run.theta,
                se=run.se,
                correct_count=sum(q["answer"] == q["correct"] for q in run.questions),
                score=adaptive.to_score(run.theta),
                started_at=finished - timedelta(minutes=20),
                expires_at=finished + timedelta(minutes=10),
                finished_at=finished,
            )
        )
    final = synth.category_of(runs)
    if final:
        db.add(
            CandidateCategory(
                user_id=user.id,
                specialization=person.specialization,
                grade=final.grade,
                score=adaptive.to_score(final.theta),
                assigned_at=finished,
            )
        )
    return user


def seed(candidates: int = 300, seed_value: int = 7) -> dict:
    rng = random.Random(seed_value)
    params = synth.perturbed_params(rng)
    # Хеш считается один раз: argon2 намеренно медленный, а пароль у демо-записей общий.
    password_hash = hash_password(PASSWORD)
    exposure: dict[str, int] = {}
    with SessionLocal() as db:
        for number in range(1, candidates + 1):
            _candidate(db, rng, f"cand{number:03d}@example.com", password_hash, params, exposure)

        # Демо-кандидат: уверенный бэкенд-мидл с понятным стеком.
        demo_person = synth.make_person(rng, "backend")
        demo_person.theta, demo_person.claimed_grade = 0.6, "middle"
        demo_person.claimed_stack = ["Python", "FastAPI", "PostgreSQL", "Docker", "Kafka"]
        demo_person.work_formats = ["remote", "hybrid"]
        # Исход теста случаен, поэтому демо-кандидат создаётся заново, пока не получит нужную историю.
        db.commit()
        while True:
            demo = _candidate(db, rng, "demo-candidate@example.com", password_hash, params, exposure, demo_person)
            db.flush()
            category = db.get(CandidateCategory, demo.id)
            attempts = db.scalar(select(func.count()).select_from(Assessment).where(Assessment.user_id == demo.id))
            # Для показа нужна простая история: одна попытка, пройденная на заявленный грейд.
            if category and category.grade == "middle" and attempts == 1:
                break
            db.rollback()
        for email in NEWCOMERS:
            newcomer = _user(db, email, Role.candidate, password_hash)
            db.add(CandidateProfile(user_id=newcomer.id))

        employers = []
        for index, (name, industry, description) in enumerate(_COMPANIES):
            email = "demo-employer@example.com" if index == 0 else f"employer{index}@example.com"
            user = _user(db, email, Role.employer, password_hash)
            db.add(
                Company(
                    user_id=user.id,
                    name=name,
                    industry=industry,
                    description=description,
                    website="https://example.com",
                    contact_person="Отдел подбора",
                    contact_email=email,
                    contact_phone="+7 495 000-00-00",
                )
            )
            employers.append(user)
        # Потребности из тестового набора вакансий распределяются между работодателями.
        for index, vacancy in enumerate(VACANCIES):
            gold = vacancy["gold"]
            low, high = gold["salary"] or (None, None)
            db.add(
                Need(
                    employer_id=employers[index % len(employers)].id,
                    title=vacancy["title"],
                    text=vacancy["text"],
                    specialization=gold["specialization"],
                    grade=gold["grade"],
                    stack=gold["stack"],
                    work_formats=gold["work_formats"],
                    salary_from=low,
                    salary_to=high,
                )
            )
        offers = [
            (employers[0], InvitationStatus.sent, "Бэкенд-разработчик в платежи", 200_000, 280_000),
            (employers[1], InvitationStatus.viewed, "Python-разработчик, сервис маршрутов", 190_000, 250_000),
            (employers[2], InvitationStatus.declined, "Разработчик интеграций", 150_000, 180_000),
        ]
        for employer, status, title, low, high in offers:
            db.add(
                Invitation(
                    employer_id=employer.id,
                    candidate_id=demo.id,
                    title=title,
                    message="Здравствуйте! Нам подходит ваш профиль: команда из шести человек, задачи — "
                            "интеграции и внутренние сервисы. Будем рады обсудить детали.",
                    salary_from=low,
                    salary_to=high,
                    contact=employer.email,
                    status=status,
                    responded_at=utcnow() if status == InvitationStatus.declined else None,
                )
            )
        # Вакансии: по две на работодателя из того же набора; отклики — от кандидатов подходящей категории.
        for index, vacancy in enumerate(item for item in VACANCIES if item["gold"]["salary"]):
            if index >= 6:
                break
            gold = vacancy["gold"]
            published = Vacancy(
                employer_id=employers[index % len(employers)].id,
                title=vacancy["title"],
                description=vacancy["text"],
                specialization=gold["specialization"],
                grade=gold["grade"],
                stack=gold["stack"],
                work_formats=gold["work_formats"],
                salary_from=gold["salary"][0],
                salary_to=gold["salary"][1],
            )
            db.add(published)
            db.flush()
            fitting = db.scalars(
                select(CandidateCategory.user_id).where(
                    CandidateCategory.specialization == gold["specialization"],
                    CandidateCategory.grade == gold["grade"],
                    CandidateCategory.user_id != demo.id,
                )
            ).all()
            for position, candidate_id in enumerate(rng.sample(fitting, min(len(fitting), 3))):
                db.add(
                    Application(
                        vacancy_id=published.id,
                        candidate_id=candidate_id,
                        message="Здравствуйте! Мой опыт совпадает с задачами вакансии, буду рад обсудить.",
                        status=[InvitationStatus.sent, InvitationStatus.viewed, InvitationStatus.accepted][position],
                    )
                )
        # Регулярные задания: первое — от демо-работодателя по специализации демо-кандидата.
        for index, (specialization, title, text) in enumerate(_CHALLENGES):
            challenge = Challenge(
                employer_id=employers[index % len(employers)].id, title=title, text=text, specialization=specialization
            )
            db.add(challenge)
            db.flush()
            authors = db.scalars(
                select(CandidateCategory.user_id).where(
                    CandidateCategory.specialization == specialization, CandidateCategory.user_id != demo.id
                )
            ).all()
            for position, candidate_id in enumerate(rng.sample(authors, min(len(authors), 3))):
                db.add(
                    ChallengeAnswer(
                        challenge_id=challenge.id,
                        candidate_id=candidate_id,
                        text=_ANSWERS[position],
                        rating=[5, 3, None][position],
                        created_at=utcnow() - timedelta(days=rng.randint(1, 20)),
                    )
                )
        for item_id, shown in exposure.items():
            db.add(ItemExposure(item_id=item_id, shown=shown))
        db.commit()
        return {
            "candidates": db.scalar(select(func.count()).select_from(CandidateProfile)),
            "with_category": db.scalar(select(func.count()).select_from(CandidateCategory)),
            "attempts": db.scalar(select(func.count()).select_from(Assessment)),
            "needs": db.scalar(select(func.count()).select_from(Need)),
            "vacancies": db.scalar(select(func.count()).select_from(Vacancy)),
            "challenges": db.scalar(select(func.count()).select_from(Challenge)),
        }


if __name__ == "__main__":
    utf8_output()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--candidates", type=int, default=300)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--reset", action="store_true", help="удалить все данные и создать схему заново")
    args = parser.parse_args()

    if args.reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        if session.scalar(select(func.count()).select_from(User)):
            sys.exit("В базе уже есть пользователи. Запустите с --reset, чтобы удалить все данные и наполнить заново.")
    print(seed(args.candidates, args.seed))
    print(f"Пароль демо-записей: {PASSWORD}")
