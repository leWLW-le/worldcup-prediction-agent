"""Immutable input/result records and database-wide single computation slot."""

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, select, update
from sqlalchemy.exc import IntegrityError

from app.db.database import Base, SessionLocal


class InputRecord(Base):
    __tablename__ = "v2_inputs"
    id = Column(String(64), primary_key=True)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ResultRecord(Base):
    __tablename__ = "v2_results"
    id = Column(String(40), primary_key=True)
    snapshot_id = Column(String(64), nullable=False, index=True)
    kind = Column(String(20), nullable=False, index=True)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class JobRecord(Base):
    __tablename__ = "v2_jobs"
    id = Column(String(40), primary_key=True)
    # UNIQUE nullable slot coordinates all workers and processes.
    active_slot = Column(String(20), unique=True, nullable=True)
    idempotency_key = Column(String(128), unique=True, nullable=False)
    request_hash = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False)
    cancelled = Column(Boolean, default=False)
    result_id = Column(String(40))
    error = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class BusyError(RuntimeError):
    pass


class DailyBudget(Base):
    __tablename__ = "v2_daily_budget"
    id = Column(String(80), primary_key=True)
    used = Column(Integer, nullable=False, default=0)


class Store:
    def __init__(self, session_factory=SessionLocal):
        self.sessions = session_factory

    def consume_budget(self, name, limit):
        key = name + ":" + datetime.now(timezone.utc).date().isoformat()
        with self.sessions() as db:
            if db.get(DailyBudget, key) is None:
                db.add(DailyBudget(id=key, used=0))
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
            claimed = db.execute(
                update(DailyBudget)
                .where(DailyBudget.id == key, DailyBudget.used < limit)
                .values(used=DailyBudget.used + 1)
            )
            if claimed.rowcount != 1:
                db.rollback()
                raise BusyError("Daily external API budget exhausted")
            db.commit()

    def put_input(self, snapshot):
        from app.tournament.bracket import BracketGraph

        if not snapshot.group_stage:
            BracketGraph(snapshot.fixtures)
        payload = snapshot.model_dump_json()
        with self.sessions() as db:
            if not db.get(InputRecord, snapshot.snapshot_id):
                db.add(InputRecord(id=snapshot.snapshot_id, payload=payload))
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    if not db.get(InputRecord, snapshot.snapshot_id):
                        raise
        return snapshot.snapshot_id

    def get_input(self, snapshot_id):
        from app.domain.contracts import TournamentInput

        with self.sessions() as db:
            row = db.get(InputRecord, snapshot_id)
            if row is None:
                raise KeyError("Unknown data snapshot")
            return TournamentInput.model_validate_json(row.payload)

    def inputs(self, season=None):
        with self.sessions() as db:
            rows = db.scalars(
                select(InputRecord).order_by(InputRecord.created_at.desc()).limit(100)
            ).all()
            values = [json.loads(r.payload) for r in rows]
        return [
            {
                "snapshot_id": self._input_hash(v),
                "season": v["season"],
                "as_of": v["as_of"],
                "source": v["source"],
                "provenance": v["provenance"],
                "fixtures": v["fixtures"],
                "group_stage": v.get("group_stage"),
            }
            for v in values
            if season is None or v["season"] == season
        ]

    @staticmethod
    def _input_hash(v):
        from app.domain.contracts import TournamentInput

        return TournamentInput.model_validate(v).snapshot_id

    def save_result(self, payload, kind="prediction"):
        from app.pipelines.prediction import validate_result

        validate_result(payload)
        with self.sessions() as db:
            db.add(
                ResultRecord(
                    id=payload["run_id"],
                    snapshot_id=payload["snapshot_id"],
                    kind=kind,
                    payload=json.dumps(payload, allow_nan=False),
                )
            )
            db.commit()

    def result(self, run_id):
        with self.sessions() as db:
            row = db.get(ResultRecord, run_id)
            if row is None:
                raise KeyError("Unknown run")
            return json.loads(row.payload)

    def results(self, snapshot_id=None, kind="prediction"):
        with self.sessions() as db:
            stmt = select(ResultRecord)
            if kind:
                stmt = stmt.where(ResultRecord.kind == kind)
            if snapshot_id:
                stmt = stmt.where(ResultRecord.snapshot_id == snapshot_id)
            rows = db.scalars(stmt.order_by(ResultRecord.created_at.desc()).limit(100)).all()
            return [json.loads(row.payload) for row in rows]

    def create_job(self, key, request_hash, slot="compute"):
        with self.sessions() as db:
            # A worker heartbeats while executing. Reclaim only an expired lease.
            db.execute(
                update(JobRecord)
                .where(
                    JobRecord.active_slot == slot,
                    JobRecord.updated_at < datetime.now(timezone.utc) - timedelta(minutes=12),
                )
                .values(active_slot=None, status="failed", error="Worker lease expired")
            )
            db.commit()
            existing = db.scalar(select(JobRecord).where(JobRecord.idempotency_key == key))
            if existing:
                if existing.request_hash != request_hash:
                    raise ValueError("Idempotency key already used for a different request")
                return existing.id, False
            job = JobRecord(
                id="job_" + uuid4().hex,
                active_slot=slot,
                idempotency_key=key,
                request_hash=request_hash,
                status="running",
            )
            db.add(job)
            try:
                db.commit()
                return job.id, True
            except IntegrityError:
                db.rollback()
                existing = db.scalar(select(JobRecord).where(JobRecord.idempotency_key == key))
                if existing and existing.request_hash == request_hash:
                    return existing.id, False
                raise BusyError("A prediction is already running")

    def job(self, job_id):
        with self.sessions() as db:
            job = db.get(JobRecord, job_id)
            if job is None:
                raise KeyError("Unknown task")
            return {
                "job_id": job.id,
                "status": job.status,
                "cancel_requested": job.cancelled,
                "run_id": job.result_id,
                "error": job.error,
            }

    def cancel(self, job_id):
        with self.sessions() as db:
            job = db.get(JobRecord, job_id)
            if job is None:
                raise KeyError("Unknown task")
            if job.status == "running":
                job.cancelled = True
                db.commit()

    def heartbeat(self, job_id):
        with self.sessions() as db:
            job = db.get(JobRecord, job_id)
            if job is None or job.status != "running":
                return True
            job.updated_at = datetime.now(timezone.utc)
            cancelled = job.cancelled
            db.commit()
            return cancelled

    def complete_result(self, job_id, result):
        from app.pipelines.prediction import validate_result

        validate_result(result)
        with self.sessions() as db:
            # Update acquires the write lock before the cancellation check.
            claimed = db.execute(
                update(JobRecord)
                .where(
                    JobRecord.id == job_id,
                    JobRecord.status == "running",
                    JobRecord.cancelled.is_(False),
                )
                .values(status="completed", active_slot=None, result_id=result["run_id"])
            )
            if claimed.rowcount != 1:
                db.rollback()
                raise RuntimeError("Task cancelled or lease expired before persistence")
            db.add(
                ResultRecord(
                    id=result["run_id"],
                    snapshot_id=result["snapshot_id"],
                    kind="scenario" if result["constraints"] else "prediction",
                    payload=json.dumps(result, allow_nan=False),
                )
            )
            db.commit()

    def finish(self, job_id, run_id=None, error=None):
        with self.sessions() as db:
            job = db.get(JobRecord, job_id)
            if job.status != "running":
                return
            job.status = "cancelled" if job.cancelled else "failed" if error else "completed"
            job.active_slot = None
            job.result_id, job.error = run_id, error
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
