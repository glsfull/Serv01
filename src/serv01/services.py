from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from serv01.domain import TaskRunStatus, TaskStatus
from serv01.models import AutomationTask, TaskLog, TaskRun, User
from serv01.queueing import TaskQueue


def get_owned_task(session: Session, user: User, task_id: str) -> AutomationTask | None:
    return (
        session.query(AutomationTask)
        .filter(AutomationTask.id == task_id, AutomationTask.owner_id == user.id)
        .one_or_none()
    )


def add_task_log(
    session: Session,
    task: AutomationTask,
    event: str,
    message: str,
    *,
    level: str = "info",
    details: dict[str, Any] | None = None,
) -> TaskLog:
    entry = TaskLog(
        task_id=task.id,
        level=level,
        event=event,
        message=message,
        details=details,
    )
    session.add(entry)
    return entry


def enqueue_task_run(session: Session, task: AutomationTask, queue: TaskQueue) -> TaskRun:
    previous_status = task.status
    task.status = TaskStatus.RUNNING.value
    if task.started_at is None:
        task.started_at = datetime.now(UTC)
    task.stopped_at = None
    run = TaskRun(task_id=task.id)
    session.add(run)
    session.flush()
    event = "task.resumed" if previous_status == TaskStatus.PAUSED.value else "task.started"
    add_task_log(
        session,
        task,
        event,
        "Task queued for execution",
        details={"task_run_id": run.id},
    )
    session.commit()

    try:
        run.queue_job_id = queue.enqueue(run.id)
        session.commit()
    except Exception as exc:
        session.rollback()
        recovered_run = session.get(TaskRun, run.id)
        recovered_task = session.get(AutomationTask, task.id)
        if recovered_run is not None:
            recovered_run.status = TaskRunStatus.FAILED.value
            recovered_run.finished_at = datetime.now(UTC)
            recovered_run.error = "queue_unavailable"
        if recovered_task is not None:
            recovered_task.status = TaskStatus.FAILED.value
            add_task_log(
                session,
                recovered_task,
                "queue.enqueue_failed",
                "Could not enqueue task run",
                level="error",
            )
        session.commit()
        raise RuntimeError("queue_unavailable") from exc
    return run


def latest_active_run(session: Session, task: AutomationTask) -> TaskRun | None:
    return session.scalar(
        select(TaskRun)
        .where(
            TaskRun.task_id == task.id,
            TaskRun.status.in_([TaskRunStatus.QUEUED.value, TaskRunStatus.RUNNING.value]),
        )
        .order_by(TaskRun.created_at.desc())
        .limit(1)
    )


def cancel_active_run(
    session: Session,
    task: AutomationTask,
    queue: TaskQueue,
    *,
    reason: str,
) -> TaskRun | None:
    run = latest_active_run(session, task)
    if run is None:
        return None
    run.cancel_requested = True
    if run.status == TaskRunStatus.QUEUED.value:
        if run.queue_job_id is not None:
            try:
                queue.cancel(run.queue_job_id)
            except Exception:
                add_task_log(
                    session,
                    task,
                    "queue.cancel_failed",
                    "Queue cancellation failed; the persisted cancellation flag remains active",
                    level="warning",
                    details={"task_run_id": run.id},
                )
        run.status = TaskRunStatus.FAILED.value
        run.finished_at = datetime.now(UTC)
        run.error = reason
    return run
