"""Translate V2 results for the unchanged original product components."""

import json
import os
import time
from collections import defaultdict

import streamlit as st

from dashboard.api_client import api

# Immutable June 1 input used by the published pre-tournament model replay.
PRE_TOURNAMENT_SNAPSHOT = "9e4760a6cc97914613b898c9f013370c9750f092c7e4ec5e6e0118612c7131ba"


def actual_bracket(feed):
    """Use provider fixtures only; never substitute a simulated path."""
    stages = {
        "LAST_32": "round_of_32",
        "LAST_16": "round_of_16",
        "QUARTER_FINALS": "quarter_finals",
        "SEMI_FINALS": "semi_finals",
        "FINAL": "final",
        "Round of 32": "round_of_32",
        "Round of 16": "round_of_16",
        "Quarter-finals": "quarter_finals",
        "Semi-finals": "semi_finals",
        "Final": "final",
    }
    rows = feed.get("fixtures") or (feed.get("fallback") or {}).get("fixtures", [])
    bracket = defaultdict(list)
    for row in sorted(rows, key=lambda r: (r.get("kickoff", ""), str(r.get("fixture_id", "")))):
        stage = stages.get(row.get("round"))
        if not stage:
            continue
        pair = row.get("score") or {}
        score = (
            "待赛"
            if pair.get("home") is None or pair.get("away") is None
            else f"{pair['home']} : {pair['away']}"
        )
        penalties = row.get("score_penalties") or {}
        if penalties.get("home") is not None and penalties.get("away") is not None:
            score += f"（点球 {penalties['home']} : {penalties['away']}）"
        elif row.get("status") == "AET":
            score += "（加时）"
        finished = row.get("status") in ("FT", "AET", "PEN", "FINISHED")
        winner = row.get("winner") if finished else None
        bracket[stage].append(
            {
                "home_team": row.get("home") or "待定",
                "away_team": row.get("away") or "待定",
                "score": score,
                "status": row.get("status"),
                "winner": winner,
            }
        )
        if stage == "final" and winner:
            bracket["champion"] = {"team": winner}
    return dict(bracket)


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
        "user_message": f"赛前预测回放 · 数据截至 {result['as_of'][:10]}",
    }
    data["stage_info"] = {"stage": "group", "stage_label": "赛前快照"}
    if result.get("actual_fixtures"):
        completed = result.get("status") == "observed"
        data["data_status"]["user_message"] = (
            f"真实赛事数据截止：{result['as_of']} · 已完赛结果锁定 · {result['simulation_count']} 次模拟"
        )
        data["stage_info"] = {
            "stage": "completed" if completed else "in_progress",
            "stage_label": "赛事结束" if completed else "赛事进行中",
        }
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
    if result.get("status") == "observed":
        data["explanation"]["content"] = (
            f"{result['champion']} 是数据源记录的实际冠军。100% 表示赛果已知，不是赛前预测准确率。"
        )
    return data


@st.cache_data(ttl=30, show_spinner=False)
def fetch_final_result():
    try:
        results = api("GET", "/results", params={"snapshot_id": PRE_TOURNAMENT_SNAPSHOT})["results"]
        result = next(
            (
                r
                for r in results
                if not r.get("constraints")
                and r.get("snapshot_id") == PRE_TOURNAMENT_SNAPSHOT
                and r.get("status") == "completed"
            ),
            None,
        )
        if result is None:
            raise RuntimeError("尚无已保存的赛前预测")
        data = adapt_result(result)
        feed = fetch_live_feed()
        data["live_feed"] = feed
        data["bracket_payload"] = actual_bracket(feed)
        return {
            "data": data,
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
    feed = fetch_live_feed()
    return {
        "source_level": "external_real" if feed.get("fixtures") else "unavailable",
        "fixtures_count": len(feed.get("fixtures", [])),
        "user_message": feed.get("last_error")
        or feed.get("prediction_error")
        or "请刷新 API-Football 比赛数据",
    }


@st.cache_data(ttl=30, show_spinner=False)
def fetch_live_feed():
    try:
        return api("GET", "/data/status")
    except Exception as exc:
        return {"fixtures": [], "last_error": str(exc)}


def display_real_fixtures():
    feed = fetch_live_feed()
    details = [feed.get(k) for k in ("primary_error", "last_error", "prediction_error")]
    rows = feed.get("fixtures", [])
    source = feed.get("provider", "API-Football")
    if not rows and (feed.get("fallback") or {}).get("fixtures"):
        feed = feed["fallback"]
        rows = feed["fixtures"]
        source = feed["provider"]
        details.append(feed.get("limitation"))
    elif (feed.get("fallback") or {}).get("error"):
        details.append(feed["fallback"]["error"])
    if not rows:
        with st.expander("数据状态", expanded=False):
            st.caption("暂无可用赛事数据；当前展示赛前预测。")
            for detail in filter(None, details):
                st.caption(detail)
        return

    def score(pair):
        return (
            "—"
            if pair.get("home") is None or pair.get("away") is None
            else f"{pair['home']}–{pair['away']}"
        )

    with st.expander("赛程与比分 · " + source, expanded=False):
        st.caption(f"更新时间：{feed.get('fetched_at', '未知')}")
        for detail in filter(None, details):
            st.caption(detail)
        st.dataframe(
            [
                {
                    "开球时间": r["kickoff"],
                    "阶段": r["round"],
                    "主队": r["home"],
                    "客队": r["away"],
                    "状态": r["status"],
                    "比分": score(r["score"]),
                    "90分钟": score(r["score_90"]),
                    "加时": score(r["score_extra_time"]),
                    "点球": score(r["score_penalties"]),
                }
                for r in sorted(rows, key=lambda r: r["kickoff"])
            ],
            use_container_width=True,
            hide_index=True,
        )


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
        matches.extend(
            {
                "match_id": m["official_match_id"],
                "home_team": m["home"],
                "away_team": m["away"],
                "stage": "淘汰赛",
            }
            for m in snapshot.get("provider_fixtures", [])
            if m.get("official_match_id") and m["status"] in ("NS", "TBD", "PST")
        )
        return {
            "matches": matches,
            "sandbox_enabled": bool(matches),
            "source": "api",
            "stage_label": "小组赛",
        }
    except Exception:
        return {"matches": [], "sandbox_enabled": None, "source": "error"}


def _token():
    # Streamlit executes on the server; never send this credential to the browser.
    token = os.getenv("BACKEND_API_KEY", "").strip()
    if not token:
        raise RuntimeError("预测服务暂未就绪，请稍后重试。")
    return token


def _run(path, body):
    token = _token()
    job = api("POST", path, token, json=body)
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        status = api("GET", "/jobs/" + job["job_id"])
        if status["status"] == "completed":
            st.cache_data.clear()
            return api("GET", "/results/" + status["run_id"])
        if status["status"] in ("failed", "cancelled"):
            st.cache_data.clear()
            raise RuntimeError(status.get("error") or status["status"])
        time.sleep(1)
    raise RuntimeError("计算仍在后台进行，请稍后刷新结果。")


def call_agent_api(mode="llm_planner", use_llm=True, refresh_data=False):
    try:
        if use_llm:
            return _planned_workflow(
                "run_prediction_workflow",
                {
                    "snapshot_id": PRE_TOURNAMENT_SNAPSHOT,
                    "simulation_count": 2000,
                    "seed": 42,
                    "refresh_data": refresh_data,
                },
            )
        result = _run(
            "/data/refresh" if refresh_data else "/predictions",
            {"snapshot_id": PRE_TOURNAMENT_SNAPSHOT, "simulation_count": 2000, "seed": 42},
        )
        return result
    except Exception as exc:
        st.error(str(exc))
        return None


def _planned_workflow(tool, arguments):
    response = api(
        "POST",
        "/coordinator",
        _token(),
        json={
            "message": "请规划并执行：先查询赛事状态，然后执行一次指定工作流，最后解释本次结果。"
            "严格使用下列参数；refresh_data=false 表示赛前历史回放，禁止混入实际赛果。"
            f"工具 {tool}；参数 {json.dumps(arguments, ensure_ascii=False)}"
        },
    )
    trace = response.get("trace", [])
    st.session_state["coordinator_trace"] = trace
    result = next(
        (
            t["result"]
            for t in trace
            if t.get("success")
            and t.get("tool") == tool
            and t.get("result", {}).get("run_id")
            and t["result"].get("champion_distribution")
        ),
        None,
    )
    if result is None:
        raise RuntimeError("LLM 规划未完成工作流，请查看任务状态后重试。")
    if not arguments.get("refresh_data") and result.get("snapshot_id") != arguments["snapshot_id"]:
        raise RuntimeError("协调器使用了不同的数据版本，本次结果不用于页面展示。")
    explanation = next(
        (
            t["result"]
            for t in reversed(trace)
            if t.get("success")
            and t.get("tool") == "generate_explanation"
            and t["result"].get("run_id") == result["run_id"]
        ),
        None,
    )
    if explanation:
        st.session_state["llm_explanation"] = {
            "run_id": result["run_id"],
            "content": explanation["text"],
        }
    st.cache_data.clear()
    return result


def refresh_real_data():
    result = call_agent_api(use_llm=True, refresh_data=True)
    if result:
        return {
            "success": True,
            "steps": {
                "identify_surviving": {
                    "stage": "赛事结束" if result.get("status") == "observed" else "赛事进行中",
                    "surviving_teams": [
                        t for t, p in result["champion_distribution"].items() if p > 0
                    ],
                }
            },
        }
    return None


def call_scenario_simulate(match_id, forced_winner, simulation_count=1000):
    try:
        data = fetch_final_result()["data"]
        result = _planned_workflow(
            "run_scenario_workflow",
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
