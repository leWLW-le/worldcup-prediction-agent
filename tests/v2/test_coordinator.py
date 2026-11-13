import json

import pytest

from app.agents.task_coordinator import TOOL_MODELS, ChatRequest, TaskCoordinator
from scripts.release_v2 import released_snapshot


class ScriptedLLM:
    def __init__(self, messages, tool_count=5):
        self.messages = iter(messages)
        self.tool_count = tool_count

    def complete(self, messages, tools):
        assert len(tools) == self.tool_count
        return next(self.messages)


def call(name, args):
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "id": "call1",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
        ],
    }


def test_coordinator_runs_business_workflow(service, snapshot):
    llm = ScriptedLLM(
        [
            call("query_tournament_state", {}),
            call(
                "run_prediction_workflow",
                {"snapshot_id": snapshot.snapshot_id, "simulation_count": 100},
            ),
            {"content": "完成"},
        ]
    )
    result = TaskCoordinator(service.store, service.pipeline, service.jobs, llm).run("预测冠军")
    assert result["status"] == "completed"
    assert result["trace"][1]["result"]["champion_distribution"]
    assert len(TOOL_MODELS) == 5


def test_coordinator_rejects_arbitrary_tool_and_extra_probability(service):
    llm = ScriptedLLM([call("write_probability", {"probability": 1}), {"content": "无法执行"}])
    result = TaskCoordinator(service.store, service.pipeline, service.jobs, llm).run("修改概率")
    assert not result["trace"][0]["success"]


def test_coordinator_limits_expensive_work(service, snapshot):
    args = {"snapshot_id": snapshot.snapshot_id, "simulation_count": 100}
    llm = ScriptedLLM(
        [
            call("run_prediction_workflow", args),
            call("run_prediction_workflow", args),
            {"content": "完成"},
        ]
    )
    result = TaskCoordinator(service.store, service.pipeline, service.jobs, llm).run("反复预测")
    assert not result["trace"][1]["success"]
    assert len(service.store.results()) == 1


@pytest.mark.parametrize("model_calls_tool", [True, False])
def test_sandbox_button_uses_exact_selection(service, snapshot, model_calls_tool):
    tool = "run_scenario_workflow"
    payload = ChatRequest.model_validate({
        "message": "开始推演",
        "action": {
            "snapshot_id": snapshot.snapshot_id,
            "fixture_id": "sf1",
            "forced_winner": "A",
            "simulation_count": 100,
        },
    })
    messages = [call(tool, {"fixture_id": "sf2", "forced_winner": "D"})] if model_calls_tool else []
    messages.append({"content": "完成"})
    result = TaskCoordinator(service.store, service.pipeline, service.jobs, ScriptedLLM(messages, 3)).run(
        payload.message, action=payload.action,
    )
    assert result["status"] == "completed"
    assert bool(result.get("fallback_reason")) is not model_calls_tool
    computed = result["trace"][0]["result"]
    assert computed["constraints"] == {"sf1": "A"}
    assert computed["baseline_champion_distribution"]
    assert len(service.store.results(kind="scenario")) == 1


def test_failed_sandbox_tool_is_reported_without_running_it_twice(service, snapshot, monkeypatch):
    tool = "run_scenario_workflow"
    payload = ChatRequest.model_validate({
        "message": "开始推演",
        "action": {
            "snapshot_id": snapshot.snapshot_id,
            "fixture_id": "sf1",
            "forced_winner": "A",
        },
    })
    calls = []

    def fail(request, *, synchronous):
        calls.append(request)
        return {"status": "failed", "error": "比赛已结束"}

    monkeypatch.setattr(service.jobs, "submit", fail)
    llm = ScriptedLLM([call(tool, {}), {"content": "推演失败"}], 3)
    result = TaskCoordinator(service.store, service.pipeline, service.jobs, llm).run(
        payload.message, action=payload.action,
    )
    assert result["trace"] == [{"tool": tool, "success": False, "result": {"error": "比赛已结束"}}]
    assert len(calls) == 1


def test_released_mexico_sandbox_runs_when_model_skips_tool(service):
    snapshot = released_snapshot()
    service.store.put_input(snapshot)
    match = next(
        match for match in snapshot.group_stage.matches
        if match.home == "Mexico" and match.away == "South Africa"
    )
    payload = ChatRequest.model_validate({
        "message": "假设墨西哥战胜南非",
        "action": {
            "snapshot_id": snapshot.snapshot_id,
            "fixture_id": match.fixture_id,
            "forced_winner": "Mexico",
            "simulation_count": 100,
        },
    })
    result = TaskCoordinator(
        service.store, service.pipeline, service.jobs, ScriptedLLM([{"content": "完成"}], 3),
    ).run(payload.message, action=payload.action)
    assert result["status"] == "completed", result["trace"]
    scenario = result["trace"][0]["result"]
    assert scenario["constraints"] == {match.fixture_id: "Mexico"}
    assert scenario["probability_change"]
