"""Bounded jobs shared by HTTP, the coordinator and scheduled callers."""

import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from app.domain.contracts import digest


class Jobs:
    def __init__(self, store, pipeline):
        self.store, self.pipeline = store, pipeline
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="prediction")

    def execute(self, job_id, request):
        last_check = 0.0

        def cancelled():
            nonlocal last_check
            if time.monotonic() - last_check >= 0.25:
                last_check = time.monotonic()
                return self.store.heartbeat(job_id)
            return False

        try:
            result = self.pipeline.run(request, cancelled=cancelled, persist=False)
            self.store.complete_result(job_id, result)
        except Exception as exc:
            self.store.finish(job_id, error=str(exc))
        return self.store.job(job_id)

    def submit(self, request, key=None, synchronous=False):
        job_id, created = self.store.create_job(
            key or uuid4().hex, digest(request.model_dump(mode="json"))
        )
        if created:
            if synchronous:
                self.execute(job_id, request)
            else:
                try:
                    self.pool.submit(self.execute, job_id, request)
                except RuntimeError:
                    self.store.finish(job_id, error="Worker is shutting down")
                    raise
        job = self.store.job(job_id)
        if synchronous and job["status"] == "completed":
            return self.store.result(job["run_id"])
        return job

    def close(self):
        # Running jobs retain their persisted lease; their loops obey the time budget.
        self.pool.shutdown(wait=True, cancel_futures=True)
