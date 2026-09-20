from pathlib import Path

from conftest import FakeTaskQueue
from fastapi.testclient import TestClient
from test_tasks import create_task

from serv01.config import Settings
from serv01.domain import TaskRunStatus
from serv01.execution import CrawledPage, is_host_allowed, robots_permits
from serv01.models import TaskRun
from serv01.worker import process_task_run

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDAT\x08\xd7c\xf8"
    b"\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_allowlist_matches_exact_normalized_hosts_only() -> None:
    allowed = {"example.com", "www.iana.org"}

    assert is_host_allowed("https://EXAMPLE.com/path", allowed)
    assert is_host_allowed("https://www.iana.org:443/domains", allowed)
    assert not is_host_allowed("https://sub.example.com", allowed)
    assert not is_host_allowed("https://example.com.evil.test", allowed)
    assert not is_host_allowed("ftp://example.com/file", allowed)
    assert not is_host_allowed("https://user:secret@example.com", allowed)


def test_robots_filter_uses_the_configured_user_agent() -> None:
    robots = """User-agent: Serv01Bot
Disallow: /private
Allow: /private/public

User-agent: *
Disallow: /
"""

    assert not robots_permits("https://example.com/private", robots, "Serv01Bot/0.1")
    assert robots_permits("https://example.com/private/public", robots, "Serv01Bot/0.1")


def test_start_enqueues_run_and_stop_cancels_queued_job(
    client: TestClient,
    auth_headers: dict[str, str],
    task_queue: FakeTaskQueue,
) -> None:
    task = create_task(client, auth_headers)

    started = client.post(f"/api/tasks/{task['id']}/start", headers=auth_headers)
    assert started.status_code == 200
    run_id = started.json()["task_run_id"]
    assert task_queue.enqueued == [run_id]

    runs = client.get(f"/api/tasks/{task['id']}/runs", headers=auth_headers)
    assert runs.status_code == 200
    assert runs.json()[0]["status"] == "queued"
    assert runs.json()[0]["queue_job_id"] == f"job-{run_id}"

    stopped = client.post(f"/api/tasks/{task['id']}/stop", headers=auth_headers)
    assert stopped.status_code == 200
    assert task_queue.cancelled == [f"job-{run_id}"]

    run = client.get(f"/api/tasks/{task['id']}/runs/{run_id}", headers=auth_headers)
    assert run.json()["status"] == "failed"
    assert run.json()["error"] == "stopped_by_user"


def test_mocked_worker_completes_run_and_exposes_page_and_screenshot(
    client: TestClient,
    auth_headers: dict[str, str],
    settings: Settings,
) -> None:
    task = create_task(client, auth_headers, urls=["https://example.com/start"])
    started = client.post(f"/api/tasks/{task['id']}/start", headers=auth_headers)
    run_id = started.json()["task_run_id"]

    def crawl(url: str, screenshot_path: Path) -> CrawledPage:
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        screenshot_path.write_bytes(PNG_1X1)
        return CrawledPage(
            title="Example Domain",
            url="https://example.com/final",
            status_code=200,
            forms=[{"method": "post", "action": "/contact", "name": "contact", "id": None}],
        )

    process_task_run(
        run_id,
        settings=settings,
        crawler=crawl,
        robots_fetcher=lambda _: "User-agent: *\nAllow: /\n",
        session_factory=client.app.state.session_factory,
    )

    detail = client.get(f"/api/tasks/{task['id']}/runs/{run_id}", headers=auth_headers).json()
    assert detail["status"] == "success"
    assert detail["result_json"] == {"pages": 1, "successful_pages": 1, "failed_pages": 0}
    assert detail["pages"][0]["title"] == "Example Domain"
    assert detail["pages"][0]["forms"][0]["action"] == "/contact"
    assert detail["screenshots"] == [f"/api/screenshots/{run_id}/1"]

    screenshot = client.get(detail["screenshots"][0], headers=auth_headers)
    assert screenshot.status_code == 200
    assert screenshot.headers["content-type"] == "image/png"
    assert screenshot.content.startswith(b"\x89PNG")

    other = client.post(
        "/api/auth/register",
        json={
            "email": "screenshot-intruder@example.com",
            "password": "correct horse battery staple",
            "full_name": "Other User",
        },
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert client.get(detail["screenshots"][0], headers=other_headers).status_code == 404

    task_after = client.get(f"/api/tasks/{task['id']}", headers=auth_headers).json()
    assert task_after["status"] == "completed"
    assert task_after["statistics"] == detail["result_json"]


def test_worker_blocks_disallowed_host_without_opening_browser(
    client: TestClient,
    auth_headers: dict[str, str],
    settings: Settings,
) -> None:
    task = create_task(client, auth_headers, urls=["https://google.com"])
    run_id = client.post(f"/api/tasks/{task['id']}/start", headers=auth_headers).json()[
        "task_run_id"
    ]

    def unexpected_crawl(_: str, __: Path) -> CrawledPage:
        raise AssertionError("crawler must not be called for a blocked host")

    process_task_run(
        run_id,
        settings=settings,
        crawler=unexpected_crawl,
        robots_fetcher=lambda _: "",
        session_factory=client.app.state.session_factory,
    )

    detail = client.get(f"/api/tasks/{task['id']}/runs/{run_id}", headers=auth_headers).json()
    assert detail["status"] == "failed"
    assert detail["error"] == "blocked_by_allowlist: google.com"

    logs = client.get(f"/api/logs?task_id={task['id']}", headers=auth_headers).json()
    assert "blocked_by_allowlist" in [entry["event"] for entry in logs]


def test_worker_respects_robots_before_opening_browser(
    client: TestClient,
    auth_headers: dict[str, str],
    settings: Settings,
) -> None:
    task = create_task(client, auth_headers, urls=["https://example.com/private"])
    run_id = client.post(f"/api/tasks/{task['id']}/start", headers=auth_headers).json()[
        "task_run_id"
    ]
    called = False

    def unexpected_crawl(_: str, __: Path) -> CrawledPage:
        nonlocal called
        called = True
        raise AssertionError("crawler must not be called when robots.txt disallows the URL")

    process_task_run(
        run_id,
        settings=settings,
        crawler=unexpected_crawl,
        robots_fetcher=lambda _: "User-agent: *\nDisallow: /private\n",
        session_factory=client.app.state.session_factory,
    )

    assert not called
    detail = client.get(f"/api/tasks/{task['id']}/runs/{run_id}", headers=auth_headers).json()
    assert detail["status"] == "failed"
    assert detail["error"] == "blocked_by_robots_txt: https://example.com/private"


def test_stop_running_run_sets_cooperative_cancellation_flag(
    client: TestClient,
    auth_headers: dict[str, str],
    task_queue: FakeTaskQueue,
) -> None:
    task = create_task(client, auth_headers)
    run_id = client.post(f"/api/tasks/{task['id']}/start", headers=auth_headers).json()[
        "task_run_id"
    ]
    with client.app.state.session_factory() as session:
        run = session.get(TaskRun, run_id)
        assert run is not None
        run.status = TaskRunStatus.RUNNING.value
        session.commit()

    stopped = client.post(f"/api/tasks/{task['id']}/stop", headers=auth_headers)
    assert stopped.status_code == 200
    with client.app.state.session_factory() as session:
        run = session.get(TaskRun, run_id)
        assert run is not None
        assert run.status == TaskRunStatus.RUNNING.value
        assert run.cancel_requested
    assert task_queue.cancelled == []
