from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from backend.app_store import AppStore
from backend.ids import stable_id


class JobManager:
    def __init__(self, store: AppStore, max_workers: int = 2):
        self.store = store
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="repoflow-job")
        self.futures: dict[str, Future[Any]] = {}

    def submit(self, kind: str, payload: dict[str, Any], work: Callable[[str], dict[str, Any]]) -> str:
        job_id = stable_id("job", kind, str(payload), str(len(self.futures)))
        self.store.create_job(job_id, kind, payload)
        self.futures[job_id] = self.executor.submit(self._run, job_id, work)
        return job_id

    def _run(self, job_id: str, work: Callable[[str], dict[str, Any]]) -> None:
        self.store.update_job(job_id, status="running", stage="starting", message="Job started")
        try:
            result = work(job_id)
            if self.store.is_cancel_requested(job_id):
                self.store.update_job(job_id, status="cancelled", stage="cancelled", progress=1, message="Job cancelled", result=result)
            else:
                self.store.update_job(job_id, status="completed", stage="completed", progress=1, message="Job completed", result=result)
        except Exception as exc:  # noqa: BLE001 - job boundary must persist all failures
            self.store.update_job(job_id, status="failed", stage="failed", message=str(exc), error={"type": type(exc).__name__, "message": str(exc)})
