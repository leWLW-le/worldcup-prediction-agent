"""Translate V2 results for the unchanged original product components."""

import time
from collections import defaultdict

import streamlit as st

from dashboard.api_client import api


def adapt_result(result):
    data = dict(result)
    bracket = defaultdict(list)
    for match in result.get("representative_path", []):
        bracket[match["stage"]].append(
            {
                **match,
                "home_team": match["home"],
                "away_team": match["away"],
                "status": "FINISHED" if match.get("source") == "observed" else "SCHEDULED",
            }
        )
    bracket["champion"] = {"team": result.get("representative_path_champion", "")}
    data["bracket_payload"] = dict(bracket)
    data["generated_at"] = result.get("created_at")
    data["data_status"] = {
        "source_level": "verified_cache",
        "fixtures_count": 104,
        "user_message": f"数据截止：{result['as_of']} · 赛前历史回放，并非实时赛果 · {result['simulation_count']} 次模拟",
    }
    data["stage_info"] = {"stage": "group", "stage_label": "赛前快照"}
    data["explanation"] = {
        "run_id": result["run_id"],
        "champion": result["champion"],
        "champion_probability": result["champion_probability"],
        "content": (
            f"在 {result['simulation_count']} 次完整赛事模拟中，{result['champion']} 的夺冠概率为 "
            f"{result['champion_probability']:.1%}。这是模型概率最高的球队，并非确定冠军。\n"
            "晋级路线展示一次独立模拟，其胜者可以与概率最高的球队不同。\n"
            "解释依据已保存的模型结果生成；未调用 LLM。"
        ),
    }
    data["agent_steps_summary"] = [
        {
            "step": 1,
            "name": "版本化赛事数据",
            "description": f"截止时间 {result['as_of']}",
            "status": "completed",
        },
        {
            "step": 2,
            "name": "模型预测",
            "description": result["model_version"],
            "status": "completed",
        },
        {
            "step": 3,
            "name": "完整赛事模拟",
            "description": f"{result['simulation_count']} 次模拟；小组排名、第三名晋级及淘汰赛",
            "status": "completed",
        },
    ]
    return data


@st.cache_data(ttl=30, show_spinner=False)
def fetch_final_result():
    try:
        results = api("GET", "/results")["results"]
        result = next((r for r in results if not r.get("constraints")), None)
        if result is None:
            raise RuntimeError("尚无已保存的正式预测")
        return {
            "data": adapt_result(result),
            "source": "api",
            "is_fallback": False,
            "run_id": result["run_id"],
            "generated_at": result["created_at"],
            "error": None,
        }
    except Exception as exc:
        return {
            "data": {},
            "source": "none",
            "is_fallback": False,
            "run_id": None,
            "generated_at": None,
            "error": str(exc),
        }


def get_data_status():
    return fetch_final_result().get("data", {}).get("data_status", {})


def fetch_stage_info():
    return fetch_final_result().get("data", {}).get("stage_info", {})


@st.cache_data(ttl=30, show_spinner=False)
def fetch_scenario_pending_matches():
    try:
        data = fetch_final_result()["data"]
        snapshots = api("GET", "/tournament-state")["snapshots"]
        snapshot = next(s for s in snapshots if s["snapshot_id"] == data["snapshot_id"])
        matches = [
            {
                "match_id": m["fixture_id"],
                "home_team": m["home"],
                "away_team": m["away"],
                "stage": "小组赛",
            }
            for m in (snapshot.get("group_stage") or {}).get("matches", [])
            if m["home_score"] is None
        ]
        return {
            "matches": matches,
            "sandbox_enabled": bool(matches),
            "source": "api",
            "stage_label": "小组赛",
        }
    except Exception:
        return {"matches": [], "sandbox_enabled": None, "source": "error"}


@st.dialog("操作授权")
def _request_token():
    token = st.text_input("操作密钥", type="password", key="operator_token_input")
    st.caption("仅用于本次浏览会话，不向匿名访客提供服务端密钥。")
    if st.button("保存到当前会话"):
        st.session_state["operator_token"] = token
        st.rerun()


def _token():
    token = st.session_state.get("operator_token", "")
    if not token:
        _request_token()
        st.stop()
    return token


def _run(path, body):
    token = _token()
    job = api("POST", path, token, json=body)
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        status = api("GET", "/jobs/" + job["job_id"])
        if status["status"] == "completed":
            return api("GET", "/results/" + status["run_id"])
        if status["status"] in ("failed", "cancelled"):
            raise RuntimeError(status.get("error") or status["status"])
        time.sleep(1)
    raise RuntimeError("计算仍在后台进行，请稍后刷新结果。")


def call_agent_api(mode="llm_planner", use_llm=True):
    try:
        data = fetch_final_result()["data"]
        return _run(
            "/predictions",
            {"snapshot_id": data["snapshot_id"], "simulation_count": 2000, "seed": 42},
        )
    except Exception as exc:
        st.error(str(exc))
        return None


def refresh_real_data():
    # A partial provider refresh must not overwrite the complete tournament snapshot.
    st.info("完整赛事需要通过 V2 快照导入接口更新已核验赛果；当前历史回放不会伪装成实时数据。")
    return None


def call_scenario_simulate(match_id, forced_winner, simulation_count=1000):
    try:
        data = fetch_final_result()["data"]
        result = _run(
            "/scenarios",
            {
                "snapshot_id": data["snapshot_id"],
                "simulation_count": simulation_count,
                "seed": 42,
                "fixture_id": str(match_id),
                "forced_winner": forced_winner,
            },
        )
        match = next(
            m
            for m in fetch_scenario_pending_matches()["matches"]
            if str(m["match_id"]) == str(match_id)
        )
        other = match["away_team"] if forced_winner == match["home_team"] else match["home_team"]
        return {
            "success": True,
            "scenario": {"forced_winner": forced_winner, "forced_loser": other},
            "champion_distribution": [
                {"name": t, "probability": p}
                for t, p in sorted(
                    result["champion_distribution"].items(), key=lambda item: -item[1]
                )
            ],
            "comparison": [
                {
                    "name": t,
                    "official_probability": result["baseline_champion_distribution"][t],
                    "scenario_probability": p,
                    "delta": result["probability_change"][t],
                    "trend": "up" if result["probability_change"][t] > 0 else "down",
                }
                for t, p in sorted(
                    result["champion_distribution"].items(), key=lambda item: -item[1]
                )[:10]
            ],
            "explanation": "与同一数据、模型、次数和种子的重算基线比较。小组赛假设为90分钟获胜，不代表对手已淘汰。",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def fetch_scenario_latest():
    return None
