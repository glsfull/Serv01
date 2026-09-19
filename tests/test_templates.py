from fastapi.testclient import TestClient


def test_template_crud(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/templates",
        headers=auth_headers,
        json={
            "name": "Primary contact",
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "+12025550123",
            "city": "New York",
            "comment": "Please call during business hours",
        },
    )
    assert created.status_code == 201
    template_id = created.json()["id"]

    listed = client.get("/api/templates", headers=auth_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [template_id]

    updated = client.patch(
        f"/api/templates/{template_id}",
        headers=auth_headers,
        json={"city": "Boston"},
    )
    assert updated.status_code == 200
    assert updated.json()["city"] == "Boston"

    assert client.delete(f"/api/templates/{template_id}", headers=auth_headers).status_code == 204
    assert client.get("/api/templates", headers=auth_headers).json() == []
