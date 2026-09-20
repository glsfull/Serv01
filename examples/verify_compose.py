"""Verify the running Compose stack with allowed and blocked task runs."""

import time
from uuid import uuid4

import httpx


def wait_for_run(client: httpx.Client, headers: dict[str, str], task_id: str, run_id: str) -> dict:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        response = client.get(f"/api/tasks/{task_id}/runs/{run_id}", headers=headers)
        response.raise_for_status()
        run = response.json()
        if run["status"] in {"success", "failed"}:
            return run
        time.sleep(0.5)
    raise TimeoutError(f"Task run {run_id} did not finish within 60 seconds")


def create_and_start(
    client: httpx.Client, headers: dict[str, str], name: str, url: str
) -> tuple[str, str]:
    task_response = client.post(
        "/api/tasks",
        headers=headers,
        json={"name": name, "keywords": ["compose"], "urls": [url]},
    )
    task_response.raise_for_status()
    task_id = task_response.json()["id"]
    start_response = client.post(f"/api/tasks/{task_id}/start", headers=headers)
    start_response.raise_for_status()
    return task_id, start_response.json()["task_run_id"]


def main() -> None:
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=10) as client:
        health = client.get("/health")
        health.raise_for_status()
        assert health.json() == {"status": "ok", "version": "0.2.0"}

        email = f"compose-{uuid4()}@example.com"
        registration = client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": "correct horse battery staple",
                "full_name": "Compose Verification",
            },
        )
        registration.raise_for_status()
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}

        task_id, run_id = create_and_start(
            client, headers, "Allowed example", "https://example.com"
        )
        successful_run = wait_for_run(client, headers, task_id, run_id)
        assert successful_run["status"] == "success", successful_run
        assert successful_run["pages"][0]["status_code"] == 200
        screenshot = client.get(successful_run["screenshots"][0], headers=headers)
        screenshot.raise_for_status()
        assert screenshot.content.startswith(b"\x89PNG")

        task_id, run_id = create_and_start(client, headers, "Blocked example", "https://google.com")
        blocked_run = wait_for_run(client, headers, task_id, run_id)
        assert blocked_run["status"] == "failed", blocked_run
        assert blocked_run["error"] == "blocked_by_allowlist: google.com"

        print("Compose verification passed: health, crawl, screenshot, and allowlist block")


if __name__ == "__main__":
    main()
