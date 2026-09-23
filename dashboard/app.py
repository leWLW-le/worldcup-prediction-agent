"""Production dashboard; all predictions come from V2 saved results."""

import json

import streamlit as st

from dashboard.api_client import api
from dashboard.components import show_result

st.set_page_config(page_title="World Cup Agent", layout="wide")
st.title("World Cup Prediction Agent")
st.caption("基于版本化数据的概率预测 · 真实晋级路径 · 情景分析")
# Do not silently proxy a server-side admin credential to anonymous visitors.
token = st.sidebar.text_input(
    "操作密钥", type="password", help="查询公开；预测、导入与协调器需要授权密钥。"
)
try:
    snapshots = api("GET", "/tournament-state")["snapshots"]
except Exception as exc:
    st.error(f"无法连接后端：{exc}")
    st.stop()

with st.sidebar.expander("导入赛事数据"):
    upload = st.file_uploader("版本化赛事快照 JSON", type=["json"])
    if st.button("验证并导入", disabled=not token or upload is None):
        try:
            response = api("POST", "/snapshots", token, json=json.load(upload))
            st.success(response["snapshot_id"])
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

if not snapshots:
    st.info("尚无赛事快照。请先导入含来源、历史比赛和固定淘汰赛关系的 JSON。")
else:
    chosen = st.selectbox(
        "赛事快照",
        snapshots,
        format_func=lambda s: f"{s['season']} · {s['as_of']} · {s['provenance']}",
    )
    if chosen["provenance"] != "verified":
        st.warning("此快照不是已验证真实数据；只可用于明确标记的本地演示。")
    count = st.slider("模拟次数", 100, 20000, 1000, 100)
    body = {"snapshot_id": chosen["snapshot_id"], "simulation_count": count, "seed": 42}
    left, right = st.columns(2)
    with left:
        if st.button("运行完整预测", disabled=not token):
            try:
                st.session_state["job"] = api("POST", "/predictions", token, json=body)["job_id"]
            except Exception as exc:
                st.error(str(exc))
    with right:
        if st.button("从 API-Football 刷新该快照赛程", disabled=not token):
            try:
                response = api("POST", "/snapshots/" + chosen["snapshot_id"] + "/refresh", token)
                st.success("已生成新快照：" + response["snapshot_id"])
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with st.expander("情景沙盘"):
        # Resolved direct participants only; backend also validates constraints.
        available = [
            f
            for f in chosen["fixtures"]
            if f["status"] == "scheduled"
            and f["home_source"].startswith("team:")
            and f["away_source"].startswith("team:")
        ]
        if available:
            fixture = st.selectbox(
                "比赛",
                available,
                format_func=lambda f: f"{f['home_source'][5:]} vs {f['away_source'][5:]}",
            )
            winner = st.selectbox(
                "假设晋级球队", [fixture["home_source"][5:], fixture["away_source"][5:]]
            )
            if st.button("运行情景分析", disabled=not token):
                try:
                    st.session_state["job"] = api(
                        "POST",
                        "/scenarios",
                        token,
                        json={**body, "fixture_id": fixture["fixture_id"], "forced_winner": winner},
                    )["job_id"]
                except Exception as exc:
                    st.error(str(exc))
        else:
            st.info("没有双方已确定且尚未结束的比赛。")


@st.fragment(run_every="2s")
def task_progress():
    job_id = st.session_state.get("job")
    if not job_id:
        return
    try:
        job = api("GET", "/jobs/" + job_id)
        st.write("任务状态", job["status"])
        if job["status"] == "running":
            if st.button("取消任务", disabled=not token):
                api("DELETE", "/jobs/" + job_id, token)
        elif job.get("run_id"):
            show_result(api("GET", "/results/" + job["run_id"]))
        elif job.get("error"):
            st.error(job["error"])
    except Exception as exc:
        st.error(str(exc))


task_progress()

with st.expander("历史结果与对比"):
    try:
        runs = api("GET", "/results")["results"]
        selected = st.multiselect(
            "选择 2–5 次同赛季运行",
            runs,
            format_func=lambda r: f"{r['run_id']} · {r['champion']} · {r['as_of']}",
        )
        if st.button("对比", disabled=not 2 <= len(selected) <= 5):
            st.json(api("POST", "/compare", json={"run_ids": [r["run_id"] for r in selected]}))
        if len(selected) == 1:
            show_result(selected[0])
            st.write(api("GET", "/results/" + selected[0]["run_id"] + "/explanation")["text"])
    except Exception as exc:
        st.error(str(exc))

st.subheader("任务协调器")
message = st.chat_input("查询赛事、预测冠军、运行假设情景或对比历史结果", disabled=not token)
if message:
    st.chat_message("user").write(message)
    try:
        with st.spinner("正在协调业务工具…"):
            response = api("POST", "/coordinator", token, json={"message": message})
        st.chat_message("assistant").write(response.get("narrative", response["status"]))
        st.caption("数值以业务工具返回的记录为准。")
        for result in response.get("authoritative_results", []):
            if "champion_distribution" in result:
                show_result(result)
        with st.expander("工具执行记录"):
            st.json(response["trace"])
    except Exception as exc:
        st.error(str(exc))
