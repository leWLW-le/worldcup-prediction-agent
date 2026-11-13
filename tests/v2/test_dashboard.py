import json
from pathlib import Path
from unittest.mock import patch

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from dashboard.legacy_adapter import adapt_result


def test_operation_auth_uses_server_configuration_without_prompt(monkeypatch):
    from dashboard.legacy_adapter import _token
    monkeypatch.setenv("BACKEND_API_KEY", "server-test-key")
    with patch("streamlit.text_input") as prompt:
        assert _token() == "server-test-key"
    prompt.assert_not_called()
    monkeypatch.delenv("BACKEND_API_KEY")
    with pytest.raises(RuntimeError, match="预测服务暂未就绪"):
        _token()


def test_dashboard_empty_state_and_backend_failure():
    for response, error in [({"results": []}, None), (None, RuntimeError("offline"))]:
        st.cache_data.clear()
        with patch("dashboard.legacy_adapter.api", return_value=response, side_effect=error):
            app = AppTest.from_file("dashboard/app.py").run()
            assert not app.exception
            assert app.button[0].disabled
            assert app.error
            if error:
                assert "offline" in app.error[0].value


def test_original_ui_displays_saved_result_without_rewriting_probabilities():
    result = json.loads(Path("data/verified/release-result.json").read_text(encoding="utf-8"))
    data = adapt_result(result)
    assert data["champion_probability"] == result["champion_probability"]
    assert data["top5"] == result["top5"]
    assert data["bracket_payload"]["champion"]["team"] == result["representative_path_champion"]
    st.cache_data.clear()

    def read(method, path, **kwargs):
        return {"results": [result]} if path == "/results" else {"snapshots": []}

    with patch("dashboard.legacy_adapter.api", side_effect=read):
        app = AppTest.from_file("dashboard/app.py").run()
        assert not app.exception
        assert any(
            "champion-name" in item.value and result["champion"] in item.value
            for item in app.markdown
        )
        assert any("hero-title" in item.value for item in app.markdown)


def test_original_ui_shows_actual_scores_alongside_explicitly_stale_prediction():
    result = json.loads(Path("data/verified/release-result.json").read_text(encoding="utf-8"))
    fixture = {
        "kickoff": "2026-06-11T19:00:00+00:00",
        "round": "Group Stage - 1",
        "home": "Mexico",
        "away": "South Africa",
        "status": "FT",
        "score": {"home": 2, "away": 0},
        "score_90": {"home": 2, "away": 0},
        "score_extra_time": {},
        "score_penalties": {},
    }
    feed = {
        "fixtures": [fixture],
        "fetched_at": "2026-06-12T00:00:00Z",
        "configured": True,
        "prediction_error": "测试：待补齐纪律信息",
        "snapshot_id": None,
    }

    def read(method, path, **kwargs):
        return {
            "/results": {"results": [result]},
            "/data/status": feed,
            "/tournament-state": {"snapshots": []},
        }[path]

    st.cache_data.clear()
    with patch("dashboard.legacy_adapter.api", side_effect=read):
        app = AppTest.from_file("dashboard/app.py").run()
        assert not app.exception
        assert any("hero-title" in item.value for item in app.markdown)
        assert any("赛前预测回放" in item.value for item in app.markdown)
        assert app.dataframe[0].value.iloc[0]["比分"] == "2–0"
        assert any("纪律" in item.value for item in app.caption)
        assert not app.warning


def test_observed_champion_cannot_replace_pre_tournament_prediction():
    from dashboard.legacy_adapter import PRE_TOURNAMENT_SNAPSHOT, fetch_final_result

    result = json.loads(Path("data/verified/release-result.json").read_text(encoding="utf-8"))
    observed = {
        **result,
        "status": "observed",
        "champion": "Spain",
        "champion_probability": 1,
        "snapshot_id": "live-results",
    }

    def read(method, path, **kwargs):
        if path == "/results":
            assert kwargs["params"]["snapshot_id"] == PRE_TOURNAMENT_SNAPSHOT
            return {"results": [observed, result]}
        return {"fixtures": []}

    st.cache_data.clear()
    with patch("dashboard.legacy_adapter.api", side_effect=read):
        displayed = fetch_final_result()["data"]
    assert displayed["champion"] == result["champion"]
    assert displayed["champion_probability"] == result["champion_probability"]


def test_actual_bracket_uses_only_provider_results():
    from dashboard.legacy_adapter import actual_bracket

    assert actual_bracket({}) == {}
    rows = [
        {
            "fixture_id": "f",
            "round": "FINAL",
            "home": "Spain",
            "away": "Argentina",
            "status": "AET",
            "score": {"home": 1, "away": 0},
            "winner": "Spain",
        }
    ]
    bracket = actual_bracket({"fixtures": rows})
    assert bracket["champion"]["team"] == "Spain"
    assert bracket["final"][0]["score"] == "1 : 0（加时）"
    rows[0].update(status="NS", score={}, winner=None)
    bracket = actual_bracket({"fixtures": rows})
    assert "champion" not in bracket
    assert bracket["final"][0]["score"] == "待赛"


def test_prediction_enters_llm_planner_before_computation():
    from dashboard.legacy_adapter import call_agent_api

    result = json.loads(Path("data/verified/release-result.json").read_text(encoding="utf-8"))
    reply = {"trace": [{"tool": "run_prediction_workflow", "success": True, "result": result}]}
    with (
        patch("dashboard.legacy_adapter._token", return_value="test"),
        patch("dashboard.legacy_adapter.api", return_value=reply) as api_mock,
        patch("dashboard.legacy_adapter._run") as deterministic,
    ):
        assert call_agent_api()["run_id"] == result["run_id"]
    deterministic.assert_not_called()
    assert api_mock.call_args.args[:2] == ("POST", "/coordinator")
    assert api_mock.call_args.kwargs["json"]["action"]["refresh_data"] is False


def test_sandbox_displays_workflow_error_instead_of_incomplete_plan():
    from dashboard.legacy_adapter import _planned_workflow

    reply = {
        "status": "completed",
        "trace": [
            {"tool": "run_scenario_workflow", "success": False, "result": {"error": "比赛已结束"}}
        ],
    }
    with (
        patch("dashboard.legacy_adapter.submit_planner_task", return_value=reply),
        pytest.raises(RuntimeError, match="比赛已结束"),
    ):
        _planned_workflow("run_scenario_workflow", {})


def test_prediction_mode_switch_routes_the_dashboard_button(monkeypatch):
    monkeypatch.setenv("BACKEND_API_KEY", "test")
    result = json.loads(Path("data/verified/release-result.json").read_text(encoding="utf-8"))

    def respond(method, path, token="", **kwargs):
        if path == "/results":
            return {"results": [result]}
        if path == "/predictions":
            return {"job_id": "job-test"}
        if path == "/jobs/job-test":
            return {"status": "completed", "run_id": result["run_id"]}
        if path == f"/results/{result['run_id']}":
            return result
        if path.endswith("/explanation"):
            return {"text": "测试摘要", "source": "template"}
        if path == "/coordinator":
            return {
                "status": "completed",
                "trace": [{"tool": "run_prediction_workflow", "success": True, "result": result}],
            }
        return {"snapshots": [], "fixtures": []}

    st.cache_data.clear()
    with patch("dashboard.legacy_adapter.api", side_effect=respond) as api_mock:
        app = AppTest.from_file("dashboard/app.py", default_timeout=10).run()
        next(button for button in app.button if "重新预测" in button.label).click().run()
        assert not app.exception
        assert [call.args[1] for call in api_mock.call_args_list if call.args[0] == "POST"] == [
            "/predictions"
        ]

        app.sidebar.radio[0].set_value("llm_planner").run()
        api_mock.reset_mock()
        next(button for button in app.button if "重新预测" in button.label).click().run()
        assert not app.exception
        posts = [call.args[1] for call in api_mock.call_args_list if call.args[0] == "POST"]
        assert "/coordinator" in posts
        assert "/predictions" not in posts

        api_mock.reset_mock()
        message = "查询当前赛事状态"
        app.sidebar.text_area[0].set_value(message)
        next(button for button in app.sidebar.button if button.label == "执行任务").click().run()
        assert not app.exception
        coordinator = next(
            call for call in api_mock.call_args_list if call.args[:2] == ("POST", "/coordinator")
        )
        assert coordinator.kwargs["json"] == {"message": message}


@pytest.mark.parametrize("use_llm", [False, True])
def test_scenario_mode_routes_the_same_parameters(use_llm):
    from dashboard.legacy_adapter import call_scenario_simulate

    match = {"match_id": "m1", "home_team": "Spain", "away_team": "Argentina"}
    prediction = {
        "champion": "Spain",
        "champion_probability": 0.6,
        "champion_distribution": {"Spain": 0.6},
        "baseline_champion_distribution": {"Spain": 0.4},
        "probability_change": {"Spain": 0.2},
    }
    with (
        patch("dashboard.legacy_adapter.fetch_final_result", return_value={"data": {"snapshot_id": "snap"}}),
        patch("dashboard.legacy_adapter.fetch_scenario_pending_matches", return_value={"matches": [match]}),
        patch("dashboard.legacy_adapter._run", return_value=prediction) as workflow,
        patch("dashboard.legacy_adapter._planned_workflow", return_value=prediction) as planner,
    ):
        assert call_scenario_simulate("m1", "Spain", use_llm=use_llm)["success"]
    arguments = {
        "snapshot_id": "snap", "simulation_count": 1000, "seed": 42,
        "fixture_id": "m1", "forced_winner": "Spain",
    }
    if use_llm:
        planner.assert_called_once_with("run_scenario_workflow", arguments)
        workflow.assert_not_called()
    else:
        workflow.assert_called_once_with("/scenarios", arguments)
        planner.assert_not_called()


def test_sandbox_selects_round_fixture_and_winner_and_displays_champion():
    result = json.loads(Path("data/verified/release-result.json").read_text(encoding="utf-8"))
    snapshot = {
        "snapshot_id": result["snapshot_id"],
        "group_stage": {
            "matches": [{**result["representative_group_matches"][0], "home_score": None}],
        },
    }
    final = next(m for m in result["representative_path"] if m["stage"] == "final")
    predicted = {"success": True, "champion": final["away"], "champion_probability": 1.0}

    def read(method, path, **kwargs):
        return {
            "/results": {"results": [result]},
            "/tournament-state": {"snapshots": [snapshot]},
            "/data/status": {},
        }[path]

    st.cache_data.clear()
    with (
        patch("dashboard.legacy_adapter.api", side_effect=read),
        patch("dashboard.legacy_adapter.call_scenario_simulate", return_value=predicted) as simulate,
    ):
        app = AppTest.from_file("dashboard/app.py", default_timeout=10).run()
        rounds = app.selectbox(key="scenario_round")
        assert "4 强赛（半决赛）" in rounds.options
        assert "8 强赛（四分之一决赛）" in rounds.options
        rounds.set_value("semi_finals").run()
        assert len(app.selectbox(key="scenario_match_semi_finals").options) == 2
        app.selectbox(key="scenario_round").set_value("final").run()
        assert app.selectbox(key="scenario_match_final").options == [f"{final['home']} vs {final['away']}"]
        app.radio(key="scenario_winner_104").set_value(final["away"])
        app.button(key="scenario_run_btn").click().run()
        assert not app.exception
        assert any(m.label == "最可能夺冠" and m.value == final["away"] for m in app.metric)
        simulate.assert_called_once_with(
            "104", final["away"], use_llm=False, reference_run_id=result["run_id"],
        )
