import io

import pytest
from fpdf import FPDF
from pypdf import PdfReader

from app.modules.candidates.pdf import PdfUnavailable, _fonts
from app.modules.candidates.resume import parse_resume
from tests.test_flow import link_fsp, login, signup, take_test

RESUME = """Смирнова Анна Сергеевна
Python-разработчик, middle
Телефон: +7 (912) 345-67-89, почта anna.smirnova@example.com, Telegram: @anna_dev
Город: Казань. Готова к удалённой работе или гибриду.

О себе
Четыре года пишу серверную часть на Python. Люблю наводить порядок в коде и данных.

Опыт работы
2021 — настоящее время. ООО «Ромашка», бэкенд-разработчик. FastAPI, PostgreSQL, Kafka, Docker.
Провожу код-ревью, наставник для двух стажёров.
2019 — 2021. Студия «Лютик», младший разработчик. Django, MySQL.

Навыки
Python, FastAPI, Django, PostgreSQL, Redis, Docker, Git
Личные качества: ответственность, работа в команде, внимание к деталям
"""


def resume_pdf(text: str) -> bytes:
    try:
        regular, _ = _fonts()
    except PdfUnavailable:
        pytest.skip("нет шрифта с кириллицей")
    pdf = FPDF()
    pdf.add_font("main", "", regular)
    pdf.add_page()
    pdf.set_font("main", size=11)
    pdf.multi_cell(0, 6, text)
    return bytes(pdf.output())


def test_resume_fields_are_recognized():
    resume = parse_resume(RESUME, current_year=2026)
    assert resume.full_name == "Смирнова Анна Сергеевна"
    assert resume.phone == "+7 (912) 345-67-89" and resume.telegram == "@anna_dev" and resume.city == "Казань"
    assert (resume.specialization, resume.claimed_grade) == ("backend", "middle")
    assert {"Python", "FastAPI", "PostgreSQL", "Kafka", "Docker", "Django"} <= set(resume.stack)
    # Стаж не указан явно — складывается из периодов работы: 2019–2026.
    assert resume.experience_years == 7
    assert {"Разработчик", "Наставник", "Ревьюер"} <= set(resume.roles)
    assert resume.soft_skills == ["Работа в команде", "Ответственность", "Внимание к деталям"]
    assert resume.about.startswith("Четыре года") and "Опыт работы" not in resume.about
    assert set(resume.work_formats) == {"remote", "hybrid"}

    # Адрес почты не принимается за Telegram, пустое резюме не ломает разбор.
    assert parse_resume("Иван Петров\nivan@example.com\nопыт работы 3 года 6 месяцев", 2026).telegram == ""
    sparse = parse_resume("Просто текст без полезных сведений", 2026)
    assert sparse.full_name == "" and sparse.notes[-1].startswith("Не распознано")


def test_resume_upload_and_profile_pdf(client, outbox):
    signup(client, outbox, "pdf-cand@example.com", "candidate")
    parsed = client.post(
        "/api/candidate/profile/resume", files={"file": ("cv.pdf", resume_pdf(RESUME), "application/pdf")}
    )
    assert parsed.status_code == 200, parsed.text
    assert parsed.json()["full_name"] == "Смирнова Анна Сергеевна" and "Python" in parsed.json()["stack"]
    # Разбор ничего не сохраняет: профиль пуст, пока кандидат сам его не сохранит.
    assert client.get("/api/candidate/profile").json()["full_name"] == ""
    not_pdf = client.post("/api/candidate/profile/resume", files={"file": ("cv.pdf", b"hello", "application/pdf")})
    assert not_pdf.status_code == 422

    client.put("/api/candidate/profile", json={"full_name": "Анна Смирнова", "stack": ["Python"], "city": "Казань"})
    take_test(client, "junior")
    link_fsp(client, "pdf-cand@fsp.example")
    response = client.get("/api/candidate/profile/pdf")
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)
    assert "Анна Смирнова" in text and "Junior" in text and "pdf-cand@example.com" in text
    # Собственный PDF-профиль распознаётся обратно: стаж «г.» не принимается за город.
    again = client.post(
        "/api/candidate/profile/resume", files={"file": ("p.pdf", response.content, "application/pdf")}
    ).json()
    assert again["city"] == "Казань" and "Python" in again["stack"]
    short = parse_resume("Пётр Ильин\nСтаж: 5,5 г.\nСтек: Go", 2026)
    assert short.city == "" and short.experience_years == 5.5


def test_hidden_fields_are_not_shown_or_scored(client, outbox):
    signup(client, outbox, "priv-cand@example.com", "candidate")
    profile = {"is_published": True, "city": "Тула", "about": "Секрет", "experience_years": 4, "work_formats": ["office"]}
    client.put("/api/candidate/profile", json=profile)
    take_test(client, "junior", specialization="devops", stack=["Linux"])
    link_fsp(client, "priv-cand@fsp.example")
    candidate_id = client.get("/api/auth/me").json()["id"]
    assert client.put("/api/candidate/profile", json={"hidden_fields": ["salary"]}).status_code == 422

    def card():
        login(client, "priv-emp@example.com")
        found = client.get("/api/employer/candidates", params={"specialization": "devops"}).json()
        return next(item for item in found if item["candidate_id"] == candidate_id)

    signup(client, outbox, "priv-emp@example.com", "employer")
    visible = card()
    assert visible["city"] == "Тула" and visible["fsp_linked"]

    login(client, "priv-cand@example.com")
    hidden_all = {**profile, "stack": ["Linux"], "hidden_fields": ["city", "about", "experience", "work_formats", "fsp"]}
    assert client.put("/api/candidate/profile", json=hidden_all).status_code == 200
    hidden = card()
    assert (hidden["city"], hidden["about"], hidden["experience_years"], hidden["work_formats"]) == ("", "", None, [])
    assert not hidden["fsp_linked"] and hidden["fsp_achievements"] == []
    assert not any("ФСП" in reason for reason in hidden["reasons"])
    # Стек и категория видны всегда.
    assert hidden["stack"] == ["Linux"] and hidden["grade"] == "junior"


def test_account_deletion_removes_all_personal_data(client, outbox):
    signup(client, outbox, "gone-cand@example.com", "candidate")
    client.put("/api/candidate/profile", json={"is_published": True, "full_name": "Удаляемый"})
    take_test(client, "junior", specialization="analyst")
    candidate_id = client.get("/api/auth/me").json()["id"]
    assert client.get("/api/auth/me").json()["consent_at"]

    signup(client, outbox, "gone-emp@example.com", "employer")
    client.put("/api/employer/company", json={"name": "ООО Клевер"})
    offer = {"candidate_id": candidate_id, "title": "A", "message": "-", "salary_from": 1, "salary_to": 2, "contact": "-"}
    assert client.post("/api/employer/invitations", json=offer).status_code == 201

    login(client, "gone-cand@example.com")
    assert client.delete("/api/auth/me").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "gone-cand@example.com", "password": "password123"}).status_code == 401

    login(client, "gone-emp@example.com")
    assert client.get("/api/employer/invitations").json() == []
    found = client.get("/api/employer/candidates", params={"specialization": "analyst"}).json()
    assert candidate_id not in [item["candidate_id"] for item in found]
