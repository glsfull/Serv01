from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi import Path as PathParameter
from fastapi.responses import FileResponse
from sqlalchemy import select

from serv01.dependencies import CurrentUser, DbSession
from serv01.models import AutomationTask, SitePage, TaskRun
from serv01.schemas import SitePageResponse, TaskRunDetail, TaskRunResponse
from serv01.services import get_owned_task

router = APIRouter(prefix="/api", tags=["task runs"])


def owned_run(
    session: DbSession,
    user: CurrentUser,
    task_id: UUID,
    run_id: UUID,
) -> TaskRun:
    if get_owned_task(session, user, str(task_id)) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    run = session.scalar(
        select(TaskRun).where(TaskRun.id == str(run_id), TaskRun.task_id == str(task_id))
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task run not found")
    return run


@router.get("/tasks/{task_id}/runs", response_model=list[TaskRunResponse])
def list_task_runs(task_id: UUID, session: DbSession, user: CurrentUser) -> list[TaskRun]:
    if get_owned_task(session, user, str(task_id)) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return list(
        session.scalars(
            select(TaskRun)
            .where(TaskRun.task_id == str(task_id))
            .order_by(TaskRun.created_at.desc())
        )
    )


@router.get("/tasks/{task_id}/runs/{run_id}", response_model=TaskRunDetail)
def get_task_run(
    task_id: UUID, run_id: UUID, session: DbSession, user: CurrentUser
) -> TaskRunDetail:
    run = owned_run(session, user, task_id, run_id)
    pages = list(
        session.scalars(
            select(SitePage).where(SitePage.task_run_id == run.id).order_by(SitePage.page_number)
        )
    )
    payload = TaskRunResponse.model_validate(run).model_dump()
    return TaskRunDetail(
        **payload,
        pages=[SitePageResponse.model_validate(page) for page in pages],
        screenshots=[f"/api/screenshots/{run.id}/{page.page_number}" for page in pages],
    )


@router.get("/screenshots/{run_id}/{page_number}", response_class=FileResponse)
def get_screenshot(
    run_id: UUID,
    page_number: Annotated[int, PathParameter(ge=1)],
    session: DbSession,
    user: CurrentUser,
) -> FileResponse:
    page = session.scalar(
        select(SitePage)
        .join(TaskRun, SitePage.task_run_id == TaskRun.id)
        .join(AutomationTask, TaskRun.task_id == AutomationTask.id)
        .where(
            SitePage.task_run_id == str(run_id),
            SitePage.page_number == page_number,
            AutomationTask.owner_id == user.id,
        )
    )
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot not found")
    screenshot = Path(page.screenshot_path)
    if not screenshot.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot not found")
    return FileResponse(screenshot, media_type="image/png")
