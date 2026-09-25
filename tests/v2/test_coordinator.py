import json

from app.agents.task_coordinator import TOOL_MODELS, TaskCoordinator


class ScriptedLLM:
    def __init__(self, messages):
        self.messages = iter(messages)

    def complete(self, messages, tools):
        assert len(tools) == 5
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
