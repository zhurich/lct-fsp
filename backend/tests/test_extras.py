from datetime import datetime, timedelta, timezone

from app.modules.matching.ranking import CandidateData, Requirements, rank
from tests.test_flow import login, signup, take_test

VACANCY = {
    "title": "QA-инженер",
    "description": "Автотесты для личного кабинета",
    "specialization": "qa",
    "grade": "junior",
    "stack": ["pytest"],
    "salary_from": 90000,
    "salary_to": 120000,
}


def test_vacancy_application_flow(client, outbox):
    signup(client, outbox, "vac-emp@example.com", "employer")
    assert client.post("/api/employer/vacancies", json=VACANCY).status_code == 409
    client.put("/api/employer/company", json={"name": "ООО Вереск"})
    assert client.post("/api/employer/vacancies", json={**VACANCY, "salary_to": 10}).status_code == 422
    no_salary = {key: value for key, value in VACANCY.items() if not key.startswith("salary")}
    assert client.post("/api/employer/vacancies", json=no_salary).status_code == 422
    vacancy_id = client.post("/api/employer/vacancies", json=VACANCY).json()["id"]

    signup(client, outbox, "vac-cand@example.com", "candidate")
    client.put("/api/candidate/profile", json={"full_name": "Олег Тестов", "phone": "+7 900 111-22-33"})
    listed = next(item for item in client.get("/api/candidate/vacancies").json() if item["id"] == vacancy_id)
    assert listed["company_name"] == "ООО Вереск" and listed["application_status"] is None
    # Без подтверждённой категории откликнуться нельзя.
    apply_url = f"/api/candidate/vacancies/{vacancy_id}/apply"
    assert client.post(apply_url, json={"message": "Хочу к вам"}).status_code == 409
    take_test(client, "junior", specialization="qa", stack=["pytest"])
    listed = client.get("/api/candidate/vacancies", params={"specialization": "qa"}).json()
    assert listed[0]["id"] == vacancy_id and listed[0]["fits_category"]
    assert client.post(apply_url, json={"message": "Хочу к вам"}).status_code == 201
    assert client.post(apply_url, json={}).status_code == 409
    assert client.get("/api/candidate/applications").json()[0]["status"] == "sent"

    login(client, "vac-emp@example.com")
    assert client.get("/api/employer/vacancies").json()[0]["applications_new"] == 1
    application = client.get(f"/api/employer/vacancies/{vacancy_id}/applications").json()[0]
    # Кандидат откликнулся сам — контакты открыты сразу; профиль при этом не опубликован.
    assert application["contacts"]["full_name"] == "Олег Тестов" and application["grade"] == "junior"
    assert application["status"] == "sent"
    assert client.get("/api/employer/vacancies").json()[0]["applications_new"] == 0
    assert client.post(f"/api/employer/applications/{application['id']}/accept").status_code == 204
    assert client.post(f"/api/employer/applications/{application['id']}/decline").status_code == 409
    # Закрытая вакансия пропадает из списка, отклик остаётся.
    assert client.put(f"/api/employer/vacancies/{vacancy_id}", json={**VACANCY, "is_open": False}).status_code == 200

    signup(client, outbox, "vac-emp2@example.com", "employer")
    assert client.get(f"/api/employer/vacancies/{vacancy_id}/applications").status_code == 404
    assert client.post(f"/api/employer/applications/{application['id']}/accept").status_code == 404

    login(client, "vac-cand@example.com")
    assert vacancy_id not in [item["id"] for item in client.get("/api/candidate/vacancies").json()]
    assert client.get("/api/candidate/applications").json()[0]["status"] == "accepted"

    # Удаление работодателя убирает его вакансии вместе с откликами.
    login(client, "vac-emp@example.com")
    assert client.delete("/api/auth/me").status_code == 204
    login(client, "vac-cand@example.com")
    assert client.get("/api/candidate/applications").json() == []


def test_challenge_answers_refresh_profile(client, outbox):
    signup(client, outbox, "ch-emp@example.com", "employer")
    client.put("/api/employer/company", json={"name": "ООО Мята"})
    task = {"title": "Медленный отчёт", "text": "Отчёт строится 40 секунд. С чего начнёте разбор?", "specialization": "data"}
    challenge_id = client.post("/api/employer/challenges", json=task).json()["id"]
    client.post("/api/employer/challenges", json={**task, "specialization": "qa"})

    signup(client, outbox, "ch-cand@example.com", "candidate")
    assert client.get("/api/candidate/challenges").json() == []
    client.put("/api/candidate/profile", json={"is_published": True})
    take_test(client, "junior", specialization="data", stack=["SQL"])
    candidate_id = client.get("/api/auth/me").json()["id"]
    offered = client.get("/api/candidate/challenges").json()
    assert [item["id"] for item in offered] == [challenge_id] and offered[0]["company_name"] == "ООО Мята"
    answer_url = f"/api/candidate/challenges/{challenge_id}/answer"
    assert client.post(answer_url, json={"text": "Не знаю"}).status_code == 422
    solution = "Сначала посмотрю план запроса и время по этапам, затем проверю индексы и объём выборки."
    assert client.post(answer_url, json={"text": solution}).status_code == 201
    assert client.post(answer_url, json={"text": solution}).status_code == 409
    assert client.get("/api/candidate/challenges").json() == []

    login(client, "ch-emp@example.com")
    answer = client.get(f"/api/employer/challenges/{challenge_id}/answers").json()[0]
    assert answer["candidate_id"] == candidate_id and answer["grade"] == "junior" and answer["in_bank"]
    assert not {"full_name", "email", "phone"} & answer.keys()
    assert client.put(f"/api/employer/answers/{answer['id']}/rating", json={"rating": 6}).status_code == 422
    assert client.put(f"/api/employer/answers/{answer['id']}/rating", json={"rating": 5}).status_code == 204
    card = next(
        item
        for item in client.get("/api/employer/candidates", params={"specialization": "data"}).json()
        if item["candidate_id"] == candidate_id
    )
    assert any("задания работодателей: 1, средняя оценка работодателей 5.0" in reason["text"] for reason in card["reasons"])

    login(client, "ch-cand@example.com")
    assert client.get("/api/candidate/answers").json()[0]["rating"] == 5


def test_recent_answer_restores_freshness():
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    stale = {
        "specialization": "backend",
        "grade": "middle",
        "test_score": 0.55,
        "assigned_at": now - timedelta(days=400),
        "stack": [],
        "work_formats": [],
        "fsp_achievements": [],
    }
    request = Requirements("backend", "middle")
    idle = rank(request, CandidateData(**stale), now)
    active = rank(request, CandidateData(**stale, last_answer_at=now - timedelta(days=5), answers_total=1), now)
    assert active.score > idle.score
