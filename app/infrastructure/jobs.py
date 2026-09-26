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

    def submit_refresh(self, request, settings, synchronous=False, force=False):
        """The same global computation slot covers fetching, validation and prediction."""
        job_id, _ = self.store.create_job(uuid4().hex, "refresh-and-predict")

        def execute():
            from datetime import datetime, timezone

            from app.data.football_sync import sync
            from app.domain.contracts import PredictionRequest

            try:
                original = self.store.get_input(request.snapshot_id)
                feed = self.store.feed(original.season) or {}
                age = (
                    datetime.now(timezone.utc)
                    - datetime.fromisoformat(feed.get("fetched_at", "2000-01-01T00:00:00+00:00"))
                ).total_seconds()
                if force or age > 300 or not feed.get("snapshot_id") or feed.get("last_error"):
                    feed = sync(self.store, settings, original)
                if not feed.get("prediction_ready") or feed.get("last_error"):
                    raise ValueError(
                        feed.get("prediction_error") or feed.get("last_error") or "赛事数据未就绪"
                    )
                updated = PredictionRequest(
                    snapshot_id=feed["snapshot_id"],
                    simulation_count=request.simulation_count,
                    seed=request.seed,
                )
                return self.execute(job_id, updated)
            except Exception as exc:
                self.store.finish(job_id, error=str(exc))
                return self.store.job(job_id)

        if synchronous:
            status = execute()
            if status["status"] == "completed":
                return self.store.result(status["run_id"])
            return status
        try:
            self.pool.submit(execute)
        except RuntimeError:
            self.store.finish(job_id, error="Worker is shutting down")
            raise
        return self.store.job(job_id)
