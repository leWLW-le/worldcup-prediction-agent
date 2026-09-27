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
        results = api("GET", "/results")["results"]
        result = next((r for r in results if not r.get("constraints")), None)
        if result is None:
            raise RuntimeError("尚无已保存的正式预测")
        data = adapt_result(result)
        feed = fetch_live_feed()
        data["live_feed"] = feed
        if feed.get("fixtures"):
            same = feed.get("snapshot_id") == result["snapshot_id"]
            count = sum(r["status"] in ("FT", "AET", "PEN") for r in feed["fixtures"])
            data["data_status"] = {
                "source_level": "external_real",
                "fixtures_count": len(feed["fixtures"]),
                "user_message": f"{feed.get('provider', 'API-Football')} · 抓取时间 {feed['fetched_at']} · {count} 场已结束"
                + (
                    " · 预测已同步"
                    if same
                    else f" · 下方预测仍基于 {result['as_of']}，尚未同步最新赛果"
                ),
            }
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
    if feed.get("primary_error"):
        st.warning(feed["primary_error"] + "；当前采用原有 football-data.org 通道。")
    if feed.get("last_error") or feed.get("prediction_error"):
        st.warning(feed.get("last_error") or feed.get("prediction_error"))
    if feed.get("configured") is False:
        st.warning("后端尚未配置 API-Football 密钥，当前不能获取真实赛事数据。")
    rows = feed.get("fixtures", [])
    source = feed.get("provider", "API-Football")
    if not rows and (feed.get("fallback") or {}).get("fixtures"):
        feed = feed["fallback"]
        rows = feed["fixtures"]
        source = feed["provider"]
        st.info(feed["limitation"])
    elif (feed.get("fallback") or {}).get("error"):
        st.warning(feed["fallback"]["error"])
    if not rows:
        return

    def score(pair):
        return (
            "—"
            if pair.get("home") is None or pair.get("away") is None
            else f"{pair['home']}–{pair['away']}"
        )

    with st.expander("📡 真实赛程与比分 · " + source, expanded=True):
        st.caption(f"上次成功抓取：{feed.get('fetched_at')}；比分来自赛事接口，非模型模拟。")
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


@st.dialog("操作授权")
def _request_token():
    token = st.text_input("操作密钥", type="password", key="operator_token_input")
    st.caption("仅用于本次浏览会话，不向匿名访客提供服务端密钥。")
    if st.button("保存到当前会话"):
        st.session_state["operator_token"] = token
        st.rerun()


def _token():
    if fetch_live_feed().get("manual_operations_configured") is False:
        st.error("后端管理员操作密钥尚未配置，手动刷新暂不可用；自动刷新状态见数据提示。")
        st.stop()
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
            st.cache_data.clear()
            return api("GET", "/results/" + status["run_id"])
        if status["status"] in ("failed", "cancelled"):
            st.cache_data.clear()
            raise RuntimeError(status.get("error") or status["status"])
        time.sleep(1)
    raise RuntimeError("计算仍在后台进行，请稍后刷新结果。")


def call_agent_api(mode="llm_planner", use_llm=True):
    try:
        snapshots = api("GET", "/tournament-state")["snapshots"]
        current = next(s for s in snapshots if s.get("group_stage"))
        result = _run(
            "/data/refresh",
            {"snapshot_id": current["snapshot_id"], "simulation_count": 2000, "seed": 42},
        )
        if use_llm:
            try:
                explanation = api(
                    "POST",
                    "/coordinator",
                    _token(),
                    json={
                        "message": f"只调用 generate_explanation，解释已保存结果 {result['run_id']}；不要重新预测。"
                    },
                )
                st.session_state["llm_explanation"] = {
                    "run_id": result["run_id"],
                    "content": explanation.get("narrative", ""),
                }
            except Exception:
                st.info("预测已完成，LLM 暂不可用，显示基于真实模型结果的模板解释。")
        return result
    except Exception as exc:
        st.error(str(exc))
        return None


def refresh_real_data():
    result = call_agent_api(use_llm=False)
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
