"""
回归测试：正式冠军预测 snapshot 一致性（v2）

测试 4 项场景：
1. 最终 top5: England 0.2525 → 所有字段一致（champion, top_candidates, explanation）
2. 早期 Argentina/0.492 → 最终 England/0.2525 → explanation 必须使用 England
3. 矛盾 snapshot → _validate_prediction_snapshot 校验失败
4. 连续 10 次 → run_id 不变，所有字段一致
"""

import sys
import types
import json
import os
from pathlib import Path
from unittest.mock import MagicMock
from copy import deepcopy

# ── Mock streamlit ──
st = types.ModuleType("streamlit")
st.set_page_config = lambda **kw: None
st.markdown = lambda *a, **kw: None
st.error = lambda *a, **kw: None
st.warning = lambda *a, **kw: None
st.info = lambda *a, **kw: None
st.success = lambda *a, **kw: None
st.spinner = lambda *a, **kw: MagicMock()
st.columns = lambda *a, **kw: [MagicMock() for _ in range(max(a) if a else 1)]
st.tabs = lambda *a, **kw: [MagicMock() for _ in range(max(a) if a else 1)]
st.expander = lambda *a, **kw: MagicMock()
st.image = lambda *a, **kw: None
st.metric = lambda *a, **kw: None
st.progress = lambda *a, **kw: None
st.divider = lambda *a, **kw: None
st.caption = lambda *a, **kw: None
st.latex = lambda *a, **kw: None
st.button = lambda *a, **kw: False
st.session_state = {}
st.cache_resource = MagicMock()
st.cache_resource.clear = lambda: None

def _mock_cache_data(**kw):
    def decorator(f):
        f.clear = lambda: None
        return f
    return decorator

st.cache_data = _mock_cache_data
sys.modules["streamlit"] = st

# ── 项目路径 ──
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── 导入被测模块 ──
import debug_dashboard as dd
from app.agents.worldcup_agent import _validate_prediction_snapshot

passed = 0
failed = 0


def check(condition, msg):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {msg}")
    else:
        failed += 1
        print(f"  ❌ {msg}")


def _make_snapshot(champion, champ_prob_01, top5, explanation, run_id="run_test123",
                   top_candidates=None):
    """构造完整的 prediction snapshot"""
    return {
        "run_id": run_id,
        "champion": champion,
        "predicted_champion": champion,
        "champion_probability": champ_prob_01,
        "top5": top5,
        "top_candidates": top_candidates if top_candidates is not None else deepcopy(top5),
        "surviving_teams": [t["team"] for t in top5],
        "stage": "semi_finals",
        "stage_info": {"stage": "semi_finals", "stage_label": "四强"},
        "bracket_payload": {},
        "data_status": {},
        "model_status": {},
        "explanation": explanation,
        "top_contenders": [],
        "agent_steps_summary": [],
        "model_version": "ensemble_v2",
        "simulation_count": 10000,
        "data_source": "",
        "historical_samples": 6000,
        "generated_at": "2026-07-14T10:00:00",
        "status": "completed",
    }


def _make_fetch_result(snapshot):
    """构造 fetch_final_result 返回值"""
    return {
        "data": snapshot,
        "source": "api",
        "is_fallback": False,
        "run_id": snapshot["run_id"],
        "generated_at": snapshot["generated_at"],
        "error": None,
    }


# ══════════════════════════════════════════════════
# 测试 1：最终 top5 England 0.2525 → 所有字段一致
# ══════════════════════════════════════════════════
print("\n" + "=" * 60)
print("测试 1：最终 top5 England 0.2525 → 所有字段一致")
print("=" * 60)

top5_eng = [
    {"team": "England", "probability": 0.2525},
    {"team": "France", "probability": 0.2496},
    {"team": "Argentina", "probability": 0.2494},
    {"team": "Spain", "probability": 0.2485},
]

explanation_eng = {
    "title": "为什么预测 England 夺冠？",
    "content": "## 为什么预测 England 夺冠？\n\n系统给出 25.25% 的夺冠概率。England 以 25.25% 的夺冠概率领跑群雄。",
    "probability": 25.25,
    "champion": "England",
    "champion_probability": 0.2525,
    "run_id": "run_eng12345",
    "source": "fallback",
}

snapshot_eng = _make_snapshot(
    champion="England",
    champ_prob_01=0.2525,
    top5=top5_eng,
    explanation=explanation_eng,
    run_id="run_eng12345",
)

# 1a. _validate_prediction_snapshot 通过
try:
    _validate_prediction_snapshot(snapshot_eng)
    check(True, "_validate_prediction_snapshot 通过")
except AssertionError as e:
    check(False, f"_validate_prediction_snapshot 不应失败: {e}")

# 1b. champion == top5[0].team
check(snapshot_eng["champion"] == "England", "champion = England")
check(snapshot_eng["champion"] == snapshot_eng["top5"][0]["team"],
      "champion == top5[0].team")

# 1c. champion_probability == top5[0].probability
check(abs(snapshot_eng["champion_probability"] - 0.2525) < 1e-9,
      "champion_probability = 0.2525")

# 1d. top_candidates[0] == England / 0.2525
check(snapshot_eng["top_candidates"][0]["team"] == "England",
      "top_candidates[0].team = England")
check(abs(snapshot_eng["top_candidates"][0]["probability"] - 0.2525) < 1e-9,
      "top_candidates[0].probability = 0.2525")

# 1e. explanation 字段
check(snapshot_eng["explanation"]["champion"] == "England",
      "explanation.champion = England")
check(abs(snapshot_eng["explanation"]["champion_probability"] - 0.2525) < 1e-9,
      "explanation.champion_probability = 0.2525")
check(snapshot_eng["explanation"]["probability"] == 25.25,
      "explanation.probability = 25.25")
check("England" in snapshot_eng["explanation"]["title"],
      "explanation.title 包含 England")
check(snapshot_eng["explanation"]["run_id"] == "run_eng12345",
      "explanation.run_id == snapshot.run_id")

# 1f. 前端一致性校验
result_eng = _make_fetch_result(snapshot_eng)
warnings_eng = dd.validate_data_consistency(result_eng)
check(len(warnings_eng) == 0,
      f"前端无一致性警告 (got {len(warnings_eng)}: {warnings_eng})")


# ══════════════════════════════════════════════════
# 测试 2：早期 Argentina/0.492 → 最终 England/0.2525
# explanation 必须使用 England
# ══════════════════════════════════════════════════
print("\n" + "=" * 60)
print("测试 2：早期 Argentina/0.492 → 最终 England/0.2525 → explanation 必须用 England")
print("=" * 60)

# 模拟：如果 explanation 错误地使用了 Argentina
explanation_wrong = {
    "title": "为什么预测 Argentina 夺冠？",
    "content": "Argentina 以 49.2% 的夺冠概率领跑。",
    "probability": 49.2,
    "champion": "Argentina",
    "champion_probability": 0.492,
    "run_id": "run_eng12345",  # 同一个 run_id
    "source": "fallback",
}

snapshot_wrong = _make_snapshot(
    champion="England",
    champ_prob_01=0.2525,
    top5=top5_eng,
    explanation=explanation_wrong,
    run_id="run_eng12345",
)

# 2a. _validate_prediction_snapshot 应该失败（explanation.champion != champion）
try:
    _validate_prediction_snapshot(snapshot_wrong)
    check(False, "_validate_prediction_snapshot 应检测到 explanation.champion 不匹配")
except AssertionError as e:
    check(True, f"_validate_prediction_snapshot 正确拒绝: {e}")

# 2b. 前端一致性校验也应检测到
result_wrong = _make_fetch_result(snapshot_wrong)
warnings_wrong = dd.validate_data_consistency(result_wrong)
check(len(warnings_wrong) > 0,
      f"前端检测到不一致 (got {len(warnings_wrong)} warnings)")
champ_warning = any("Argentina" in w for w in warnings_wrong)
check(champ_warning, f"检测到 champion 不匹配: {warnings_wrong}")


# ══════════════════════════════════════════════════
# 测试 3：矛盾 snapshot → 校验失败
# ══════════════════════════════════════════════════
print("\n" + "=" * 60)
print("测试 3：矛盾 snapshot → 校验失败，不得保存为 completed")
print("=" * 60)

# 3a. champion != top5[0].team
snapshot_contradict1 = _make_snapshot(
    champion="England",
    champ_prob_01=0.2525,
    top5=[{"team": "Argentina", "probability": 0.492}],
    explanation={"champion": "England", "champion_probability": 0.2525, "run_id": "run_x",
                 "title": "", "content": "", "probability": 25.25, "source": "fallback"},
    run_id="run_x",
)
try:
    _validate_prediction_snapshot(snapshot_contradict1)
    check(False, "champion != top5[0].team 应失败")
except AssertionError:
    check(True, "champion != top5[0].team 正确拒绝")

# 3b. top_candidates[0] != champion
snapshot_contradict2 = _make_snapshot(
    champion="England",
    champ_prob_01=0.2525,
    top5=top5_eng,
    top_candidates=[{"team": "Argentina", "probability": 0.492}],
    explanation={"champion": "England", "champion_probability": 0.2525, "run_id": "run_x",
                 "title": "", "content": "", "probability": 25.25, "source": "fallback"},
    run_id="run_x",
)
try:
    _validate_prediction_snapshot(snapshot_contradict2)
    check(False, "top_candidates[0] != champion 应失败")
except AssertionError:
    check(True, "top_candidates[0] != champion 正确拒绝")

# 3c. explanation.run_id != snapshot.run_id
snapshot_contradict3 = _make_snapshot(
    champion="England",
    champ_prob_01=0.2525,
    top5=top5_eng,
    explanation={"champion": "England", "champion_probability": 0.2525,
                 "run_id": "run_OLD", "title": "", "content": "",
                 "probability": 25.25, "source": "fallback"},
    run_id="run_NEW",
)
try:
    _validate_prediction_snapshot(snapshot_contradict3)
    check(False, "explanation.run_id != snapshot.run_id 应失败")
except AssertionError:
    check(True, "explanation.run_id != snapshot.run_id 正确拒绝")

# 3d. status != completed
snapshot_not_complete = _make_snapshot(
    champion="England",
    champ_prob_01=0.2525,
    top5=top5_eng,
    explanation={"champion": "England", "champion_probability": 0.2525,
                 "run_id": "run_x", "title": "", "content": "",
                 "probability": 25.25, "source": "fallback"},
    run_id="run_x",
)
snapshot_not_complete["status"] = "building"
try:
    _validate_prediction_snapshot(snapshot_not_complete)
    check(False, "status=building 应失败")
except AssertionError:
    check(True, "status != completed 正确拒绝")


# ══════════════════════════════════════════════════
# 测试 4：连续 10 次 → run_id 不变，所有字段一致
# ══════════════════════════════════════════════════
print("\n" + "=" * 60)
print("测试 4：连续 10 次渲染 → run_id 不变，所有字段一致")
print("=" * 60)

run_ids = set()
all_consistent = True

for i in range(10):
    result = _make_fetch_result(snapshot_eng)
    run_ids.add(result["run_id"])
    w = dd.validate_data_consistency(result)
    if len(w) > 0:
        all_consistent = False
        break

check(len(run_ids) == 1, f"run_id 唯一 (got {len(run_ids)}: {run_ids})")
check(all_consistent, "10 次渲染全部通过一致性校验")


# ══════════════════════════════════════════════════
# 汇总
# ══════════════════════════════════════════════════
print("\n" + "=" * 60)
total = passed + failed
print(f"结果: {passed}/{total} 通过, {failed}/{total} 失败")
print("=" * 60)

if failed > 0:
    sys.exit(1)
else:
    print("✅ 全部通过！")
    sys.exit(0)
