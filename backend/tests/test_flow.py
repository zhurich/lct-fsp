from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from app.core.config import settings
from app.core.db import SessionLocal, utcnow
from app.modules.assessment import adaptive
from app.modules.assessment.models import Assessment, CandidateCategory
from app.modules.fsp.idp import provider

PASSWORD = "password123"


def signup(client, outbox, email, role):
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD, "role": role, "consent": True})
    token = outbox[-1]["body"].split("token=")[1].split()[0]
    client.post("/api/auth/verify", json={"token": token})
    login(client, email)


def login(client, email):
    assert client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200


def fsp_callback(client, start_url, email):
    """Проходит вход на странице ФСП ID и возвращается на платформу с кодом."""
    state = parse_qs(urlsplit(client.get(start_url).json()["url"]).query)["state"][0]
    code = client.post("/api/fsp-id/login", json={"email": email, "password": provider.DEMO_PASSWORD}).json()["code"]
    return client.post("/api/auth/fsp/callback", json={"code": code, "state": state})


def link_fsp(client, email):
    """Привязывает к текущему кандидату ФСП ID участника с этой почтой."""
    return fsp_callback(client, "/api/candidate/fsp/start", email)


def take_test(client, grade, correct=True, specialization="backend", stack=("Python", "PostgreSQL")):
    """Проходит адаптивный тест до конца: на все задания отвечает верно либо на все неверно."""
    started = client.post(
        "/api/candidate/assessment",
        json={"specialization": specialization, "grade": grade, "stack": list(stack)},
    )
    assert started.status_code == 201, started.text
    state = started.json()
    while state["active"]:
        attempt = state["active"]
        assert "correct" not in attempt["question"]
        with SessionLocal() as db:
            right = db.get(Assessment, attempt["id"]).questions[-1]["correct"]
        answered = client.post(
            f"/api/candidate/assessment/{attempt['id']}/answer",
            json={"position": attempt["position"], "answer": right if correct else (right + 1) % 4},
        )
        assert answered.status_code == 200, answered.text
        state = answered.json()
    return state


def test_end_to_end_invitation_flow(client, outbox):
    signup(client, outbox, "flow-cand@example.com", "candidate")
    client.put(
        "/api/candidate/profile",
        json={"full_name": "Анна Смирнова", "phone": "+7 900 000-00-00", "telegram": "@anna", "is_published": True},
    )
    state = take_test(client, "middle")
    assert state["category"]["grade"] == "middle"
    assert state["history"][0]["status"] == "passed"
    candidate_id = client.get("/api/auth/me").json()["id"]

    signup(client, outbox, "flow-emp@example.com", "employer")
    found = client.get(
        "/api/employer/candidates", params={"specialization": "backend", "grade": "middle", "stack": ["python"]}
    ).json()
    card = next(item for item in found if item["candidate_id"] == candidate_id)
    assert card["matched_stack"] == ["Python"]
    assert card["invitation_status"] is None
    assert not {"full_name", "phone", "telegram", "email"} & card.keys()
    assert client.get("/api/employer/candidates", params={"stack": ["cobol"]}).json() == []

    offer = {
        "candidate_id": candidate_id,
        "title": "Python-разработчик",
        "message": "Команда платежей",
        "salary_from": 200000,
        "salary_to": 260000,
        "contact": "hr@romashka.example",
    }
    # Без названия компании приглашать нельзя, как и с перевёрнутой вилкой.
    assert client.post("/api/employer/invitations", json=offer).status_code == 409
    client.put("/api/employer/company", json={"name": "ООО Ромашка"})
    assert client.post("/api/employer/invitations", json={**offer, "salary_to": 100}).status_code == 422
    assert client.post("/api/employer/invitations", json=offer).status_code == 201
    assert client.post("/api/employer/invitations", json=offer).status_code == 409
    sent = client.get("/api/employer/invitations").json()[0]
    assert sent["status"] == "sent" and sent["contacts"] is None

    login(client, "flow-cand@example.com")
    inbox = client.get("/api/candidate/invitations").json()
    assert inbox[0]["company_name"] == "ООО Ромашка" and inbox[0]["status"] == "sent"
    assert client.get("/api/candidate/invitations").json()[0]["status"] == "viewed"
    assert client.post(f"/api/candidate/invitations/{inbox[0]['id']}/accept").json()["status"] == "accepted"
    assert client.post(f"/api/candidate/invitations/{inbox[0]['id']}/decline").status_code == 409

    login(client, "flow-emp@example.com")
    accepted = client.get("/api/employer/invitations").json()[0]
    assert accepted["contacts"] == {
        "full_name": "Анна Смирнова",
        "email": "flow-cand@example.com",
        "phone": "+7 900 000-00-00",
        "telegram": "@anna",
    }


def test_unpublished_or_untested_candidate_is_hidden(client, outbox):
    signup(client, outbox, "hidden-cand@example.com", "candidate")
    take_test(client, "junior", specialization="qa")
    candidate_id = client.get("/api/auth/me").json()["id"]

    signup(client, outbox, "hidden-emp@example.com", "employer")
    client.put("/api/employer/company", json={"name": "ООО Лютик"})
    ids = [item["candidate_id"] for item in client.get("/api/employer/candidates").json()]
    assert candidate_id not in ids
    offer = {"candidate_id": candidate_id, "title": "QA", "message": "-", "salary_from": 1, "salary_to": 2, "contact": "-"}
    assert client.post("/api/employer/invitations", json=offer).status_code == 404


def test_candidate_cannot_answer_foreign_invitation(client, outbox):
    signup(client, outbox, "own-cand@example.com", "candidate")
    client.put("/api/candidate/profile", json={"is_published": True})
    take_test(client, "junior")
    candidate_id = client.get("/api/auth/me").json()["id"]
    signup(client, outbox, "own-emp@example.com", "employer")
    client.put("/api/employer/company", json={"name": "ООО Василёк"})
    offer = {"candidate_id": candidate_id, "title": "Dev", "message": "-", "salary_from": 1, "salary_to": 2, "contact": "-"}
    invitation_id = client.post("/api/employer/invitations", json=offer).json()["id"]

    signup(client, outbox, "other-cand@example.com", "candidate")
    assert client.get("/api/candidate/invitations").json() == []
    assert client.post(f"/api/candidate/invitations/{invitation_id}/accept").status_code == 404


def test_failed_test_keeps_lower_grades_open(client, outbox):
    signup(client, outbox, "fail-cand@example.com", "candidate")
    state = take_test(client, "middle", correct=False)
    assert state["category"] is None
    locked = {item["grade"] for item in state["grades"] if item["available_from"]}
    assert locked == {"middle", "senior"}
    survey = {"specialization": "backend", "grade": "senior", "stack": []}
    assert client.post("/api/candidate/assessment", json=survey).status_code == 409

    # Тест на грейд ниже доступен сразу; после присвоения категории смена грейда закрыта на срок cooldown.
    state = take_test(client, "junior")
    assert state["category"]["grade"] == "junior"
    assert client.post("/api/candidate/assessment", json={**survey, "grade": "intern"}).status_code == 409

    # Срок вышел: попытка повысить грейд разрешена, а её провал не понижает имеющуюся категорию.
    user_id = client.get("/api/auth/me").json()["id"]
    long_ago = utcnow() - timedelta(days=settings.grade_change_cooldown_days + 1)
    with SessionLocal() as db:
        db.get(CandidateCategory, user_id).assigned_at = long_ago
        for attempt in db.query(Assessment).filter_by(user_id=user_id):
            attempt.finished_at = long_ago
        db.commit()
    state = take_test(client, "senior", correct=False)
    assert state["category"]["grade"] == "junior"


def test_confident_result_offers_one_early_upgrade(client, outbox):
    signup(client, outbox, "up-cand@example.com", "candidate")
    state = take_test(client, "junior")
    assert state["category"]["upgrade_offer"] is True
    assert state["history"][0]["estimated_grade"] == "senior"
    open_grades = [item["grade"] for item in state["grades"] if item["available_from"] is None]
    assert open_grades == ["middle"]

    # Предложение действует только для подтверждённой специализации и сгорает после одной попытки.
    survey = {"specialization": "frontend", "grade": "middle", "stack": []}
    assert client.post("/api/candidate/assessment", json=survey).status_code == 409
    state = take_test(client, "middle", correct=False)
    assert state["category"]["grade"] == "junior"
    assert state["category"]["upgrade_offer"] is False
    assert all(item["available_from"] for item in state["grades"])


def test_questions_are_not_repeated_within_and_across_attempts(client, outbox):
    signup(client, outbox, "seen-cand@example.com", "candidate")
    take_test(client, "senior", correct=False)
    take_test(client, "junior", correct=False)
    user_id = client.get("/api/auth/me").json()["id"]
    with SessionLocal() as db:
        first, second = [
            [question["item_id"] for question in attempt.questions]
            for attempt in db.query(Assessment).filter_by(user_id=user_id).order_by(Assessment.id)
        ]
    assert len(set(first)) == len(first) == adaptive.TEST_LENGTH
    # Профильных заданий в тесте треть; общие во второй попытке берутся из ещё не виденных.
    assert sum(not item.startswith("common.") for item in first) == adaptive.TEST_LENGTH // 3
    assert not {item for item in first if item.startswith("common.")} & set(second)


def test_expired_attempt_counts_as_failed(client, outbox):
    signup(client, outbox, "late-cand@example.com", "candidate")
    survey = {"specialization": "frontend", "grade": "intern", "stack": []}
    attempt = client.post("/api/candidate/assessment", json=survey).json()["active"]
    assert client.post("/api/candidate/assessment", json=survey).status_code == 409
    url = f"/api/candidate/assessment/{attempt['id']}/answer"
    assert client.post(url, json={"position": 2, "answer": 0}).status_code == 409
    with SessionLocal() as db:
        db.get(Assessment, attempt["id"]).expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert client.post(url, json={"position": 1, "answer": 0}).status_code == 409
    state = client.get("/api/candidate/assessment").json()
    assert state["active"] is None and state["history"][0]["status"] == "failed"
    assert state["history"][0]["estimated_grade"] is None
