from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    OPERATOR = "operator"


class SearchEngine(StrEnum):
    GOOGLE = "google"
    YANDEX = "yandex"


class ActionType(StrEnum):
    REGISTRATION = "registration"
    FORM_SUBMISSION = "form_submission"
    CRAWL = "crawl"
    COMBINED = "combined"


class ScheduleType(StrEnum):
    ONCE = "once"
    CRON = "cron"


class TaskStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class SubmissionStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
