"""Правки по итогам сессии вопросов и ответов с организаторами: вход через ФСП ID, кандидаты с
неподтверждённым грейдом в выдаче, равный вес соревнований, демо-режим стенда."""

from datetime import date

from app.core.config import settings
from app.modules.fsp.idp import provider
from app.modules.fsp.registry import fsp_strength
from tests.test_flow import PASSWORD, fsp_callback, link_fsp, login, signup, take_test

TODAY = date(2026, 10, 1)


def result(place, level="regional", when="2026-05-01"):
    return {"event": "Кубок", "discipline": "-", "level": level, "place": place, "date": when, "team": False}


def test_fsp_strength_counts_results_not_competition_level():
    # Все соревнования равно важны: уровень на вес не влияет.
    assert fsp_strength([result(1, "regional")], TODAY) == fsp_strength([result(1, "federal")], TODAY)
    assert fsp_strength([result(1)], TODAY) > fsp_strength([result(3)], TODAY) > fsp_strength([result(None)], TODAY)
    # Свежий результат весит больше давнего, число результатов тоже учитывается.
    assert fsp_strength([result(1)], TODAY) > fsp_strength([result(1, when="2023-05-01")], TODAY)
    assert fsp_strength([result(2), result(2)], TODAY) > fsp_strength([result(2)], TODAY)
    # Одними участиями профиль не набить: двадцать явок слабее одного призового места.
    assert fsp_strength([result(None)] * 20, TODAY) < fsp_strength([result(3)], TODAY)


def test_login_through_fsp_id_creates_candidate_with_achievements(client):
    first = fsp_callback(client, "/api/auth/fsp/start", "newbie@fsp.example")
    assert first.status_code == 200, first.text
    assert first.json()["intent"] == "login" and first.json()["user"]["role"] == "candidate"
    profile = client.get("/api/candidate/profile").json()
    assert profile["fsp_id"] == provider.participant("newbie@fsp.example")

    # Повторный вход приводит в ту же учётную запись; по паролю в неё войти нельзя.
    client.post("/api/auth/logout")
    again = fsp_callback(client, "/api/auth/fsp/start", "newbie@fsp.example")
    assert again.json()["user"]["id"] == first.json()["user"]["id"]
    assert client.post("/api/auth/login", json={"email": "newbie@fsp.example", "password": ""}).status_code == 401
    # Единственный способ входа отвязать нельзя; достижения обновляются из реестра.
    assert client.delete("/api/candidate/fsp").status_code == 409
    assert client.post("/api/candidate/fsp/refresh").json()["fsp_synced_at"] >= profile["fsp_synced_at"]


def test_fsp_id_does_not_open_accounts_by_matching_email(client, outbox):
    signup(client, outbox, "owner@example.com", "candidate")
    client.post("/api/auth/logout")
    # Вход в ФСП ID с той же почтой не даёт доступа к учётной записи, созданной по паролю.
    assert fsp_callback(client, "/api/auth/fsp/start", "owner@example.com").status_code == 409
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/fsp-id/login", json={"email": "owner@example.com", "password": "wrong"}).status_code == 401

    # Код одноразовый, а привязку завершает только тот, кто её начал.
    login(client, "owner@example.com")
    state = client.get("/api/candidate/fsp/start").json()["url"].split("state=")[1]
    code = client.post(
        "/api/fsp-id/login", json={"email": "owner@example.com", "password": provider.DEMO_PASSWORD}
    ).json()["code"]
    client.post("/api/auth/logout")
    assert client.post("/api/auth/fsp/callback", json={"code": code, "state": state}).status_code == 401
    assert client.post("/api/auth/fsp/callback", json={"code": code, "state": state}).status_code == 400
    assert client.post("/api/auth/fsp/callback", json={"code": "x", "state": "forged"}).status_code == 400

    login(client, "owner@example.com")
    assert link_fsp(client, "owner@example.com").json()["intent"] == "link"
    assert client.delete("/api/candidate/fsp").json()["fsp_id"] is None


def test_unverified_grade_is_shown_below_verified_and_can_be_invited(client, outbox):
    signup(client, outbox, "unv-pass@example.com", "candidate")
    client.put("/api/candidate/profile", json={"is_published": True})
    take_test(client, "middle", specialization="mobile", stack=["Kotlin"])
    passed_id = client.get("/api/auth/me").json()["id"]

    signup(client, outbox, "unv-fail@example.com", "candidate")
    client.put("/api/candidate/profile", json={"is_published": True})
    take_test(client, "middle", correct=False, specialization="mobile", stack=["Kotlin", "Swift"])
    failed_id = client.get("/api/auth/me").json()["id"]

    # Не сдававший тест грейда не заявлял — его в выдаче нет.
    signup(client, outbox, "unv-none@example.com", "candidate")
    client.put("/api/candidate/profile", json={"is_published": True, "specialization": "mobile"})
    untested_id = client.get("/api/auth/me").json()["id"]

    signup(client, outbox, "unv-emp@example.com", "employer")
    client.put("/api/employer/company", json={"name": "ООО Пион"})
    bank = client.get("/api/employer/candidates", params={"specialization": "mobile"}).json()
    assert [card["candidate_id"] for card in bank] == [passed_id, failed_id]
    unverified = bank[1]
    assert unverified["verified"] is False and unverified["grade"] == "middle" and unverified["score"] is None
    assert "не подтверждён" in unverified["reasons"][0]["text"] and unverified["breakdown"] == []
    assert unverified["reasons"][0]["kind"] == "minus"

    need = {"title": "Мобильный разработчик", "specialization": "mobile", "grade": "middle", "stack": ["Swift"]}
    url = f"/api/employer/needs/{client.post('/api/employer/needs', json=need).json()['id']}/matches"
    found = client.get(url).json()
    # Полное покрытие стека не поднимает неподтверждённого в основную подборку и не меняет её размер.
    assert [card["candidate_id"] for card in found["candidates"]] == [passed_id] and found["total"] == 1
    assert [card["candidate_id"] for card in found["unverified"]] == [failed_id]
    assert found["unverified"][0]["matched_stack"] == ["Swift"]
    assert {item["grade"]: item["count"] for item in found["categories"]}["middle"] == 1
    assert client.get(url, params={"stack": ["Kotlin"], "grade": "senior"}).json()["unverified"] == []
    # Заявленный грейд дальше смежного от запроса в подборку не попадает.
    intern = client.post("/api/employer/needs", json={**need, "grade": "intern"}).json()["id"]
    assert client.get(f"/api/employer/needs/{intern}/matches").json()["unverified"] == []

    offer = {"title": "Dev", "message": "-", "salary_from": 1, "salary_to": 2, "contact": "-"}
    assert client.post("/api/employer/invitations", json={**offer, "candidate_id": failed_id}).status_code == 201
    assert client.post("/api/employer/invitations", json={**offer, "candidate_id": untested_id}).status_code == 404


def test_demo_mode_skips_mail_and_allows_test_reset(client, outbox, monkeypatch):
    signup(client, outbox, "demo-off@example.com", "candidate")
    assert client.get("/api/candidate/assessment").json()["demo_mode"] is False
    assert client.post("/api/candidate/assessment/reset").status_code == 404

    monkeypatch.setattr(settings, "demo_mode", True)
    sent = len(outbox)
    registered = client.post(
        "/api/auth/register",
        json={"email": "demo-on@example.com", "password": PASSWORD, "role": "candidate", "consent": True},
    )
    assert registered.json()["verified"] is True and len(outbox) == sent
    login(client, "demo-on@example.com")

    state = take_test(client, "junior")
    assert state["category"] and all(item["available_from"] for item in state["grades"][:1])
    state = client.post("/api/candidate/assessment/reset").json()
    assert state["category"] is None and state["history"] == []
    assert all(item["available_from"] is None for item in state["grades"])
