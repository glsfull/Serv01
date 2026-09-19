from fastapi.testclient import TestClient


def create_task(client: TestClient, headers: dict[str, str], **overrides: object) -> dict:
    payload: dict[str, object] = {
        "name": "Find partner sites",
        "keywords": ["industrial widgets", "widget distributors"],
        "search_engine": "google",
        "search_depth": 10,
        "region": "US",
        "language": "en",
        "action_type": "crawl",
        "max_sites": 25,
        "max_actions": 100,
        "max_runtime_minutes": 30,
        "schedule_type": "once",
        "respect_robots_txt": True,
    }
    payload.update(overrides)
    response = client.post("/api/tasks", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_task_crud_clone_and_lifecycle(client: TestClient, auth_headers: dict[str, str]) -> None:
    task = create_task(client, auth_headers)
    task_id = task["id"]
    assert task["status"] == "draft"
    assert task["keywords"] == ["industrial widgets", "widget distributors"]

    listed = client.get("/api/tasks", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == task_id
    assert listed.json()["total"] == 1

    updated = client.patch(f"/api/tasks/{task_id}", headers=auth_headers, json={"max_sites": 50})
    assert updated.status_code == 200
    assert updated.json()["max_sites"] == 50

    started = client.post(f"/api/tasks/{task_id}/start", headers=auth_headers)
    assert started.status_code == 200
    assert started.json()["status"] == "running"
    assert started.json()["started_at"] is not None

    immutable = client.patch(
        f"/api/tasks/{task_id}", headers=auth_headers, json={"name": "Cannot change"}
    )
    assert immutable.status_code == 409

    paused = client.post(f"/api/tasks/{task_id}/pause", headers=auth_headers)
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    resumed = client.post(f"/api/tasks/{task_id}/start", headers=auth_headers)
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "running"

    stopped = client.post(f"/api/tasks/{task_id}/stop", headers=auth_headers)
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"
    assert stopped.json()["stopped_at"] is not None

    cloned = client.post(f"/api/tasks/{task_id}/clone", headers=auth_headers)
    assert cloned.status_code == 201
    assert cloned.json()["id"] != task_id
    assert cloned.json()["name"] == "Find partner sites (copy)"
    assert cloned.json()["status"] == "draft"

    assert client.delete(f"/api/tasks/{task_id}", headers=auth_headers).status_code == 204


def test_task_validation_requires_cron_expression(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/tasks",
        headers=auth_headers,
        json={
            "name": "Scheduled task",
            "keywords": ["widgets"],
            "search_engine": "yandex",
            "search_depth": 50,
            "action_type": "crawl",
            "schedule_type": "cron",
        },
    )
    assert response.status_code == 422


def test_task_rejects_whitespace_name_and_null_required_update(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    invalid_name = client.post(
        "/api/tasks",
        headers=auth_headers,
        json={"name": "   ", "keywords": ["widgets"]},
    )
    assert invalid_name.status_code == 422

    task = create_task(client, auth_headers)
    invalid_update = client.patch(
        f"/api/tasks/{task['id']}",
        headers=auth_headers,
        json={"max_sites": None},
    )
    assert invalid_update.status_code == 422


def test_task_rejects_template_owned_by_another_user(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    other_registration = client.post(
        "/api/auth/register",
        json={
            "email": "other@example.com",
            "password": "correct horse battery staple",
            "full_name": "Other User",
        },
    )
    other_headers = {"Authorization": f"Bearer {other_registration.json()['access_token']}"}
    template = client.post(
        "/api/templates",
        headers=other_headers,
        json={"name": "Private", "email": "private@example.com"},
    ).json()

    response = client.post(
        "/api/tasks",
        headers=auth_headers,
        json={
            "name": "Invalid template",
            "keywords": ["widgets"],
            "action_type": "form_submission",
            "template_id": template["id"],
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Template not found"


def test_users_cannot_see_each_others_tasks(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    private_task = create_task(client, auth_headers)
    registration = client.post(
        "/api/auth/register",
        json={
            "email": "other@example.com",
            "password": "correct horse battery staple",
            "full_name": "Other User",
        },
    )
    other_headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}

    assert client.get("/api/tasks", headers=other_headers).json()["items"] == []
    assert client.get(f"/api/tasks/{private_task['id']}", headers=other_headers).status_code == 404


def test_task_audit_logs_and_empty_report(client: TestClient, auth_headers: dict[str, str]) -> None:
    task = create_task(client, auth_headers)
    task_id = task["id"]
    client.post(f"/api/tasks/{task_id}/start", headers=auth_headers)
    client.post(f"/api/tasks/{task_id}/stop", headers=auth_headers)

    logs = client.get(f"/api/logs?task_id={task_id}", headers=auth_headers)
    assert logs.status_code == 200
    assert [entry["event"] for entry in logs.json()] == [
        "task.created",
        "task.started",
        "task.stopped",
    ]

    stats = client.get(f"/api/stats?task_id={task_id}", headers=auth_headers)
    assert stats.status_code == 200
    assert stats.json() == {
        "tasks": 1,
        "found_sites": 0,
        "submissions": 0,
        "successful_submissions": 0,
        "failed_submissions": 0,
    }
    assert client.get(f"/api/sites?task_id={task_id}", headers=auth_headers).json() == []
    assert client.get(f"/api/submissions?task_id={task_id}", headers=auth_headers).json() == []
