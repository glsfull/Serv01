from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from serv01.config import Settings
from serv01.database import create_database_engine, create_session_factory
from serv01.domain import TaskRunStatus, TaskStatus
from serv01.execution import (
    CrawledPage,
    Crawler,
    ExecutionBlocked,
    RobotsFetcher,
    crawl_page,
    fetch_robots_text,
    is_host_allowed,
    robots_permits,
    robots_url_for,
)
from serv01.models import AutomationTask, FoundSite, SitePage, TaskRun
from serv01.services import add_task_log


class RunCancelled(RuntimeError):
    pass


def _mark_failed(session: Session, run: TaskRun, task: AutomationTask, error: str) -> None:
    now = datetime.now(UTC)
    run.status = TaskRunStatus.FAILED.value
    run.finished_at = now
    run.error = error
    completed_pages = len(run.pages)
    run.result_json = {
        "pages": completed_pages,
        "successful_pages": completed_pages,
        "failed_pages": 1,
    }
    task.statistics = dict(run.result_json)
    if task.status not in {TaskStatus.STOPPED.value, TaskStatus.PAUSED.value}:
        task.status = TaskStatus.FAILED.value
    event = error.split(":", 1)[0]
    add_task_log(session, task, event, error, level="error", details={"task_run_id": run.id})
    session.commit()


def _get_run_and_task(session: Session, task_run_id: str) -> tuple[TaskRun, AutomationTask]:
    run = session.get(TaskRun, task_run_id)
    if run is None:
        raise LookupError(f"Task run {task_run_id} does not exist")
    task = session.get(AutomationTask, run.task_id)
    if task is None:
        raise LookupError(f"Task {run.task_id} does not exist")
    return run, task


def process_task_run(
    task_run_id: str,
    *,
    settings: Settings,
    crawler: Crawler | None = None,
    robots_fetcher: RobotsFetcher | None = None,
    session_factory: Callable[[], Session] | None = None,
) -> None:
    engine = None
    if session_factory is None:
        engine = create_database_engine(settings.database_url)
        session_factory = create_session_factory(engine)
    page_crawler = crawler or (lambda url, path: crawl_page(url, path, settings))
    fetch_robots = robots_fetcher or (lambda url: fetch_robots_text(url, settings))

    try:
        with session_factory() as session:
            run, task = _get_run_and_task(session, task_run_id)
            if run.status != TaskRunStatus.QUEUED.value:
                return
            if run.cancel_requested:
                _mark_failed(session, run, task, "stopped_by_user")
                return

            run.status = TaskRunStatus.RUNNING.value
            run.started_at = datetime.now(UTC)
            add_task_log(
                session,
                task,
                "run.started",
                "Worker started task run",
                details={"task_run_id": run.id, "template_id": task.template_id},
            )
            session.commit()

            try:
                if not task.urls:
                    raise RuntimeError("no_urls_configured")
                for page_number, url in enumerate(task.urls, start=1):
                    session.refresh(run)
                    if run.cancel_requested:
                        raise RunCancelled("stopped_by_user")

                    add_task_log(
                        session,
                        task,
                        "page.started",
                        f"Validating {url}",
                        details={"task_run_id": run.id, "page_number": page_number},
                    )
                    session.commit()

                    if not is_host_allowed(url, settings.parsed_allowed_hosts):
                        host = urlsplit(url).hostname or "invalid"
                        raise ExecutionBlocked(f"blocked_by_allowlist: {host}")

                    if task.respect_robots_txt:
                        robots_text = fetch_robots(robots_url_for(url))
                        if not robots_permits(url, robots_text, settings.bot_user_agent):
                            raise ExecutionBlocked(f"blocked_by_robots_txt: {url}")

                    screenshot_path = Path(settings.screenshot_dir) / run.id / f"{page_number}.png"
                    page: CrawledPage = page_crawler(url, screenshot_path)
                    if not is_host_allowed(page.url, settings.parsed_allowed_hosts):
                        host = urlsplit(page.url).hostname or "invalid"
                        raise ExecutionBlocked(f"blocked_by_allowlist: {host}")

                    session.add(
                        SitePage(
                            task_run_id=run.id,
                            page_number=page_number,
                            title=page.title,
                            url=page.url,
                            status_code=page.status_code,
                            forms=page.forms,
                            screenshot_path=str(screenshot_path),
                        )
                    )
                    existing_site = session.scalar(
                        select(FoundSite).where(
                            FoundSite.task_id == task.id, FoundSite.url == page.url
                        )
                    )
                    if existing_site is None:
                        session.add(FoundSite(task_id=task.id, url=page.url, title=page.title))
                    add_task_log(
                        session,
                        task,
                        "page.captured",
                        f"Captured {page.url}",
                        details={
                            "task_run_id": run.id,
                            "page_number": page_number,
                            "status_code": page.status_code,
                        },
                    )
                    session.commit()

                page_count = len(task.urls)
                result = {
                    "pages": page_count,
                    "successful_pages": page_count,
                    "failed_pages": 0,
                }
                run.status = TaskRunStatus.SUCCESS.value
                run.finished_at = datetime.now(UTC)
                run.result_json = result
                task.status = TaskStatus.COMPLETED.value
                task.statistics = result
                add_task_log(
                    session,
                    task,
                    "run.succeeded",
                    "Task run completed",
                    details={"task_run_id": run.id, **result},
                )
                session.commit()
            except Exception as exc:
                session.rollback()
                run, task = _get_run_and_task(session, task_run_id)
                _mark_failed(session, run, task, str(exc) or type(exc).__name__)
    finally:
        if engine is not None:
            engine.dispose()


def execute_task_run(task_run_id: str) -> None:
    process_task_run(task_run_id, settings=Settings())
