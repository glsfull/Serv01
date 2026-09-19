from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from serv01.dependencies import CurrentUser, DbSession
from serv01.domain import SubmissionStatus
from serv01.models import AutomationTask, FoundSite, Submission, TaskLog
from serv01.schemas import FoundSiteResponse, LogResponse, StatsResponse, SubmissionResponse
from serv01.services import get_owned_task

router = APIRouter(prefix="/api", tags=["reports"])


def owned_task_ids(session: DbSession, user: CurrentUser, task_id: UUID | None) -> list[str]:
    if task_id is not None:
        task = get_owned_task(session, user, str(task_id))
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return [task.id]
    return list(
        session.scalars(select(AutomationTask.id).where(AutomationTask.owner_id == user.id))
    )


@router.get("/sites", response_model=list[FoundSiteResponse])
def list_sites(
    session: DbSession,
    user: CurrentUser,
    task_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[FoundSite]:
    task_ids = owned_task_ids(session, user, task_id)
    if not task_ids:
        return []
    return list(
        session.scalars(
            select(FoundSite)
            .where(FoundSite.task_id.in_(task_ids))
            .order_by(FoundSite.discovered_at.desc())
            .limit(limit)
        )
    )


@router.get("/submissions", response_model=list[SubmissionResponse])
def list_submissions(
    session: DbSession,
    user: CurrentUser,
    task_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[Submission]:
    task_ids = owned_task_ids(session, user, task_id)
    if not task_ids:
        return []
    return list(
        session.scalars(
            select(Submission)
            .where(Submission.task_id.in_(task_ids))
            .order_by(Submission.created_at.desc())
            .limit(limit)
        )
    )


@router.get("/logs", response_model=list[LogResponse])
def list_logs(
    session: DbSession,
    user: CurrentUser,
    task_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> list[TaskLog]:
    task_ids = owned_task_ids(session, user, task_id)
    if not task_ids:
        return []
    return list(
        session.scalars(
            select(TaskLog)
            .where(TaskLog.task_id.in_(task_ids))
            .order_by(TaskLog.created_at.asc())
            .limit(limit)
        )
    )


@router.get("/stats", response_model=StatsResponse)
def get_stats(session: DbSession, user: CurrentUser, task_id: UUID | None = None) -> StatsResponse:
    task_ids = owned_task_ids(session, user, task_id)
    if not task_ids:
        return StatsResponse(
            tasks=0,
            found_sites=0,
            submissions=0,
            successful_submissions=0,
            failed_submissions=0,
        )

    found_sites = (
        session.scalar(
            select(func.count()).select_from(FoundSite).where(FoundSite.task_id.in_(task_ids))
        )
        or 0
    )
    submissions = (
        session.scalar(
            select(func.count()).select_from(Submission).where(Submission.task_id.in_(task_ids))
        )
        or 0
    )
    successful_submissions = (
        session.scalar(
            select(func.count())
            .select_from(Submission)
            .where(
                Submission.task_id.in_(task_ids),
                Submission.status == SubmissionStatus.SUCCESS.value,
            )
        )
        or 0
    )
    failed_submissions = (
        session.scalar(
            select(func.count())
            .select_from(Submission)
            .where(
                Submission.task_id.in_(task_ids),
                Submission.status == SubmissionStatus.FAILED.value,
            )
        )
        or 0
    )

    return StatsResponse(
        tasks=len(task_ids),
        found_sites=found_sites,
        submissions=submissions,
        successful_submissions=successful_submissions,
        failed_submissions=failed_submissions,
    )
