from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from serv01.config import Settings
from serv01.main import create_app


@dataclass
class FakeTaskQueue:
    enqueued: list[str] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)

    def enqueue(self, task_run_id: str) -> str:
        self.enqueued.append(task_run_id)
        return f"job-{task_run_id}"

    def cancel(self, job_id: str) -> bool:
        self.cancelled.append(job_id)
        return True


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url="sqlite+pysqlite://",
        jwt_secret="test-secret-that-is-long-enough-for-hmac",
        access_token_minutes=30,
        allowed_hosts="example.com,www.iana.org,httpbin.org",
        screenshot_dir=str(tmp_path / "screenshots"),
    )


@pytest.fixture
def task_queue() -> FakeTaskQueue:
    return FakeTaskQueue()


@pytest.fixture
def client(settings: Settings, task_queue: FakeTaskQueue) -> Iterator[TestClient]:
    with TestClient(create_app(settings, task_queue=task_queue)) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
            "full_name": "Task Owner",
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
