from fastapi.testclient import TestClient


def test_cookie_auth_and_minimal_web_workflow(client: TestClient) -> None:
    anonymous = client.get("/dashboard", follow_redirects=False)
    assert anonymous.status_code == 303
    assert anonymous.headers["location"] == "/login"

    registered = client.post(
        "/register",
        data={
            "email": "web@example.com",
            "password": "correct horse battery staple",
            "full_name": "Web User",
        },
        follow_redirects=False,
    )
    assert registered.status_code == 303
    assert registered.headers["location"] == "/dashboard"
    assert registered.cookies["serv01_access_token"]

    template = client.post(
        "/templates/new",
        data={"name": "Web profile", "email": "web@example.com"},
        follow_redirects=False,
    )
    assert template.status_code == 303

    created = client.post(
        "/tasks/new",
        data={
            "name": "Example crawl",
            "urls": "https://example.com",
            "template_id": "",
            "respect_robots_txt": "on",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    assert created.headers["location"].startswith("/tasks/")

    task_page = client.get(created.headers["location"])
    assert task_page.status_code == 200
    assert "Example crawl" in task_page.text
    assert "https://example.com" in task_page.text


def test_api_login_sets_http_only_cookie(client: TestClient) -> None:
    client.post(
        "/api/auth/register",
        json={
            "email": "cookie@example.com",
            "password": "correct horse battery staple",
            "full_name": "Cookie User",
        },
    )
    response = client.post(
        "/api/auth/login",
        json={"email": "cookie@example.com", "password": "correct horse battery staple"},
    )

    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert response.cookies["serv01_access_token"]
