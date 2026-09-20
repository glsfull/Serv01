from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from serv01.domain import (
    ActionType,
    ScheduleType,
    SearchEngine,
    SubmissionStatus,
    TaskRunStatus,
    TaskStatus,
    UserRole,
)


class FromAttributesModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=1, max_length=100)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).lower()

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("full_name cannot be blank")
        return normalized


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class UserResponse(FromAttributesModel):
    id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    full_name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    city: str | None = Field(default=None, max_length=120)
    comment: str | None = Field(default=None, max_length=5000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be blank")
        return normalized


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    full_name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    city: str | None = Field(default=None, max_length=120)
    comment: str | None = Field(default=None, max_length=5000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be blank")
        return normalized

    @model_validator(mode="after")
    def reject_null_name(self) -> "TemplateUpdate":
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class TemplateResponse(FromAttributesModel):
    id: UUID
    name: str
    full_name: str | None
    email: EmailStr | None
    phone: str | None
    city: str | None
    comment: str | None
    created_at: datetime
    updated_at: datetime


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    keywords: list[str] = Field(min_length=1, max_length=100)
    search_engine: SearchEngine = SearchEngine.GOOGLE
    search_depth: Literal[10, 50, 100] = 10
    region: str | None = Field(default=None, max_length=50)
    language: str = Field(default="en", min_length=2, max_length=10)
    action_type: ActionType = ActionType.CRAWL
    template_id: UUID | None = None
    max_sites: int = Field(default=100, ge=1, le=10_000)
    max_actions: int = Field(default=100, ge=1, le=100_000)
    max_runtime_minutes: int = Field(default=60, ge=1, le=10_080)
    schedule_type: ScheduleType = ScheduleType.ONCE
    cron_expression: str | None = Field(default=None, max_length=100)
    respect_robots_txt: bool = True
    urls: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("name", "language")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value cannot be blank")
        return normalized

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for keyword in value:
            item = keyword.strip()
            if not item:
                raise ValueError("keywords cannot contain empty values")
            if len(item) > 200:
                raise ValueError("each keyword must contain at most 200 characters")
            lookup = item.casefold()
            if lookup not in seen:
                normalized.append(item)
                seen.add(lookup)
        return normalized

    @field_validator("urls")
    @classmethod
    def normalize_urls(cls, value: list[str]) -> list[str]:
        return normalize_task_urls(value)

    @model_validator(mode="after")
    def validate_schedule(self) -> "TaskCreate":
        if self.schedule_type == ScheduleType.CRON:
            if not self.cron_expression or len(self.cron_expression.split()) != 5:
                raise ValueError("cron_expression must be a five-field cron expression")
        elif self.cron_expression is not None:
            raise ValueError("cron_expression is only valid for cron schedules")
        return self


class TaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    keywords: list[str] | None = Field(default=None, min_length=1, max_length=100)
    search_engine: SearchEngine | None = None
    search_depth: Literal[10, 50, 100] | None = None
    region: str | None = Field(default=None, max_length=50)
    language: str | None = Field(default=None, min_length=2, max_length=10)
    action_type: ActionType | None = None
    template_id: UUID | None = None
    max_sites: int | None = Field(default=None, ge=1, le=10_000)
    max_actions: int | None = Field(default=None, ge=1, le=100_000)
    max_runtime_minutes: int | None = Field(default=None, ge=1, le=10_080)
    schedule_type: ScheduleType | None = None
    cron_expression: str | None = Field(default=None, max_length=100)
    respect_robots_txt: bool | None = None
    urls: list[str] | None = Field(default=None, max_length=100)

    @field_validator("name", "language")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("value cannot be blank")
        return normalized

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized: list[str] = []
        seen: set[str] = set()
        for keyword in value:
            item = keyword.strip()
            if not item:
                raise ValueError("keywords cannot contain empty values")
            if len(item) > 200:
                raise ValueError("each keyword must contain at most 200 characters")
            lookup = item.casefold()
            if lookup not in seen:
                normalized.append(item)
                seen.add(lookup)
        return normalized

    @field_validator("urls")
    @classmethod
    def normalize_urls(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else normalize_task_urls(value)

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "TaskUpdate":
        required_fields = {
            "name",
            "keywords",
            "search_engine",
            "search_depth",
            "language",
            "action_type",
            "max_sites",
            "max_actions",
            "max_runtime_minutes",
            "schedule_type",
            "respect_robots_txt",
            "urls",
        }
        null_fields = sorted(
            field
            for field in required_fields.intersection(self.model_fields_set)
            if getattr(self, field) is None
        )
        if null_fields:
            raise ValueError(f"fields cannot be null: {', '.join(null_fields)}")
        return self


class TaskResponse(FromAttributesModel):
    id: UUID
    name: str
    keywords: list[str]
    search_engine: SearchEngine
    search_depth: Literal[10, 50, 100]
    region: str | None
    language: str
    action_type: ActionType
    template_id: UUID | None
    max_sites: int
    max_actions: int
    max_runtime_minutes: int
    schedule_type: ScheduleType
    cron_expression: str | None
    respect_robots_txt: bool
    urls: list[str]
    statistics: dict[str, int]
    status: TaskStatus
    started_at: datetime | None
    stopped_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TaskPage(BaseModel):
    items: list[TaskResponse]
    total: int
    page: int
    page_size: int


class TaskStartResponse(TaskResponse):
    task_run_id: UUID


class SitePageResponse(FromAttributesModel):
    id: UUID
    task_run_id: UUID
    page_number: int
    title: str | None
    url: str
    status_code: int | None
    forms: list[dict[str, Any]]
    created_at: datetime


class TaskRunResponse(FromAttributesModel):
    id: UUID
    task_id: UUID
    status: TaskRunStatus
    queue_job_id: str | None
    cancel_requested: bool
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    result_json: dict[str, Any] | None
    created_at: datetime


class TaskRunDetail(TaskRunResponse):
    pages: list[SitePageResponse]
    screenshots: list[str]


class FoundSiteResponse(FromAttributesModel):
    id: UUID
    task_id: UUID
    url: str
    title: str | None
    snippet: str | None
    discovered_at: datetime


class SubmissionResponse(FromAttributesModel):
    id: UUID
    task_id: UUID
    site_id: UUID | None
    action_type: ActionType
    status: SubmissionStatus
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime


class LogResponse(FromAttributesModel):
    id: UUID
    task_id: UUID
    level: str
    event: str
    message: str
    details: dict[str, Any] | None
    created_at: datetime


class StatsResponse(BaseModel):
    tasks: int
    found_sites: int
    submissions: int
    successful_submissions: int
    failed_submissions: int


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str


def normalize_task_urls(value: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_url in value:
        url = raw_url.strip()
        if not url:
            raise ValueError("urls cannot contain empty values")
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError("urls must use http or https")
        if len(url) > 2048:
            raise ValueError("each URL must contain at most 2048 characters")
        if url not in seen:
            normalized.append(url)
            seen.add(url)
    return normalized
