"""诊断 LLM Planner 是否真正在工作"""
import sys, io, logging
sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')

from app.agents.llm_planner_agent import LLMPlannerAgent
from app.agents.agent_state import AgentState
from app.core.config import get_settings

settings = get_settings()
print(f"API_KEY: {settings.OPENAI_API_KEY[:20]}...")
print(f"BASE_URL: {settings.OPENAI_BASE_URL}")
print(f"MODEL: {settings.OPENAI_MODEL}")
print()

# 1. 测试 LLM 初始化
print("=== 1. 测试 LLM 初始化 ===")
planner = LLMPlannerAgent(use_llm=True, timeout_seconds=15)
llm = planner._get_llm()
print(f"LLM 对象: {llm}")
print(f"LLM 类型: {type(llm).__name__ if llm else 'None'}")
print()

# 2. 测试 LLM 决策（空状态）
print("=== 2. 测试 LLM 决策（空状态）===")
state = AgentState(season=2026)
state.objective = "Predict 2026 World Cup champion"

action = planner.decide_next_action(state)
print(f"tool_name: {action.get('tool_name')}")
print(f"planner_type: {action.get('planner_type')}")
print(f"reason: {action.get('reason')}")
print()

# 3. 手动测试 _call_llm_for_decision
print("=== 3. 手动测试 _call_llm_for_decision ===")
system_prompt = planner._build_system_prompt()
user_prompt = planner._build_user_prompt(state)
print(f"system_prompt 长度: {len(system_prompt)}")
print(f"user_prompt 长度: {len(user_prompt)}")

result = planner._call_llm_for_decision(system_prompt, user_prompt)
print(f"LLM 返回: {result}")
print(f"验证通过: {planner._validate_tool_call(result) if result else 'None'}")
print()

# 4. 对比规则引擎
print("=== 4. 对比规则引擎 ===")
rule_planner = LLMPlannerAgent(use_llm=False)
rule_action = rule_planner.decide_next_action(state)
print(f"规则引擎 tool_name: {rule_action.get('tool_name')}")
print(f"规则引擎 planner_type: {rule_action.get('planner_type')}")
print()

# 结论
print("=" * 50)
if action.get("planner_type") == "llm":
    print("✅ LLM Planner 真正在工作！大模型参与了工具选择决策。")
else:
    print("❌ LLM Planner 没有工作！所有决策都是规则引擎兜底。")
    print(f"   planner_type = '{action.get('planner_type')}'")
    print("   需要排查 _call_llm_for_decision 为什么失败。")
