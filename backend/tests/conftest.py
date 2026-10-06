import os
import tempfile

# База подменяется до импорта приложения: настройки читаются при импорте.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["SMTP_HOST"] = ""
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only-0123456789"

import pytest
from fastapi.testclient import TestClient

from app.core import mail
from app.main import app
from app.modules.auth.router import LIMITERS


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    # Счётчики частоты живут в памяти процесса и иначе переходили бы из теста в тест.
    for limiter in LIMITERS:
        limiter.reset()


@pytest.fixture
def outbox(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(mail, "send_mail", lambda to, subject, body: sent.append({"to": to, "body": body}))
    return sent


@pytest.fixture
def client(outbox):
    with TestClient(app) as test_client:
        yield test_client
