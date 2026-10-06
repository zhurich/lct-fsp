def register(client, outbox, email, role, password="password123"):
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "role": role, "consent": True},
    )
    assert response.status_code == 201, response.text
    return outbox[-1]["body"].split("token=")[1].split()[0]


def test_registration_requires_consent(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": "password123", "role": "candidate", "consent": False},
    )
    assert response.status_code == 422


def test_login_blocked_until_email_verified(client, outbox):
    token = register(client, outbox, "cand@example.com", "candidate")
    credentials = {"email": "cand@example.com", "password": "password123"}

    assert client.post("/api/auth/login", json=credentials).status_code == 403
    assert client.post("/api/auth/verify", json={"token": token}).status_code == 200
    assert client.post("/api/auth/login", json=credentials).status_code == 200
    assert client.get("/api/auth/me").json()["role"] == "candidate"

    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401


def test_duplicate_email_and_wrong_password(client, outbox):
    token = register(client, outbox, "dup@example.com", "candidate")
    client.post("/api/auth/verify", json={"token": token})

    again = client.post(
        "/api/auth/register",
        json={"email": "DUP@example.com", "password": "password123", "role": "employer", "consent": True},
    )
    assert again.status_code == 409
    wrong = client.post("/api/auth/login", json={"email": "dup@example.com", "password": "wrong-password"})
    assert wrong.status_code == 401


def test_access_token_is_not_accepted_as_verify_token(client, outbox):
    token = register(client, outbox, "tok@example.com", "candidate")
    client.post("/api/auth/verify", json={"token": token})
    client.post("/api/auth/login", json={"email": "tok@example.com", "password": "password123"})
    access = client.cookies.get("access_token")
    assert client.post("/api/auth/verify", json={"token": access}).status_code == 400


def test_cabinets_are_separated_by_role(client, outbox):
    token = register(client, outbox, "emp@example.com", "employer")
    client.post("/api/auth/verify", json={"token": token})
    client.post("/api/auth/login", json={"email": "emp@example.com", "password": "password123"})

    assert client.get("/api/candidate/profile").status_code == 403
    saved = client.put("/api/employer/company", json={"name": "ООО Ромашка", "industry": "Финтех"})
    assert saved.status_code == 200
    assert client.get("/api/employer/company").json()["name"] == "ООО Ромашка"


def test_candidate_profile_roundtrip_and_validation(client, outbox):
    token = register(client, outbox, "prof@example.com", "candidate")
    client.post("/api/auth/verify", json={"token": token})
    client.post("/api/auth/login", json={"email": "prof@example.com", "password": "password123"})

    assert client.get("/api/candidate/profile").json()["is_published"] is False
    bad = client.put("/api/candidate/profile", json={"specialization": "astrology"})
    assert bad.status_code == 422
    good = client.put(
        "/api/candidate/profile",
        json={"full_name": "Иван Иванов", "specialization": "backend", "stack": ["Python", "PostgreSQL"]},
    )
    assert good.status_code == 200
    assert client.get("/api/candidate/profile").json()["stack"] == ["Python", "PostgreSQL"]
