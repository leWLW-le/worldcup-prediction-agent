from copy import deepcopy

import pytest

from app.domain.contracts import PredictionRequest, ScenarioRequest
from app.infrastructure.store import BusyError
from app.pipelines.prediction import PredictionPipeline, validate_result


def test_result_immutable_and_ranked(service, snapshot):
    r = service.pipeline.run(
        PredictionRequest(snapshot_id=snapshot.snapshot_id, simulation_count=100)
    )
    assert service.store.result(r["run_id"]) == r
    corrupt = deepcopy(r)
    corrupt["top5"].reverse()
    with pytest.raises(ValueError):
        validate_result(corrupt)
    assert service.store.result(r["run_id"]) == r


def test_demo_not_accepted_by_default(service, snapshot):
    pipeline = PredictionPipeline(service.store, service.registry)
    with pytest.raises(ValueError, match="Unverified"):
        pipeline.run(PredictionRequest(snapshot_id=snapshot.snapshot_id))


def test_scenario_does_not_replace_baseline(service, snapshot):
    req = PredictionRequest(snapshot_id=snapshot.snapshot_id, simulation_count=100)
    base = service.pipeline.run(req)
    scenario = service.pipeline.run(
        ScenarioRequest(**req.model_dump(), fixture_id="sf1", forced_winner="A")
    )
    assert scenario["champion_distribution"]["B"] == 0
    assert service.store.results()[0]["run_id"] == base["run_id"]


def test_failed_job_does_not_persist(service, snapshot):
    bad = ScenarioRequest(
        snapshot_id=snapshot.snapshot_id,
        fixture_id="sf1",
        forced_winner="UNKNOWN",
        simulation_count=100,
    )
    result = service.jobs.submit(bad, synchronous=True)
    assert result["status"] == "failed"
    assert service.store.results() == []


def test_db_computation_gate_and_idempotency(service):
    job, created = service.store.create_job("test", "hash")
    assert created
    assert service.store.create_job("test", "hash") == (job, False)
    with pytest.raises(ValueError):
        service.store.create_job("test", "different")
    with pytest.raises(BusyError):
        service.store.create_job("other", "hash")
    service.store.finish(job, error="test complete")
    assert service.store.create_job("other", "hash")[1]


def test_cancelled_job_cannot_publish(service, snapshot):
    req = PredictionRequest(snapshot_id=snapshot.snapshot_id, simulation_count=100)
    result = service.pipeline.run(req, persist=False)
    job, _ = service.store.create_job("cancel", "h")
    service.store.cancel(job)
    with pytest.raises(RuntimeError):
        service.store.complete_result(job, result)
    assert service.store.results() == []


def test_compare_exposes_data_and_model_changes(service, snapshot):
    req = PredictionRequest(snapshot_id=snapshot.snapshot_id, simulation_count=100)
    a, b = service.pipeline.run(req), service.pipeline.run(req)
    comparison = service.pipeline.compare([a["run_id"], b["run_id"]])
    assert not comparison["comparisons"][0]["snapshot_changed"]
    assert all(d == 0 for d in comparison["comparisons"][0]["delta"].values())
