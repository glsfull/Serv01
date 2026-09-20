from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select

from serv01.dependencies import CurrentUser, DbSession
from serv01.domain import ScheduleType, TaskStatus
from serv01.models import AutomationTask, DataTemplate
from serv01.schemas import TaskCreate, TaskPage, TaskResponse, TaskStartResponse, TaskUpdate
from serv01.services import (
    add_task_log,
    cancel_active_run,
    enqueue_task_run,
    get_owned_task,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def require_owned_task(session: DbSession, user: CurrentUser, task_id: UUID) -> AutomationTask:
    task = get_owned_task(session, user, str(task_id))
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


def validate_template(session: DbSession, user: CurrentUser, template_id: str | None) -> None:
    if template_id is None:
        return
    template = session.scalar(
        select(DataTemplate).where(DataTemplate.id == template_id, DataTemplate.owner_id == user.id)
    )
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")


@router.get("", response_model=TaskPage)
def list_tasks(
    session: DbSession,
    user: CurrentUser,
    task_status: Annotated[TaskStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TaskPage:
    filters = [AutomationTask.owner_id == user.id]
    if task_status is not None:
        filters.append(AutomationTask.status == task_status.value)

    total = session.scalar(select(func.count()).select_from(AutomationTask).where(*filters)) or 0
    tasks = list(
        session.scalars(
            select(AutomationTask)
            .where(*filters)
            .order_by(AutomationTask.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return TaskPage(
        items=[TaskResponse.model_validate(task) for task in tasks],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, session: DbSession, user: CurrentUser) -> AutomationTask:
    values = payload.model_dump(mode="json")
    validate_template(session, user, values["template_id"])
    task = AutomationTask(owner_id=user.id, **values)
    session.add(task)
    session.flush()
    add_task_log(session, task, "task.created", "Task created")
    session.commit()
    return task


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: UUID, session: DbSession, user: CurrentUser) -> AutomationTask:
    return require_owned_task(session, user, task_id)


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    session: DbSession,
    user: CurrentUser,
) -> AutomationTask:
    task = require_owned_task(session, user, task_id)
    if task.status == TaskStatus.RUNNING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A running task must be paused or stopped before it can be edited",
        )

    values = payload.model_dump(exclude_unset=True, mode="json")
    if "template_id" in values:
        validate_template(session, user, values["template_id"])

    schedule_type = values.get("schedule_type", task.schedule_type)
    if schedule_type == ScheduleType.ONCE.value and "schedule_type" in values:
        values.setdefault("cron_expression", None)
    cron_expression = values.get("cron_expression", task.cron_expression)
    if schedule_type == ScheduleType.CRON.value:
        if not cron_expression or len(cron_expression.split()) != 5:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="cron_expression must be a five-field cron expression",
            )
    elif cron_expression is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="cron_expression is only valid for cron schedules",
        )

    for field, value in values.items():
        setattr(task, field, value)
    add_task_log(
        session,
        task,
        "task.updated",
        "Task configuration updated",
        details={"fields": sorted(values)},
    )
    session.commit()
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: UUID, session: DbSession, user: CurrentUser) -> Response:
    task = require_owned_task(session, user, task_id)
    if task.status == TaskStatus.RUNNING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Stop the task before deleting it",
        )
    session.delete(task)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{task_id}/clone", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def clone_task(task_id: UUID, session: DbSession, user: CurrentUser) -> AutomationTask:
    source = require_owned_task(session, user, task_id)
    copy_name = f"{source.name} (copy)"
    clone = AutomationTask(
        owner_id=user.id,
        template_id=source.template_id,
        name=copy_name[:120],
        keywords=list(source.keywords),
        search_engine=source.search_engine,
        search_depth=source.search_depth,
        region=source.region,
        language=source.language,
        action_type=source.action_type,
        max_sites=source.max_sites,
        max_actions=source.max_actions,
        max_runtime_minutes=source.max_runtime_minutes,
        schedule_type=source.schedule_type,
        cron_expression=source.cron_expression,
        respect_robots_txt=source.respect_robots_txt,
        urls=list(source.urls),
    )
    session.add(clone)
    session.flush()
    add_task_log(
        session,
        clone,
        "task.created",
        "Task cloned",
        details={"source_task_id": source.id},
    )
    session.commit()
    return clone


@router.post("/{task_id}/start", response_model=TaskStartResponse)
def start_task(
    task_id: UUID, request: Request, session: DbSession, user: CurrentUser
) -> TaskStartResponse:
    task = require_owned_task(session, user, task_id)
    allowed = {TaskStatus.DRAFT.value, TaskStatus.PAUSED.value}
    if task.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task cannot be started from status '{task.status}'",
        )
    try:
        run = enqueue_task_run(session, task, request.app.state.task_queue)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Task queue is unavailable",
        ) from exc
    payload = TaskResponse.model_validate(task).model_dump()
    return TaskStartResponse(**payload, task_run_id=UUID(run.id))


@router.post("/{task_id}/pause", response_model=TaskResponse)
def pause_task(
    task_id: UUID, request: Request, session: DbSession, user: CurrentUser
) -> AutomationTask:
    task = require_owned_task(session, user, task_id)
    if task.status != TaskStatus.RUNNING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task cannot be paused from status '{task.status}'",
        )
    task.status = TaskStatus.PAUSED.value
    cancel_active_run(
        session,
        task,
        request.app.state.task_queue,
        reason="paused_by_user",
    )
    add_task_log(session, task, "task.paused", "Task paused")
    session.commit()
    return task


@router.post("/{task_id}/stop", response_model=TaskResponse)
def stop_task(
    task_id: UUID, request: Request, session: DbSession, user: CurrentUser
) -> AutomationTask:
    task = require_owned_task(session, user, task_id)
    if task.status not in {TaskStatus.RUNNING.value, TaskStatus.PAUSED.value}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task cannot be stopped from status '{task.status}'",
        )
    task.status = TaskStatus.STOPPED.value
    task.stopped_at = datetime.now(UTC)
    cancel_active_run(
        session,
        task,
        request.app.state.task_queue,
        reason="stopped_by_user",
    )
    add_task_log(session, task, "task.stopped", "Task stopped")
    session.commit()
    return task
