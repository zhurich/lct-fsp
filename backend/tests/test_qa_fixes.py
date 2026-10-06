"""Регрессионные тесты по отчёту аудита docs/qa-2026-10-06/REPORT.md; номера QA — из отчёта."""

import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, BrokenBarrierError
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import mail
from app.core.config import Settings
from app.core.db import SessionLocal
from app.core.deps import ACCESS_COOKIE
from app.core.security import create_token
from app.modules.assessment import bank
from app.modules.assessment import router as assessment_router
from app.modules.assessment.models import Assessment, AttemptStatus
from app.modules.candidates.privacy import CONTACT_PLACEHOLDER, mask_contacts
from app.modules.candidates.resume import parse_resume
from app.modules.invitations.models import Invitation
from app.modules.matching.parser import parse_need
from app.modules.matching.ranking import CandidateData, Requirements, rank
from app.modules.vacancies.models import Application
from tests.test_flow import PASSWORD, login, signup, take_test

START = {"specialization": "backend", "grade": "junior", "stack": ["Python"]}
INVITATION = {"title": "Разработчик", "message": "Задачи команды", "salary_from": 100000, "salary_to": 150000,
              "contact": "hr@example.com"}
VACANCY = {"title": "Разработчик", "description": "Описание", "specialization": "backend", "grade": "junior",
           "salary_from": 100000, "salary_to": 150000}


def _wait(barrier: Barrier) -> None:
    # Если второй запрос до барьера не дошёл (его остановила более ранняя проверка), первый продолжает сам.
    try:
        barrier.wait(timeout=3)
    except BrokenBarrierError:
        pass


def _together(request) -> list[int]:
    with ThreadPoolExecutor(max_workers=2) as pool:
        return sorted(response.status_code for response in pool.map(lambda _: request(), range(2)))


def _employer_with_company(client, outbox, email):
    signup(client, outbox, email, "employer")
    client.put("/api/employer/company", json={"name": "ООО Проверка"})


def _published_candidate(client, outbox, email, **profile) -> int:
    signup(client, outbox, email, "candidate")
    take_test(client, "junior")
    saved = client.put(
        "/api/candidate/profile",
        json={"specialization": "backend", "stack": ["Python"], "is_published": True, **profile},
    )
    assert saved.status_code == 200, saved.text
    return client.get("/api/auth/me").json()["id"]


def test_qa01_parallel_starts_create_one_attempt(client, outbox):
    signup(client, outbox, "race-start@example.com", "candidate")
    user_id = client.get("/api/auth/me").json()["id"]
    barrier, original = Barrier(2), assessment_router._grade_locks

    def locks(*args, **kwargs):
        # Оба запроса уже убедились, что активной попытки нет.
        _wait(barrier)
        return original(*args, **kwargs)

    with patch.object(assessment_router, "_grade_locks", side_effect=locks):
        statuses = _together(lambda: client.post("/api/candidate/assessment", json=START))
    assert statuses == [201, 409]
    with SessionLocal() as db:
        active = db.scalar(
            select(func.count()).select_from(Assessment).where(
                Assessment.user_id == user_id, Assessment.status == AttemptStatus.in_progress
            )
        )
    assert active == 1


def test_qa02_parallel_answers_accept_only_one(client, outbox):
    signup(client, outbox, "race-answer@example.com", "candidate")
    attempt = client.post("/api/candidate/assessment", json=START).json()["active"]
    barrier, original = Barrier(2), assessment_router.adaptive.estimate

    def estimate(*args, **kwargs):
        # Оба запроса уже прошли проверку номера задания.
        _wait(barrier)
        return original(*args, **kwargs)

    answers = iter([0, 1])
    with patch.object(assessment_router.adaptive, "estimate", side_effect=estimate):
        statuses = _together(
            lambda: client.post(
                f"/api/candidate/assessment/{attempt['id']}/answer", json={"position": 1, "answer": next(answers)}
            )
        )
    assert statuses == [200, 409]
    with SessionLocal() as db:
        questions = db.get(Assessment, attempt["id"]).questions
    assert len(questions) == 2 and "answer" in questions[0] and "answer" not in questions[1]


def test_qa03_answer_outside_options_is_rejected_without_losing_question(client, outbox):
    signup(client, outbox, "range@example.com", "candidate")
    attempt = client.post("/api/candidate/assessment", json=START).json()["active"]
    url = f"/api/candidate/assessment/{attempt['id']}/answer"
    for wrong in (999, 4, -1):
        assert client.post(url, json={"position": 1, "answer": wrong}).status_code == 422
    state = client.get("/api/candidate/assessment").json()
    assert state["active"]["position"] == 1
    assert client.post(url, json={"position": 1, "answer": 3}).status_code == 200


def test_qa04_qa05_hidden_fields_and_contacts_in_free_text(client, outbox):
    candidate_id = _published_candidate(
        client,
        outbox,
        "private@example.com",
        experience_years=7,
        hidden_fields=["experience"],
        about="Пишу сервисы на Python. Контакт: qa-private@example.com, телефон +7 999 123 45 67, tg @private_dev",
    )
    _employer_with_company(client, outbox, "private-emp@example.com")
    vacancy = client.post("/api/employer/vacancies", json=VACANCY).json()

    card = next(item for item in client.get("/api/employer/candidates").json() if item["candidate_id"] == candidate_id)
    assert card["experience_years"] is None
    assert "Пишу сервисы на Python" in card["about"] and CONTACT_PLACEHOLDER in card["about"]
    for secret in ("qa-private@example.com", "999 123", "@private_dev"):
        assert secret not in card["about"]

    login(client, "private@example.com")
    assert client.post(f"/api/candidate/vacancies/{vacancy['id']}/apply", json={"message": ""}).status_code == 201
    login(client, "private-emp@example.com")
    application = client.get(f"/api/employer/vacancies/{vacancy['id']}/applications").json()[0]
    # Отклик раскрывает контакты, но не то, что кандидат скрыл настройками приватности.
    assert application["experience_years"] is None
    assert application["contacts"]["email"] == "private@example.com"


def test_qa05_mask_keeps_ordinary_text():
    text = "Опыт 5 лет, с 2019 по 2024 год работал в команде из 12 человек, Python 3.12, зарплата от 200 000"
    assert mask_contacts(text) == text
    stack = "Работаю с PostgreSQL, REST, Spring. Писал Telegram ботов и интеграцию с Telegram Bot API"
    assert mask_contacts(stack) == stack
    assert mask_contacts("telegram: dev_name, тг - other_name") == f"{CONTACT_PLACEHOLDER}, {CONTACT_PLACEHOLDER}"
    assert mask_contacts("пишите на t.me/dev_name или https://example.com/me") == (
        f"пишите на {CONTACT_PLACEHOLDER} или {CONTACT_PLACEHOLDER}"
    )


def test_qa06_secret_key_must_be_set():
    for value in ("", "short", "dev-secret-change-me-in-production-please"):
        with pytest.raises(ValidationError):
            Settings(secret_key=value, _env_file=None)
    assert Settings(secret_key="x" * 32, _env_file=None).secret_key


def test_qa07_mail_failure_does_not_block_registration(client, outbox, monkeypatch):
    data = {"email": "smtp-down@example.com", "password": PASSWORD, "role": "candidate", "consent": True}

    def broken(*args):
        raise ConnectionRefusedError("SMTP недоступен")

    monkeypatch.setattr(mail, "send_mail", broken)
    assert client.post("/api/auth/register", json=data).status_code == 503
    monkeypatch.setattr(mail, "send_mail", lambda to, subject, body: outbox.append({"to": to, "body": body}))
    assert client.post("/api/auth/register", json=data).status_code == 201
    assert outbox[-1]["to"] == "smtp-down@example.com"


def test_qa08_resend_and_login_are_rate_limited(client, outbox):
    data = {"email": "limit@example.com", "password": PASSWORD, "role": "candidate", "consent": True}
    assert client.post("/api/auth/register", json=data).status_code == 201
    # Письмо только что ушло при регистрации: повтор — не раньше чем через минуту.
    assert client.post("/api/auth/resend-verification", json={"email": data["email"]}).status_code == 429
    assert len(outbox) == 1
    # Для незарегистрированного адреса ответ и лимит те же.
    assert client.post("/api/auth/resend-verification", json={"email": "nobody@example.com"}).status_code == 200
    assert client.post("/api/auth/resend-verification", json={"email": "nobody@example.com"}).status_code == 429

    wrong = {"email": data["email"], "password": "wrong-password"}
    assert [client.post("/api/auth/login", json=wrong).status_code for _ in range(11)] == [401] * 10 + [429]


def _race_on_add(model, request) -> list[int]:
    """Два запроса одновременно доходят до сохранения строки model: оба уже прошли проверку на дубль."""
    barrier, original = Barrier(2), Session.add

    def add(self, instance, *args, **kwargs):
        if isinstance(instance, model):
            _wait(barrier)
        return original(self, instance, *args, **kwargs)

    with patch.object(Session, "add", add):
        return _together(request)


def test_qa09_qa10_parallel_invitations_and_applications(client, outbox):
    candidate_id = _published_candidate(client, outbox, "dup-cand@example.com")
    _employer_with_company(client, outbox, "dup-emp@example.com")
    vacancy = client.post("/api/employer/vacancies", json=VACANCY).json()

    invite = {**INVITATION, "candidate_id": candidate_id}
    assert _race_on_add(Invitation, lambda: client.post("/api/employer/invitations", json=invite)) == [201, 409]
    assert len(client.get("/api/employer/invitations").json()) == 1

    login(client, "dup-cand@example.com")
    url = f"/api/candidate/vacancies/{vacancy['id']}/apply"
    assert _race_on_add(Application, lambda: client.post(url, json={"message": ""})) == [201, 409]

    # После отказа кандидата работодатель может пригласить его снова.
    invitation_id = client.get("/api/candidate/invitations").json()[0]["id"]
    assert client.post(f"/api/candidate/invitations/{invitation_id}/decline").status_code == 200
    login(client, "dup-emp@example.com")
    assert client.post("/api/employer/invitations", json=invite).status_code == 201


def test_qa11_challenge_answer_needs_text_and_own_specialization(client, outbox):
    _employer_with_company(client, outbox, "task-emp@example.com")
    challenge = {"title": "Задание", "text": "Опишите подход к решению задачи из практики команды"}
    own = client.post("/api/employer/challenges", json={**challenge, "specialization": "backend"}).json()
    foreign = client.post("/api/employer/challenges", json={**challenge, "specialization": "mobile"}).json()

    signup(client, outbox, "task-cand@example.com", "candidate")
    take_test(client, "junior")
    answer = {"text": "Разобью задачу на шаги, оценю каждый и начну с самого рискованного участка."}
    assert client.post(f"/api/candidate/challenges/{own['id']}/answer", json={"text": " " * 60}).status_code == 422
    assert client.post(f"/api/candidate/challenges/{foreign['id']}/answer", json=answer).status_code == 404
    assert client.post(f"/api/candidate/challenges/{own['id']}/answer", json=answer).status_code == 201


def test_qa12_qa13_qa24_blank_text_and_huge_values_are_rejected(client, outbox):
    candidate_id = _published_candidate(client, outbox, "bounds-cand@example.com")
    profile = {"specialization": "backend", "stack": ["Python"]}
    for broken in (
        {"stack": ["x" * 20000]},
        {"stack": ["  "]},
        {"salary_expectation": 10**30},
        {"experience_years": 10**30},
    ):
        assert client.put("/api/candidate/profile", json={**profile, **broken}).status_code == 422, broken
    # QA-14: NaN и бесконечность в JSON.
    for value in ("NaN", "Infinity", "-Infinity"):
        response = client.put(
            "/api/candidate/profile",
            content='{"experience_years": %s}' % value,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422, value

    _employer_with_company(client, outbox, "bounds-emp@example.com")
    need = {"title": "Потребность", "specialization": "backend", "grade": "junior"}
    cases = [
        ("/api/employer/needs", {**need, "title": "   "}),
        ("/api/employer/needs", {**need, "salary_to": 10**30}),
        ("/api/employer/needs", {**need, "stack": ["x" * 61]}),
        ("/api/employer/vacancies", {**VACANCY, "title": "   "}),
        ("/api/employer/vacancies", {**VACANCY, "description": "\n\t "}),
        ("/api/employer/vacancies", {**VACANCY, "salary_to": 10**30}),
        ("/api/employer/challenges", {"title": " ", "text": "Условие задания не короче двадцати символов",
                                      "specialization": "backend"}),
        ("/api/employer/challenges", {"title": "Задание", "text": " " * 30, "specialization": "backend"}),
        ("/api/employer/invitations", {**INVITATION, "candidate_id": candidate_id, "title": "  "}),
        ("/api/employer/invitations", {**INVITATION, "candidate_id": candidate_id, "message": "  "}),
        ("/api/employer/invitations", {**INVITATION, "candidate_id": candidate_id, "contact": "  "}),
        ("/api/employer/invitations", {**INVITATION, "candidate_id": 10**30}),
    ]
    for url, body in cases:
        assert client.post(url, json=body).status_code == 422, body
    # Идентификатор вне диапазона — ошибка запроса, а не сервера.
    assert client.get(f"/api/employer/needs/{10**30}/matches").status_code == 422
    assert client.get(f"/api/employer/vacancies/{10**30}/applications").status_code == 422
    # Пробелы по краям обрезаются.
    assert client.post("/api/employer/needs", json={**need, "title": "  Бэкенд  "}).json()["title"] == "Бэкенд"


def test_qa18_study_years_are_not_experience():
    assert parse_resume("Образование: Университет 2018–2022\nОпыт работы отсутствует", 2026).experience_years == 0
    assert parse_resume("Образование: Университет 2018–2022; Опыт работы отсутствует", 2026).experience_years == 0
    resume = "Иван Петров\nОбразование\nМГУ, 2014–2018\nОпыт работы\nООО Ромашка, 2020–2023\nООО Лютик, 2023 — н.в."
    assert parse_resume(resume, 2026).experience_years == 6
    assert parse_resume("Навыки: Python\nКурсы 2019-2020", 2026).experience_years is None
    assert parse_resume("Опыт работы 3 года 6 месяцев\nОбразование: 2010-2015", 2026).experience_years == 3.5


def test_qa19_qa20_qa21_need_parser():
    assert parse_need("Нужен senior backend, наставничество junior-разработчиков. Python PostgreSQL.").grade == "senior"
    assert parse_need("Ищем тимлида: менторство для джунов и мидлов, код-ревью").grade == "senior"
    # Несколько грейдов как требование — по-прежнему берётся младший.
    assert parse_need("Ищем middle или senior разработчика").grade == "middle"
    assert parse_need("Junior Python-разработчик").grade == "junior"

    formats = lambda text: parse_need(text).work_formats  # noqa: E731
    assert formats("Нужен middle backend Python, удалённая работа невозможна, только офис.") == ["office"]
    assert formats("Работа не удалённая, офис в Москве") == ["office"]
    assert formats("Без удалёнки: гибрид или офис") == ["office", "hybrid"]
    assert formats("Удалённо или в офисе") == ["remote", "office"]
    assert formats("Только удалённая работа") == ["remote"]

    upper = parse_need("Нужен backend middle Python, зарплата до 250 тыс. руб.")
    assert (upper.salary_from, upper.salary_to) == (None, 250000)
    assert any("до 250 000" in note for note in upper.notes)
    both = parse_need("Зарплата 150–200 тыс. руб.")
    assert (both.salary_from, both.salary_to) == (150000, 200000)
    assert parse_need("Зарплата от 180 тыс").salary_from == 180000


def test_qa22_profile_strength_never_outweighs_a_missing_technology():
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    stack = ["Python", "PostgreSQL", "Docker", "Redis", "Kafka", "FastAPI", "Linux", "Git", "Kubernetes", "Celery"]
    achievements = [
        {"event": "Чемпионат", "discipline": "Продуктовое", "level": "federal", "place": 1, "date": "2026-05-01"}
    ]

    def candidate(skills, score, fsp):
        return CandidateData(
            specialization="backend", grade="middle", test_score=score, assigned_at=now - timedelta(days=5),
            stack=skills, work_formats=[], fsp_achievements=fsp,
        )

    for wanted in (stack, stack[:3], stack[:1]):
        need = Requirements(specialization="backend", grade="middle", stack=wanted)
        strong_but_partial = rank(need, candidate(wanted[:-1], 1.0, achievements), now)
        weak_but_full = rank(need, candidate(wanted, 0.35, []), now)
        assert weak_but_full.score > strong_but_partial.score, len(wanted)
    # Шкала сохраняется: при равном соответствии сильный профиль выше, идеальный кандидат получает 100.
    need = Requirements(specialization="backend", grade="middle", stack=stack)
    assert rank(need, candidate(stack, 0.9, []), now).score > rank(need, candidate(stack, 0.5, []), now).score
    perfect = CandidateData(
        specialization="backend", grade="middle", test_score=1.0, assigned_at=now, stack=stack, work_formats=[],
        fsp_achievements=[],
    )
    with patch("app.modules.matching.ranking.fsp_strength", return_value=1.0):
        assert rank(need, perfect, now).score == 100


def test_qa23_complexity_code_runs():
    for level in range(4):
        for seed in range(80):
            question = bank.ITEMS[f"common.complexity.{level}"].generate(random.Random(seed))
            scope = {"n": 6}
            exec(question.code, scope)  # noqa: S102 — код из собственного банка заданий
            if level == 3:
                function = next(value for name, value in scope.items() if callable(value) and name != "__builtins__")
                assert function(6) >= 1


def test_qa29_token_with_broken_subject_is_unauthorized(client, outbox):
    token = create_token("not-an-int", "access", timedelta(minutes=5))  # type: ignore[arg-type]
    client.cookies.set(ACCESS_COOKIE, token)
    assert client.get("/api/auth/me").status_code == 401


def test_qa2_01_logout_revokes_copied_token(client, outbox):
    # Повторный аудит 07.10.2026: токен, скопированный до выхода, после выхода не принимается.
    signup(client, outbox, "replay@example.com", "candidate")
    stolen = client.cookies.get(ACCESS_COOKIE)
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.set(ACCESS_COOKIE, stolen)
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/candidate/profile").status_code == 401

    # Выход закрывает только свою сессию: вторая, открытая с другого устройства, продолжает работать.
    client.cookies.clear()
    login(client, "replay@example.com")
    first = client.cookies.get(ACCESS_COOKIE)
    client.cookies.clear()
    login(client, "replay@example.com")
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.set(ACCESS_COOKIE, first)
    assert client.get("/api/auth/me").status_code == 200


def test_qa2_failed_test_locks_grade_only_in_its_specialization(client, outbox):
    # Провал теста на Middle по QA не закрывает Middle по бэкенду: срок пересдачи считается по специализации.
    signup(client, outbox, "cross@example.com", "candidate")
    state = take_test(client, "middle", correct=False, specialization="qa")

    def locked(specialization):
        return {item["grade"] for item in state["grades_by_specialization"][specialization] if item["available_from"]}

    assert locked("qa") == {"middle", "senior"} and locked("backend") == set()
    survey = {"specialization": "qa", "grade": "middle", "stack": []}
    assert client.post("/api/candidate/assessment", json=survey).status_code == 409
    state = take_test(client, "middle", specialization="backend")
    assert state["category"]["specialization"] == "backend" and state["category"]["grade"] == "middle"
    # Подтверждённая категория закрывает смену во всех специализациях, как и раньше; открыта только
    # досрочная попытка повышения в своей.
    open_grades = {
        (specialization, item["grade"])
        for specialization, grades in state["grades_by_specialization"].items()
        for item in grades
        if item["available_from"] is None
    }
    assert open_grades == {("backend", "senior")}


def test_qa2_01_signed_token_without_session_is_unauthorized(client, outbox):
    # Одной подписи мало: токен без открытой на сервере сессии не даёт доступа.
    signup(client, outbox, "nosession@example.com", "candidate")
    user_id = client.get("/api/auth/me").json()["id"]
    client.cookies.clear()
    client.cookies.set(ACCESS_COOKIE, create_token(user_id, "access", timedelta(minutes=5)))
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.set(ACCESS_COOKIE, create_token(user_id, "access", timedelta(minutes=5), "unknown-session"))
    assert client.get("/api/auth/me").status_code == 401
