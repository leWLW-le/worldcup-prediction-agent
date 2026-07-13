"""验证完整运行中 LLM Planner 是否真正工作"""
import sys, io
sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app.agents.worldcup_agent import WorldCupPredictionAgent

print("运行 llm_planner + use_llm=True ...")
agent = WorldCupPredictionAgent(seed=42)
state = agent.run(season=2026, mode="llm_planner", use_llm=True)

print(f"\n=== 结果 ===")
print(f"mode: {state.mode}")
print(f"use_llm: {state.use_llm}")
print(f"planner_summary: {state.planner_summary}")
print(f"tool_trace 数量: {len(state.tool_trace)}")

llm_steps = sum(1 for t in state.tool_trace if t.get("planner_type") == "llm")
rule_steps = sum(1 for t in state.tool_trace if t.get("planner_type") == "rule_fallback")
print(f"LLM 步骤: {llm_steps}")
print(f"规则兜底步骤: {rule_steps}")

print(f"\n--- tool_trace 详情 ---")
for t in state.tool_trace:
    print(f"  Step {t['step']}: {t['tool_name']} (planner_type={t['planner_type']}, success={t['success']})")

if llm_steps > 0:
    print(f"\n✅ 大模型真正参与了 {llm_steps} 步决策！")
else:
    print(f"\n❌ 大模型没有参与决策，全部是规则兜底。")
    print("   需要排查 _run_llm_planner 中的 LLMPlannerAgent 是否正确传入 use_llm=True")
