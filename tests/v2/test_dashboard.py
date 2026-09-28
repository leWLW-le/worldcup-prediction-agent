import json
from pathlib import Path
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

from dashboard.legacy_adapter import adapt_result


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
    assert '"refresh_data": false' in api_mock.call_args.kwargs["json"]["message"]
