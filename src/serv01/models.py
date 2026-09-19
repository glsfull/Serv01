from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from serv01.database import Base
from serv01.domain import (
    ActionType,
    ScheduleType,
    SearchEngine,
    SubmissionStatus,
    TaskStatus,
    UserRole,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default=UserRole.OPERATOR.value, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    templates: Mapped[list["DataTemplate"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["AutomationTask"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class DataTemplate(TimestampMixin, Base):
    __tablename__ = "templates"
    __table_args__ = (Index("ix_templates_owner_name", "owner_id", "name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(40))
    city: Mapped[str | None] = mapped_column(String(120))
    comment: Mapped[str | None] = mapped_column(Text)

    owner: Mapped[User] = relationship(back_populates="templates")
    tasks: Mapped[list["AutomationTask"]] = relationship(back_populates="template")


class AutomationTask(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_owner_status", "owner_id", "status"),
        Index("ix_tasks_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    template_id: Mapped[str | None] = mapped_column(
        ForeignKey("templates.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    search_engine: Mapped[str] = mapped_column(
        String(20), default=SearchEngine.GOOGLE.value, nullable=False
    )
    search_depth: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    region: Mapped[str | None] = mapped_column(String(50))
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    action_type: Mapped[str] = mapped_column(
        String(30), default=ActionType.CRAWL.value, nullable=False
    )
    max_sites: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    max_actions: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    max_runtime_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    schedule_type: Mapped[str] = mapped_column(
        String(20), default=ScheduleType.ONCE.value, nullable=False
    )
    cron_expression: Mapped[str | None] = mapped_column(String(100))
    respect_robots_txt: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=TaskStatus.DRAFT.value, index=True, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner: Mapped[User] = relationship(back_populates="tasks")
    template: Mapped[DataTemplate | None] = relationship(back_populates="tasks")
    sites: Mapped[list["FoundSite"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    logs: Mapped[list["TaskLog"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class FoundSite(Base):
    __tablename__ = "found_sites"
    __table_args__ = (Index("ix_found_sites_task_url", "task_id", "url", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    snippet: Mapped[str | None] = mapped_column(Text)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    task: Mapped[AutomationTask] = relationship(back_populates="sites")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="site")


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (Index("ix_submissions_task_status", "task_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("found_sites.id", ondelete="SET NULL"), index=True
    )
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=SubmissionStatus.PENDING.value, nullable=False
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    task: Mapped[AutomationTask] = relationship(back_populates="submissions")
    site: Mapped[FoundSite | None] = relationship(back_populates="submissions")


class TaskLog(Base):
    __tablename__ = "logs"
    __table_args__ = (Index("ix_logs_task_created", "task_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    level: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    event: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    task: Mapped[AutomationTask] = relationship(back_populates="logs")
