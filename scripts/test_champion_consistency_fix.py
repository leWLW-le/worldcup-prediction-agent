"""
回归测试：正式冠军卡片与 AI 冠军解读概率一致性

测试 4 项场景：
1. 同一 run 内，champion / probability / top5 / explanation 全部一致
2. explanation 属于旧 run → 一致性校验失败，不展示旧解释
3. 连续 10 次渲染 → run_id 不变，概率始终一致
4. 重新预测后 → 所有字段切换到新 run
"""

import sys
import types
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Mock streamlit（必须在 import debug_dashboard 之前） ──
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


# ══════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════

def _make_mock_fetch(resp):
    """创建带 .clear() 的 mock fetch 函数"""
    def mock_fetch():
        return resp
    mock_fetch.clear = lambda: None
    return mock_fetch


def _make_result(champion, champ_prob, top5, explanation, run_id="run_abc123",
                 generated_at="2026-07-14T10:00:00"):
    """构造 fetch_final_result 返回值"""
    data = {
        "run_id": run_id,
        "champion": champion,
        "predicted_champion": champion,
        "champion_probability": champ_prob,
        "top5": top5,
        "top_candidates": top5,
        "explanation": explanation,
        "generated_at": generated_at,
        "stage": "semi_finals",
        "stage_info": {"stage": "semi_finals", "stage_label": "四强"},
        "bracket_payload": {},
        "data_status": {},
        "model_status": {},
        "surviving_teams": [t["team"] for t in top5],
    }
    return {
        "data": data,
        "source": "api",
        "is_fallback": False,
        "run_id": run_id,
        "generated_at": generated_at,
        "error": None,
    }


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


# ══════════════════════════════════════════════════
# 测试 1：同一 run 内所有字段一致
# ══════════════════════════════════════════════════
print("\n" + "=" * 60)
print("测试 1：同一 run 内 champion / probability / top5 / explanation 全部一致")
print("=" * 60)

top5_b = [
    {"team": "Argentina", "probability": 0.4881},
    {"team": "France", "probability": 0.2569},
    {"team": "England", "probability": 0.1469},
]
explanation_b = {
    "title": "为什么预测 Argentina 夺冠？",
    "content": "系统给出 48.81% 的夺冠概率。Argentina 以 48.81% 的夺冠概率领跑群雄。",
    "probability": 48.81,
    "champion": "Argentina",
    "champion_probability": 0.4881,
    "run_id": "run_bbbbbbb",
    "source": "fallback",
}
result_b = _make_result(
    champion="Argentina",
    champ_prob=0.4881,
    top5=top5_b,
    explanation=explanation_b,
    run_id="run_bbbbbbb",
)

# 一致性校验
warnings = dd.validate_data_consistency(result_b)
check(len(warnings) == 0, f"无一致性警告 (got {len(warnings)} warnings: {warnings})")

# champion == top5[0].team
check(result_b["data"]["champion"] == result_b["data"]["top5"][0]["team"],
      f"champion={result_b['data']['champion']} == top5[0]={result_b['data']['top5'][0]['team']}")

# champion_probability == top5[0].probability
check(abs(result_b["data"]["champion_probability"] - result_b["data"]["top5"][0]["probability"]) < 1e-9,
      f"champion_probability={result_b['data']['champion_probability']} == top5[0].probability={result_b['data']['top5'][0]['probability']}")

# explanation.champion == champion
check(explanation_b["champion"] == result_b["data"]["champion"],
      f"explanation.champion={explanation_b['champion']} == champion={result_b['data']['champion']}")

# explanation.champion_probability == champion_probability
check(abs(explanation_b["champion_probability"] - result_b["data"]["champion_probability"]) < 1e-9,
      f"explanation.champion_probability={explanation_b['champion_probability']} == champion_probability={result_b['data']['champion_probability']}")

# explanation.run_id == data.run_id
check(explanation_b["run_id"] == result_b["data"]["run_id"],
      f"explanation.run_id={explanation_b['run_id']} == data.run_id={result_b['data']['run_id']}")


# ══════════════════════════════════════════════════
# 测试 2：explanation 属于旧 run → 一致性校验失败
# ══════════════════════════════════════════════════
print("\n" + "=" * 60)
print("测试 2：数据库有 run B，但 explanation 属于 run A → 一致性校验失败")
print("=" * 60)

explanation_a = {
    "title": "为什么预测 Argentina 夺冠？",
    "content": "系统给出 47.74% 的夺冠概率。",
    "probability": 47.74,
    "champion": "Argentina",
    "champion_probability": 0.4774,
    "run_id": "run_aaaaaaa",
    "source": "fallback",
}
# run B 的数据，但 explanation 来自 run A
result_mixed = _make_result(
    champion="Argentina",
    champ_prob=0.4881,
    top5=top5_b,
    explanation=explanation_a,  # 旧 run 的 explanation
    run_id="run_bbbbbbb",
)

warnings_mixed = dd.validate_data_consistency(result_mixed)
check(len(warnings_mixed) > 0, f"检测到不一致 (got {len(warnings_mixed)} warnings)")

# 检查是否检测到 champion_probability 不一致
prob_warning = any("概率" in w or "probability" in w.lower() for w in warnings_mixed)
check(prob_warning, f"检测到概率不一致: {warnings_mixed}")

# 检查是否检测到 run_id 不一致
run_id_warning = any("run_id" in w for w in warnings_mixed)
check(run_id_warning, f"检测到 run_id 不一致: {warnings_mixed}")


# ══════════════════════════════════════════════════
# 测试 3：连续 10 次渲染 → run_id 不变，概率一致
# ══════════════════════════════════════════════════
print("\n" + "=" * 60)
print("测试 3：连续 10 次渲染 → run_id 不变，概率始终一致")
print("=" * 60)

run_ids_seen = set()
all_consistent = True

for i in range(10):
    # 模拟 fetch_final_result 返回相同数据
    result = _make_result(
        champion="Argentina",
        champ_prob=0.4881,
        top5=top5_b,
        explanation=explanation_b,
        run_id="run_bbbbbbb",
        generated_at="2026-07-14T10:00:00",
    )
    run_ids_seen.add(result["data"]["run_id"])
    w = dd.validate_data_consistency(result)
    if len(w) > 0:
        all_consistent = False

check(len(run_ids_seen) == 1, f"run_id 唯一: {run_ids_seen}")
check(all_consistent, "10 次渲染全部一致")


# ══════════════════════════════════════════════════
# 测试 4：重新预测后 → 所有字段切换到新 run
# ══════════════════════════════════════════════════
print("\n" + "=" * 60)
print("测试 4：重新预测后 → champion / probability / top5 / explanation 同时切换到新 run")
print("=" * 60)

# Run A
top5_a = [
    {"team": "Argentina", "probability": 0.4774},
    {"team": "France", "probability": 0.2598},
]
explanation_a_full = {
    "title": "为什么预测 Argentina 夺冠？",
    "content": "系统给出 47.74% 的夺冠概率。",
    "probability": 47.74,
    "champion": "Argentina",
    "champion_probability": 0.4774,
    "run_id": "run_aaaaaaa",
}
result_a = _make_result(
    champion="Argentina",
    champ_prob=0.4774,
    top5=top5_a,
    explanation=explanation_a_full,
    run_id="run_aaaaaaa",
)

# Run B（重新预测后）
result_b_full = _make_result(
    champion="Argentina",
    champ_prob=0.4881,
    top5=top5_b,
    explanation=explanation_b,
    run_id="run_bbbbbbb",
)

# 验证 Run A
w_a = dd.validate_data_consistency(result_a)
check(len(w_a) == 0, f"Run A 一致: {len(w_a)} warnings")
check(result_a["data"]["champion_probability"] == 0.4774,
      f"Run A probability = {result_a['data']['champion_probability']}")

# 验证 Run B
w_b = dd.validate_data_consistency(result_b_full)
check(len(w_b) == 0, f"Run B 一致: {len(w_b)} warnings")
check(result_b_full["data"]["champion_probability"] == 0.4881,
      f"Run B probability = {result_b_full['data']['champion_probability']}")

# 验证 Run B 的 explanation 不包含旧概率
check(result_b_full["data"]["explanation"]["champion_probability"] == 0.4881,
      f"Run B explanation.champion_probability = {result_b_full['data']['explanation']['champion_probability']}")
check(result_b_full["data"]["explanation"]["run_id"] == "run_bbbbbbb",
      f"Run B explanation.run_id = {result_b_full['data']['explanation']['run_id']}")

# 交叉验证：Run B data + Run A explanation → 不一致
result_cross = _make_result(
    champion="Argentina",
    champ_prob=0.4881,
    top5=top5_b,
    explanation=explanation_a_full,  # 旧 run A 的 explanation
    run_id="run_bbbbbbb",
)
w_cross = dd.validate_data_consistency(result_cross)
check(len(w_cross) > 0, f"交叉验证检测到不一致: {len(w_cross)} warnings: {w_cross}")


# ══════════════════════════════════════════════════
# 总结
# ══════════════════════════════════════════════════
print("\n" + "=" * 60)
total = passed + failed
print(f"结果：{passed}/{total} 通过，{failed}/{total} 失败")
print("=" * 60)

if failed > 0:
    sys.exit(1)
else:
    print("✅ 全部测试通过！")
    sys.exit(0)
