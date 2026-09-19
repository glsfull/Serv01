from fastapi.testclient import TestClient


def test_register_login_and_current_user(client: TestClient) -> None:
    registration = client.post(
        "/api/auth/register",
        json={
            "email": "Alice@Example.COM",
            "password": "correct horse battery staple",
            "full_name": "Alice Example",
        },
    )

    assert registration.status_code == 201
    payload = registration.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]

    login = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "correct horse battery staple"},
    )
    assert login.status_code == 200

    current_user = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert current_user.status_code == 200
    assert current_user.json() == {
        "email": "alice@example.com",
        "full_name": "Alice Example",
        "id": current_user.json()["id"],
        "role": "operator",
        "is_active": True,
        "created_at": current_user.json()["created_at"],
    }


def test_registration_rejects_duplicate_email(client: TestClient) -> None:
    account = {
        "email": "owner@example.com",
        "password": "correct horse battery staple",
        "full_name": "Owner",
    }
    assert client.post("/api/auth/register", json=account).status_code == 201
    response = client.post("/api/auth/register", json=account)
    assert response.status_code == 409
    assert response.json()["detail"] == "An account with this email already exists"


def test_protected_endpoint_requires_valid_token(client: TestClient) -> None:
    assert client.get("/api/tasks").status_code == 401
    assert client.get("/api/tasks", headers={"Authorization": "Bearer invalid"}).status_code == 401
