"""Authenticated mutations, read-only history, asynchronous bounded compute."""

from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.agents.task_coordinator import ChatRequest, CompatibleLLM, TaskCoordinator
from app.core.config import get_settings
from app.domain.contracts import (
    CompareRequest,
    PredictionRequest,
    ScenarioRequest,
    TournamentInput,
)
from app.explanation.service import explain_result
from app.infrastructure.store import BusyError

router = APIRouter()


@router.get("/model-info")
def model_info():
    import json
    from pathlib import Path

    root = get_settings().MODEL_BUNDLE_DIR
    path = Path(root) / "evaluation.json" if root else None
    return {
        "evaluation": json.loads(path.read_text(encoding="utf-8"))
        if path and path.exists()
        else None
    }


def authorize(x_api_key: str | None = Header(default=None)):
    from secrets import compare_digest

    expected = get_settings().ADMIN_API_KEY
    if not expected or not x_api_key or not compare_digest(expected, x_api_key):
        raise HTTPException(401, "A valid X-API-Key is required")


def services(request: Request):
    return request.app.state.services


@router.post("/snapshots", dependencies=[Depends(authorize)])
def import_snapshot(payload: TournamentInput, service=Depends(services)):
    try:
        return {"snapshot_id": service.store.put_input(payload)}
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/tournament-state")
def tournament_state(season: int | None = None, service=Depends(services)):
    return {"snapshots": service.store.inputs(season)}


@router.post("/snapshots/{snapshot_id}/refresh", dependencies=[Depends(authorize)])
def refresh(snapshot_id: str, service=Depends(services)):
    from app.data.v2_provider import refresh_snapshot

    try:
        job_id, _ = service.store.create_job(uuid4().hex, "refresh", slot="refresh")
    except BusyError:
        raise HTTPException(429, "Fixture refresh is busy")
    try:
        original = service.store.get_input(snapshot_id)
        service.store.consume_budget("api-football", get_settings().API_FOOTBALL_MAX_DAILY_CALLS)
        updated = refresh_snapshot(original, get_settings().api_football_key)
        return {"snapshot_id": service.store.put_input(updated)}
    except BusyError as exc:
        raise HTTPException(429, str(exc))
    except httpx.HTTPError:
        raise HTTPException(502, "Fixture provider unavailable")
    finally:
        service.store.finish(job_id)


def submit(payload, service, key):
    try:
        return service.jobs.submit(payload, key)
    except BusyError as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/predictions", status_code=202, dependencies=[Depends(authorize)])
def predict(
    payload: PredictionRequest,
    service=Depends(services),
    idempotency_key: str | None = Header(default=None, max_length=128),
):
    # Validate existence before allocating a computation slot.
    service.store.get_input(payload.snapshot_id)
    return submit(payload, service, idempotency_key)


@router.post("/scenarios", status_code=202, dependencies=[Depends(authorize)])
def scenario(
    payload: ScenarioRequest,
    service=Depends(services),
    idempotency_key: str | None = Header(default=None, max_length=128),
):
    service.store.get_input(payload.snapshot_id)
    return submit(payload, service, idempotency_key)


@router.get("/jobs/{job_id}")
def job(job_id: str, service=Depends(services)):
    return service.store.job(job_id)


@router.delete("/jobs/{job_id}", dependencies=[Depends(authorize)])
def cancel(job_id: str, service=Depends(services)):
    service.store.cancel(job_id)
    return service.store.job(job_id)


@router.get("/results")
def results(snapshot_id: str | None = None, service=Depends(services)):
    return {"results": service.store.results(snapshot_id, kind=None)}


@router.get("/results/{run_id}")
def result(run_id: str, service=Depends(services)):
    return service.store.result(run_id)


@router.get("/results/{run_id}/explanation")
def explanation(run_id: str, service=Depends(services)):
    return explain_result(service.store.result(run_id))


@router.post("/compare")
def compare(payload: CompareRequest, service=Depends(services)):
    return service.pipeline.compare(payload.run_ids)


@router.post("/coordinator", dependencies=[Depends(authorize)])
def coordinate(payload: ChatRequest, service=Depends(services)):
    try:
        job_id, _ = service.store.create_job(uuid4().hex, "coordinator", slot="coordinator")
    except BusyError:
        raise HTTPException(429, "Coordinator is busy")
    try:
        return TaskCoordinator(
            service.store,
            service.pipeline,
            service.jobs,
            CompatibleLLM(get_settings(), service.store),
        ).run(payload.message)
    except BusyError as exc:
        raise HTTPException(429, str(exc))
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(503, str(exc))
    finally:
        service.store.finish(job_id)
