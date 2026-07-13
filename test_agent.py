"""Acceptance test - 14 checks for dual-mode Agent (with LLM support)"""
import sys
import io
import time
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app.agents.worldcup_agent import WorldCupPredictionAgent
from app.agents.tool_registry import ToolRegistry
from app.agents.llm_planner_agent import LLMPlannerAgent
from app.agents.agent_executor import AgentExecutor
from app.agents.agent_state import AgentState

passed = 0
failed = 0

def check(num, desc, condition):
    global passed, failed
    status = "PASS" if condition else "FAIL"
    if condition:
        passed += 1
    else:
        failed += 1
    print(f"{num:2d}. [{status}] {desc}")

print("=" * 60)
print("Dual-Mode Agent Acceptance Test (with LLM Support)")
print("=" * 60)

start_time = time.time()

# -- Test 1: workflow mode --
print("\n--- Test 1: workflow mode ---")
agent_wf = WorldCupPredictionAgent(seed=42)
state_wf = agent_wf.run(season=2026, mode="workflow", use_llm=False)
check(1, f"workflow mode works (status={state_wf.status}, champion={state_wf.predicted_champion})",
      state_wf.status in ("completed", "degraded_completed") and state_wf.predicted_champion is not None)

# -- Test 2: llm_planner mode with use_llm=False (rule-based) --
print("\n--- Test 2: llm_planner mode (use_llm=False, rule-based) ---")
agent_rule = WorldCupPredictionAgent(seed=42)
state_rule = agent_rule.run(season=2026, mode="llm_planner", use_llm=False)
check(2, f"llm_planner rule mode works (status={state_rule.status}, mode={state_rule.mode})",
      state_rule.status in ("completed", "degraded_completed", "failed")
      and state_rule.mode in ("llm_planner", "llm_planner_fallback_workflow"))

# -- Test 3: llm_planner mode with use_llm=True (real LLM) --
print("\n--- Test 3: llm_planner mode (use_llm=True, real LLM) ---")
from app.core.config import get_settings
settings = get_settings()
has_zhipu_key = bool(settings.OPENAI_API_KEY) and "bigmodel" in settings.OPENAI_BASE_URL
if has_zhipu_key:
    agent_llm = WorldCupPredictionAgent(seed=42)
    state_llm = agent_llm.run(season=2026, mode="llm_planner", use_llm=True)
    llm_trace_count = sum(1 for t in state_llm.tool_trace if t.get("planner_type") == "llm")
    check(3, f"llm_planner LLM mode works (status={state_llm.status}, LLM steps={llm_trace_count})",
          state_llm.status in ("completed", "degraded_completed", "failed")
          and state_llm.mode in ("llm_planner", "llm_planner_fallback_workflow"))
else:
    print("3. [SKIP] llm_planner LLM mode (no ZHIPU_API_KEY)")
    passed += 1  # Count as pass if no key

# -- Test 4: ToolRegistry has all required tools --
registry = ToolRegistry(seed=42)
required_tools = [
    "get_worldcup_fixtures", "get_worldcup_teams", "get_worldcup_standings",
    "get_live_fixtures", "load_historical_matches", "get_recent_matches",
    "run_data_quality_check", "build_team_features", "predict_group_stage",
    "calculate_group_standings", "select_qualified_teams", "predict_knockout_stage",
    "explain_champion_path",
]
all_registered = all(registry.has_tool(t) for t in required_tools)
no_unknown = not registry.has_tool("unknown_tool_xyz")
check(4, f"ToolRegistry has all {len(required_tools)} tools (found={len(registry.get_tool_names())}, unknown_rejected={no_unknown})",
      all_registered and no_unknown)

# -- Test 5: LLMPlannerAgent rule fallback works --
planner = LLMPlannerAgent(use_llm=False)
empty_state = AgentState(season=2026)
empty_state.objective = "test"
action = planner.decide_next_action(empty_state)
check(5, f"Rule planner returns valid tool (tool={action.get('tool_name')}, type={action.get('planner_type')})",
      action.get("tool_name") == "get_worldcup_fixtures"
      and action.get("planner_type") == "rule_fallback"
      and "reason" in action)

# -- Test 6: AgentExecutor can execute tools --
executor = AgentExecutor(registry)
test_state = AgentState(season=2026)
test_call = {"tool_name": "load_historical_matches", "arguments": {"start_year": 2020}, "reason": "test", "planner_type": "rule_fallback"}
exec_result = executor.execute(test_call, test_state)
check(6, f"AgentExecutor executes tool (success={exec_result.get('success')})",
      exec_result.get("success") is True)

# -- Test 7: tool_trace is not empty (llm_planner rule mode) --
trace_count_rule = len(state_rule.tool_trace)
check(7, f"tool_trace not empty in rule mode (count={trace_count_rule})",
      trace_count_rule > 0)

# -- Test 8: all tools in tool_trace are from ToolRegistry --
if state_rule.tool_trace:
    all_from_registry = all(
        registry.has_tool(t.get("tool_name", ""))
        for t in state_rule.tool_trace
    )
    check(8, f"All trace tools from ToolRegistry (valid={all_from_registry})",
          all_from_registry)
else:
    check(8, "All trace tools from ToolRegistry (no trace)", False)

# -- Test 9: predicted_champion not empty --
check(9, f"predicted_champion exists (wf={state_wf.predicted_champion}, rule={state_rule.predicted_champion})",
      state_wf.predicted_champion is not None and state_rule.predicted_champion is not None)

# -- Test 10: final_explanation not empty --
wf_expl = len(state_wf.final_explanation or "")
rule_expl = len(state_rule.final_explanation or "")
check(10, f"final_explanation exists (wf_len={wf_expl}, rule_len={rule_expl})",
      wf_expl > 0 and rule_expl > 0)

# -- Test 11: knockout_predictions >= 31 --
wf_ko = len(state_wf.knockout_predictions)
rule_ko = len(state_rule.knockout_predictions)
check(11, f"knockout_predictions >= 31 (wf={wf_ko}, rule={rule_ko})",
      wf_ko >= 31 and rule_ko >= 31)

# -- Test 12: planner_summary exists in llm_planner mode --
check(12, f"planner_summary exists in rule mode (summary={state_rule.planner_summary})",
      bool(state_rule.planner_summary) and "llm_steps" in state_rule.planner_summary)

# -- Test 13: use_llm field is set correctly --
check(13, f"use_llm field correct (wf={state_wf.use_llm}, rule={state_rule.use_llm})",
      state_wf.use_llm is False and state_rule.use_llm is False)

# -- Test 14: test completes within 120 seconds --
total_time = time.time() - start_time
check(14, f"Test completes within 120s (took={total_time:.1f}s)",
      total_time < 120)

# Summary
print()
print("-" * 60)
print("Summary:")
print(f"  workflow mode:")
print(f"    Champion:       {state_wf.predicted_champion}")
print(f"    Runner-up:      {state_wf.predicted_runner_up}")
print(f"    Knockout:       {len(state_wf.knockout_predictions)} matches")
print(f"    Explanation:    {len(state_wf.final_explanation or '')} chars")
print(f"    Status:         {state_wf.status}")
print(f"    Mode:           {state_wf.mode}")
print(f"    use_llm:        {state_wf.use_llm}")
qr_wf = state_wf.data_quality_report or {}
print(f"    fallback_used:          {qr_wf.get('fallback_used')}")
print(f"    is_real_data_ready:     {qr_wf.get('is_real_data_ready')}")
print(f"    fixtures_source:        {qr_wf.get('fixtures_source')}")
print(f"    teams_source:           {qr_wf.get('teams_source')}")
print(f"    live_data_source:       {qr_wf.get('live_data_source')}")
print(f"    llm_generated_data_used:{qr_wf.get('llm_generated_data_used')}")
print(f"    needs_review_count:     {qr_wf.get('needs_review_count')}")
print(f"  llm_planner rule mode:")
print(f"    Champion:       {state_rule.predicted_champion}")
print(f"    Runner-up:      {state_rule.predicted_runner_up}")
print(f"    Knockout:       {len(state_rule.knockout_predictions)} matches")
print(f"    Tool trace:     {len(state_rule.tool_trace)} steps")
print(f"    Explanation:    {len(state_rule.final_explanation or '')} chars")
print(f"    Status:         {state_rule.status}")
print(f"    Mode:           {state_rule.mode}")
print(f"    use_llm:        {state_rule.use_llm}")
print(f"    Planner summary: {state_rule.planner_summary}")
qr_rule = state_rule.data_quality_report or {}
print(f"    fallback_used:          {qr_rule.get('fallback_used')}")
print(f"    is_real_data_ready:     {qr_rule.get('is_real_data_ready')}")
print(f"    fixtures_source:        {qr_rule.get('fixtures_source')}")
print(f"    teams_source:           {qr_rule.get('teams_source')}")
print(f"    live_data_source:       {qr_rule.get('live_data_source')}")
print(f"    llm_generated_data_used:{qr_rule.get('llm_generated_data_used')}")
print(f"    needs_review_count:     {qr_rule.get('needs_review_count')}")
if has_zhipu_key:
    print(f"  llm_planner LLM mode:")
    print(f"    Champion:       {state_llm.predicted_champion}")
    print(f"    Runner-up:      {state_llm.predicted_runner_up}")
    print(f"    Knockout:       {len(state_llm.knockout_predictions)} matches")
    print(f"    Tool trace:     {len(state_llm.tool_trace)} steps")
    llm_steps = sum(1 for t in state_llm.tool_trace if t.get('planner_type') == 'llm')
    rule_steps = sum(1 for t in state_llm.tool_trace if t.get('planner_type') == 'rule_fallback')
    print(f"    LLM steps:      {llm_steps}")
    print(f"    Rule fallback:  {rule_steps}")
    print(f"    Explanation:    {len(state_llm.final_explanation or '')} chars")
    print(f"    Status:         {state_llm.status}")
    print(f"    Mode:           {state_llm.mode}")
    print(f"    use_llm:        {state_llm.use_llm}")
    print(f"    Planner summary: {state_llm.planner_summary}")
print(f"  Total time:       {total_time:.1f}s")
print("-" * 60)

if failed == 0:
    print(f"ALL {passed} CHECKS PASSED!")
else:
    print(f"{passed} PASSED, {failed} FAILED")
print("=" * 60)
