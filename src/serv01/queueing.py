from typing import Protocol

from redis import Redis
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job

from serv01.config import Settings


class TaskQueue(Protocol):
    def enqueue(self, task_run_id: str) -> str: ...

    def cancel(self, job_id: str) -> bool: ...


class RQTaskQueue:
    def __init__(self, settings: Settings) -> None:
        self.connection: Redis = Redis.from_url(settings.redis_url)
        self.queue = Queue(settings.queue_name, connection=self.connection)

    def enqueue(self, task_run_id: str) -> str:
        job = self.queue.enqueue(
            "serv01.worker.execute_task_run",
            task_run_id,
            job_timeout=3600,
            result_ttl=86400,
            failure_ttl=604800,
        )
        return job.id

    def cancel(self, job_id: str) -> bool:
        try:
            job = Job.fetch(job_id, connection=self.connection)
        except NoSuchJobError:
            return False
        job.cancel()
        return True


def create_task_queue(settings: Settings) -> TaskQueue:
    return RQTaskQueue(settings)
