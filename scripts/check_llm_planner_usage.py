"""
诊断脚本：检测大模型是否真正参与了工具选择决策

运行方式：
    python scripts/check_llm_planner_usage.py

判断规则：
    - llm_steps > 0 且 tool_trace 中存在 planner_type="llm"
      → 大模型规划器已调用，大模型参与了工具选择
    - llm_steps = 0 或无 planner_type="llm"
      → 大模型没有真正参与工具选择，当前是规则/固定流程兜底
    - workflow_fallback_used = True
      → 大模型参与过规划，但最终回退到固定流程
"""

import sys
import io
from pathlib import Path

# 确保项目根目录在 sys.path 中
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.agents.worldcup_agent import WorldCupPredictionAgent


def check_llm_planner_usage():
    print("=" * 60)
    print("  LLM Planner 使用诊断")
    print("=" * 60)
    print()

    # 运行 Agent
    print("正在运行 agent.run(mode='llm_planner', use_llm=True) ...")
    print()
    agent = WorldCupPredictionAgent(seed=42)
    state = agent.run(season=2026, mode="llm_planner", use_llm=True)

    # 提取关键字段
    mode = state.mode
    use_llm = state.use_llm
    ps = state.planner_summary
    tt = state.tool_trace

    llm_steps = sum(1 for t in tt if t.get("planner_type") == "llm")
    rule_steps = sum(1 for t in tt if t.get("planner_type") == "rule_fallback")
    total_steps = len(tt)
    wf_fallback = ps.get("workflow_fallback_used", False) if ps else False

    # 输出诊断结果
    print("-" * 60)
    print("  诊断结果")
    print("-" * 60)
    print(f"  1. mode              = {mode}")
    print(f"  2. use_llm           = {use_llm}")
    print(f"  3. planner_summary   = {ps}")
    print(f"  4. tool_trace 总步数 = {total_steps}")
    print(f"  5. LLM 决策步数      = {llm_steps}")
    print(f"  6. 规则兜底步数      = {rule_steps}")
    print(f"  7. 回退固定流程      = {wf_fallback}")
    print()

    # 前 10 条 tool_trace
    print("-" * 60)
    print("  前 10 条 tool_trace")
    print("-" * 60)
    for i, t in enumerate(tt[:10]):
        step = t.get("step", i + 1)
        tool = t.get("tool_name", "?")
        pt = t.get("planner_type", "?")
        reason = t.get("reason", "")[:60]
        success = t.get("success", None)
        error = t.get("error_type", t.get("error", None))
        msg = t.get("message", "")
        status = "OK" if success else ("FAIL" if success is False else "?")
        err_str = f" error={error}" if error else ""
        msg_str = f" - {msg[:50]}" if msg else ""
        print(f"  Step {step}: {tool} | planner_type={pt} | {status}{err_str}{msg_str}")
        if reason:
            print(f"           reason: {reason}")
    print()

    # 最终判断
    print("=" * 60)
    if llm_steps > 0 and any(t.get("planner_type") == "llm" for t in tt):
        print("  ✅ 大模型规划器已调用，大模型参与了工具选择。")
        print(f"     共 {llm_steps} 步由大模型决策。")
    else:
        print("  ❌ 大模型没有真正参与工具选择，当前是规则/固定流程兜底。")

    if wf_fallback:
        print()
        print("  ⚠️  大模型参与过规划，但最终回退到固定流程。")
        print("     请检查工具调用是否失败、API 是否限流。")

    print("=" * 60)


if __name__ == "__main__":
    check_llm_planner_usage()
