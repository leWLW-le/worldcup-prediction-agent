"""
strict 模式诊断脚本

运行 llm_planner_strict 模式，输出每步 tool_trace，检查核心预测工具调用和完成条件。

运行：python scripts/check_prediction_agent_strict.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")


def main():
    print("=" * 60)
    print("strict 模式验收")
    print("=" * 60)

    from app.agents.worldcup_agent import WorldCupPredictionAgent

    agent = WorldCupPredictionAgent(seed=42)
    state = agent.run(season=2026, mode="llm_planner_strict", use_llm=True)

    # 基本信息
    print(f"\n- mode: {state.mode}")
    print(f"- use_llm: {state.use_llm}")
    print(f"- status: {state.status}")

    # 统计
    llm_steps = sum(1 for t in state.tool_trace if t.get("planner_type") == "llm")
    rule_steps = sum(1 for t in state.tool_trace if t.get("planner_type") == "rule_fallback")
    workflow_fallback = state.mode == "llm_planner_fallback_workflow"
    print(f"- llm_steps: {llm_steps}")
    print(f"- rule_fallback_steps: {rule_steps}")
    print(f"- workflow_fallback_used: {workflow_fallback}")
    print(f"- tool_trace 总步数: {len(state.tool_trace)}")

    # 输出每步 tool_trace
    print(f"\n--- 工具调用轨迹 ---")
    for trace in state.tool_trace:
        step = trace.get("step", "?")
        tool = trace.get("tool_name", "?")
        planner = trace.get("planner_type", "?")
        success = trace.get("success", False)
        error = trace.get("error_type")
        reason = trace.get("reason", "")
        status_icon = "[OK]" if success else "[FAIL]"
        error_str = f" ({error})" if error else ""
        print(f"  Step {step}: {status_icon} [{planner}] {tool}{error_str}")
        print(f"    reason: {reason}")
        if trace.get("state_updates"):
            print(f"    state_updates: {trace.get('state_updates')}")

    # 检查核心预测工具
    core_tools = [
        "build_team_features",
        "predict_knockout_bracket",
        "build_visualization_payload",
        "generate_final_explanation",
    ]
    called_tools = {t.get("tool_name") for t in state.tool_trace if t.get("success")}
    missing_tools = [t for t in core_tools if t not in called_tools]
    print(f"\n--- 核心预测工具调用 ---")
    for tool in core_tools:
        called = tool in called_tools
        icon = "[OK]" if called else "[FAIL]"
        print(f"  {icon} {tool}")

    # predict_champion 可选（冠军可能在 predict_knockout_bracket 中已预测）
    champion_predicted = state.has_champion_prediction
    predict_champion_called = "predict_champion" in called_tools
    print(f"  {'[OK]' if predict_champion_called else '[INFO]'} predict_champion (单独调用: {predict_champion_called}, 冠军已预测: {champion_predicted})")

    # 完成条件
    checks = {
        "has_champion_prediction": state.has_champion_prediction,
        "has_visualization_payload": state.has_visualization_payload,
        "has_final_explanation": state.has_final_explanation,
    }
    missing_state = [k for k, v in checks.items() if not v]
    print(f"\n--- 完成条件 ---")
    for field, value in checks.items():
        icon = "[OK]" if value else "[FAIL]"
        print(f"  {icon} {field} = {value}")

    # 失败工具
    failed_tools = state.failed_tools
    if failed_tools:
        print(f"\n- 失败工具：{failed_tools}")

    # 最后成功步骤
    last_successful = None
    for trace in reversed(state.tool_trace):
        if trace.get("success"):
            last_successful = trace.get("tool_name")
            break

    # 判断是否通过
    has_llm_steps = llm_steps > 0
    has_llm_traces = any(t.get("planner_type") == "llm" for t in state.tool_trace)
    all_core_called = len(missing_tools) == 0
    all_state_complete = len(missing_state) == 0

    passed = (
        state.mode == "llm_planner_strict"
        and state.use_llm
        and state.status == "completed"
        and not workflow_fallback
        and has_llm_steps
        and has_llm_traces
        and all_core_called
        and champion_predicted  # 冠军必须已预测（不一定需要单独调用 predict_champion）
        and state.has_visualization_payload
        and state.has_final_explanation
    )

    # 总结
    print("\n" + "=" * 60)
    if passed:
        print("[OK] strict 模式验收通过：大模型已自主调用工具完成预测。")
    else:
        print("[FAIL] strict 模式验收失败")
        print(f"  - missing_tools: {missing_tools}")
        print(f"  - missing_state: {missing_state}")
        print(f"  - failed_tools: {failed_tools}")
        print(f"  - last_successful_step: {last_successful}")
        print(f"  - stop_reason: {state.errors[-1] if state.errors else 'unknown'}")
    print("=" * 60)

    return passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
