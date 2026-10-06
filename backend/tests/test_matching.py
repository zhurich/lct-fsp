from datetime import datetime, timedelta, timezone

from app.modules.fsp.idp import provider
from app.modules.fsp.registry import MockRegistry, fsp_strength
from app.modules.matching.parser import parse_need
from app.modules.matching.ranking import CandidateData, Requirements, rank
from app.modules.reference.skills import extract_skills, normalize_skill
from tests.test_flow import link_fsp, login, signup, take_test

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def candidate(**overrides) -> CandidateData:
    data = {
        "specialization": "backend",
        "grade": "middle",
        "test_score": 0.55,
        "assigned_at": NOW - timedelta(days=10),
        "stack": ["python", "Postgres", "Docker"],
        "work_formats": ["remote"],
        "fsp_achievements": [],
    }
    return CandidateData(**{**data, **overrides})


def test_skills_are_normalized_and_extracted_from_text():
    assert normalize_skill(" постгрес ") == "PostgreSQL"
    assert normalize_skill("Erlang") == "Erlang"
    text = "Нужен React Native и TypeScript, бэкенд на C# (.NET), k8s. Знание JavaScript — плюс."
    assert extract_skills(text) == ["React Native", "TypeScript", "C#", ".NET", "Kubernetes", "JavaScript"]
    # Java не находится внутри JavaScript, React — внутри React Native.
    assert "Java" not in extract_skills(text) and "React" not in extract_skills(text)


def test_need_is_parsed_from_free_text():
    need = parse_need(
        "Ищем в команду платежей бэкенд-разработчика уровня middle: Python, FastAPI, PostgreSQL, Kafka. "
        "Удалённо или гибрид, вилка от 200 до 280 тыс. руб."
    )
    assert (need.specialization, need.grade) == ("backend", "middle")
    assert need.stack == ["Python", "FastAPI", "PostgreSQL", "Kafka"]
    assert need.work_formats == ["remote", "hybrid"]
    assert (need.salary_from, need.salary_to) == (200_000, 280_000)

    # Специализация по стеку, грейд по стажу; «от 3 до 5 лет» — не зарплата.
    need = parse_need("Нужен человек с опытом от 3 до 5 лет: React, TypeScript, Redux. Офис в Казани.")
    assert (need.specialization, need.grade, need.work_formats) == ("frontend", "senior", ["office"])
    assert need.salary_from is None

    need = parse_need("Аналитик данных, junior/middle, SQL и Pandas, зарплата 120 000 – 150 000 ₽")
    assert (need.specialization, need.grade) == ("data", "junior")
    assert (need.salary_from, need.salary_to) == (120_000, 150_000)

    empty = parse_need("Нужен хороший специалист в дружную команду")
    assert empty.specialization is None and empty.grade is None and len(empty.notes) == 2


def test_ranking_orders_by_fit_then_profile_strength():
    request = Requirements("backend", "middle", ["Python", "PostgreSQL", "Kafka"], ["remote"])
    full = rank(request, candidate(stack=["Python", "PostgreSQL", "Kafka"]), NOW)
    partial = rank(request, candidate(), NOW)
    adjacent = rank(request, candidate(grade="senior", test_score=0.8, stack=["Python", "PostgreSQL", "Kafka"]), NOW)
    assert full.score > partial.score and full.score > adjacent.score
    assert partial.matched_stack == ["Python", "PostgreSQL"]
    assert any("нет: Kafka" in reason for reason in partial.reasons)

    # Вне категории: другая специализация и грейд дальше смежного.
    assert rank(request, candidate(specialization="frontend"), NOW) is None
    assert rank(request, candidate(grade="intern"), NOW) is None

    # При равном соответствии выше тот, у кого сильнее подтверждённый профиль.
    medal = [{"event": "Чемпионат России", "discipline": "-", "level": "federal", "place": 1, "date": "2026-03-01"}]
    with_fsp = rank(request, candidate(fsp_achievements=medal), NOW)
    stronger_test = rank(request, candidate(test_score=0.64), NOW)
    stale = rank(request, candidate(assigned_at=NOW - timedelta(days=400)), NOW)
    assert with_fsp.score > partial.score and stronger_test.score > partial.score > stale.score
    # Нет истории ФСП — нет надбавки, но и упоминаний об этом в объяснении нет.
    assert not any("ФСП" in reason for reason in partial.reasons)
    assert {part["key"]: part["value"] for part in partial.breakdown}["fsp"] == 0


def test_mock_registry_is_deterministic_and_covers_empty_cases():
    registry = MockRegistry()
    assert registry.fetch("FSP-000007") is None
    assert registry.fetch("FSP-000123") == registry.fetch("FSP-000123")
    histories = [registry.fetch(f"FSP-{number:06d}") for number in range(1, 60) if number % 7]
    assert any(history == [] for history in histories) and any(history for history in histories)
    assert all(0 <= fsp_strength(history, NOW.date()) <= 1 for history in histories)


def test_need_selection_with_refinement_and_fsp_link(client, outbox):
    # Два бэкенд-мидла с разным стеком; у второго привязан ФСП ID с достижениями.
    signup(client, outbox, "m-plain@example.com", "candidate")
    client.put("/api/candidate/profile", json={"is_published": True, "work_formats": ["remote"]})
    take_test(client, "middle", stack=["Python", "Django"])
    plain_id = client.get("/api/auth/me").json()["id"]

    signup(client, outbox, "m-fsp@example.com", "candidate")
    client.put("/api/candidate/profile", json={"is_published": True, "work_formats": ["remote"]})
    take_test(client, "middle", stack=["питон", "fastapi", "postgres"])
    fsp_id = client.get("/api/auth/me").json()["id"]
    # Участник ФСП с достижениями: идентификатор мок-провайдер выводит из почты.
    emails = (f"m-fsp-{n}@fsp.example" for n in range(50))
    fsp_email = next(email for email in emails if MockRegistry().fetch(provider.participant(email)))
    assert link_fsp(client, fsp_email).status_code == 200
    assert client.get("/api/candidate/profile").json()["fsp_achievements"]

    # Чужой ФСП ID привязать нельзя.
    login(client, "m-plain@example.com")
    assert link_fsp(client, fsp_email).status_code == 409

    signup(client, outbox, "m-emp@example.com", "employer")
    parsed = client.post(
        "/api/employer/needs/parse", json={"text": "Middle backend: Python, FastAPI, PostgreSQL, удалёнка"}
    ).json()
    assert parsed["specialization"] == "backend" and parsed["grade"] == "middle"
    need = client.post(
        "/api/employer/needs",
        json={"title": "Бэкенд в платежи", **{key: parsed[key] for key in parsed if key != "notes"}},
    )
    assert need.status_code == 201, need.text
    url = f"/api/employer/needs/{need.json()['id']}"

    found = client.get(f"{url}/matches").json()
    order = [card["candidate_id"] for card in found["candidates"] if card["candidate_id"] in (plain_id, fsp_id)]
    assert order == [fsp_id, plain_id]
    top = found["candidates"][0]
    assert top["matched_stack"] == ["Python", "FastAPI", "PostgreSQL"] and top["fsp_linked"]
    assert [category["grade"] for category in found["categories"]] == ["junior", "middle", "senior"]
    assert not {"full_name", "phone", "telegram", "email"} & top.keys()

    # Уточнение не меняет потребность и размер исходной подборки.
    refined = client.get(f"{url}/matches", params={"fsp_only": True, "stack": ["FastAPI"]}).json()
    assert [card["candidate_id"] for card in refined["candidates"]] == [fsp_id]
    assert refined["total"] == found["total"] and refined["need"] == found["need"]
    bank = client.get("/api/employer/candidates", params={"specialization": "backend", "fsp_only": True}).json()
    assert fsp_id in [card["candidate_id"] for card in bank] and plain_id not in [card["candidate_id"] for card in bank]

    # Потребность видна только владельцу.
    signup(client, outbox, "m-emp2@example.com", "employer")
    assert client.get(f"{url}/matches").status_code == 404
    assert client.delete(url).status_code == 404
    assert client.get("/api/employer/needs").json() == []
    login(client, "m-emp@example.com")
    assert client.put(url, json={**need.json(), "grade": "senior"}).json()["grade"] == "senior"
    assert client.delete(url).status_code == 204
