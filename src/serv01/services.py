from typing import Any

from sqlalchemy.orm import Session

from serv01.models import AutomationTask, TaskLog, User


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
