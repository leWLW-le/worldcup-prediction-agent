"""
LLM Planner Agent（增强版）

让 LLM 根据 AgentState 摘要自主决定下一步调用哪个工具。
LLM 只能选择工具，不能直接决定冠军。
LLM 失败时使用规则引擎兜底。

增强特性：
- Chain-of-Thought 推理：LLM 先分析状态再决策
- 反思机制：定期评估当前策略是否有效
- 记忆集成：参考历史工具可靠性和经验教训

支持 use_llm=False 纯规则模式，用于测试和对照。
"""

import json
import logging
from typing import Any, Dict, Optional

from app.agents.agent_state import AgentState
from app.agents.tool_schemas import TOOL_SCHEMAS

logger = logging.getLogger(__name__)

# 所有合法工具名
VALID_TOOL_NAMES = {s["name"] for s in TOOL_SCHEMAS} | {"finish"}


class LLMPlannerAgent:
    """LLM 决策 Agent - 根据状态决定下一步工具调用（增强版）"""

    def __init__(self, use_llm: bool = True, timeout_seconds: int = 20, enable_reflection: bool = True):
        """
        Args:
            use_llm: 是否使用真实 LLM。False 时直接走规则引擎。
            timeout_seconds: LLM 调用超时秒数
            enable_reflection: 是否启用反思机制
        """
        self.use_llm = use_llm
        self.timeout_seconds = timeout_seconds
        self.enable_reflection = enable_reflection
        self._explainer = None
        self._memory = None
        self._step_count = 0
        self._reflection_interval = 4  # 每 N 步反思一次
        self._last_reflection_step = 0

    def _get_llm(self):
        """懒加载 LLM"""
        if not self.use_llm:
            return None
        if self._explainer is None:
            try:
                from app.services.llm_explainer import MatchExplainerAgent
                from app.core.config import get_settings
                settings = get_settings()
                api_key = settings.OPENAI_API_KEY or "sk-placeholder-key"
                self._explainer = MatchExplainerAgent(
                    model_name=settings.OPENAI_MODEL,
                    api_key=api_key,
                    use_local_model=settings.USE_LOCAL_MODEL,
                )
            except Exception as e:
                logger.warning(f"[LLMPlanner] LLM init failed: {e}")
                self._explainer = None
        return self._explainer

    def _get_memory(self):
        """懒加载 Memory"""
        if self._memory is None:
            try:
                from app.agents.agent_memory import AgentMemory
                self._memory = AgentMemory()
            except Exception as e:
                logger.warning(f"[LLMPlanner] Memory init failed: {e}")
                self._memory = None
        return self._memory

    def _build_state_summary(self, state: AgentState) -> Dict[str, Any]:
        """构建 AgentState 摘要，告诉大模型当前进度和缺什么"""
        summary = {
            "objective": state.objective,
            "season": state.season,
            "当前已有": {
                "fixtures": state.has_fixtures,
                "teams": state.has_teams,
                "historical_matches": state.has_historical_matches,
                "team_features": state.has_team_features,
                "group_predictions": state.has_group_predictions,
                "knockout_predictions": state.has_knockout_predictions,
                "champion_prediction": state.has_champion_prediction,
                "visualization_payload": state.has_visualization_payload,
                "final_explanation": state.has_final_explanation,
            },
            "data_quality_score": state.data_quality_score,
            "can_predict": state.can_predict,
            "missing_fields": state.missing_fields,
            "api_rate_limited": state.api_rate_limited,
            "failed_tools": state.failed_tools,
            "completed_tools": state.completed_tools,
            "warnings": state.warnings[-3:],
            "current_step": self._step_count,
        }
        # 附加记忆上下文
        memory = self._get_memory()
        if memory:
            summary["memory_context"] = memory.get_planner_context()
        return summary

    def _build_system_prompt(self, state: AgentState) -> str:
        """构建系统提示 - 中文，包含完整工具列表和决策规则（CoT 增强版）"""
        tools_desc = []
        for schema in TOOL_SCHEMAS:
            tools_desc.append(f"- {schema['name']}: {schema['description']}")
        tools_str = "\n".join(tools_desc)

        failed_tools = state.failed_tools if state else []
        failed_str = "、".join(failed_tools) if failed_tools else "无"

        # 记忆上下文
        memory_context = ""
        memory = self._get_memory()
        if memory:
            lessons = memory.get_lessons(3)
            if lessons:
                lessons_str = "\n".join(f"  - {l['lesson']}" for l in lessons)
                memory_context = f"\n\n历史经验教训（从过往运行中学习）：\n{lessons_str}"

            tool_rel = memory.get_tool_reliability_summary()
            if tool_rel:
                rel_str = "\n".join(
                    f"  - {name}: 成功率{d['success_rate']:.0%}, 最近状态={d['last_status']}"
                    for name, d in tool_rel.items()
                )
                memory_context += f"\n\n工具可靠性历史：\n{rel_str}"

        return f"""你是 2026 世界杯冠军预测 Agent 的规划器。
你的任务不是直接猜冠军，而是根据当前 AgentState 选择合适工具完成预测流程。

可用工具：
{tools_str}

决策规则（按优先级）：
1. 如果缺赛程（has_fixtures=false），优先调用 get_cached_fixtures。
2. 如果 get_cached_fixtures 返回失败（如 API 限流或空数据），不要重复调用它，直接继续下一步。
3. 如果缺球队（has_teams=false），调用 get_worldcup_teams。
4. 如果 get_worldcup_teams 返回失败，不要重复调用，直接继续下一步。
5. 如果缺历史比赛（has_historical_matches=false），调用 load_historical_matches。
6. 如果数据质量不清楚（can_predict 为 null），调用 check_data_quality。
7. 如果已有基础数据（fixtures 或 teams 或 historical_matches 任一为 true），调用 build_team_features。
   注意：即使 API 数据不可用，系统也有默认球队数据，build_team_features 可以正常工作。
8. 如果已有特征（has_team_features=true），调用 predict_group_stage。
9. 如果已有小组赛结果（has_group_predictions=true），调用 predict_knockout_bracket。
10. 如果已有淘汰赛结果（has_knockout_predictions=true），调用 predict_champion。
11. 如果已有冠军预测（has_champion_prediction=true），调用 build_visualization_payload。
12. 如果已有可视化数据（has_visualization_payload=true），调用 generate_final_explanation。
13. 如果所有步骤完成，返回 finish。
14. 每一步只能选择一个工具。
15. 不允许直接编造真实比分或赛程。
16. 如果工具失败，不要重复调用同一个工具，尝试其他工具或继续下一步。
17. 如果 API 限流（api_rate_limited=true），不要调用任何 API 相关工具，直接跳到 build_team_features。
18. 重要：即使 API 数据不可用，系统也有默认 48 支球队数据，build_team_features 可以正常工作，不要卡在数据获取步骤。

已经失败的工具（不要再次调用）：
{failed_str}
{memory_context}

返回严格 JSON（必须包含 thought 字段进行推理）：
{{"thought": "你的分析过程...", "tool_name": "工具名", "arguments": {{}}, "reason": "选择理由"}}

如果预测流程已完成：
{{"thought": "所有步骤已完成", "tool_name": "finish", "arguments": {{}}, "reason": "预测流程已完成"}}
"""

    def _build_user_prompt(self, state: AgentState) -> str:
        """构建用户提示"""
        summary = self._build_state_summary(state)
        return (
            f"当前 Agent 状态摘要：\n"
            f"{json.dumps(summary, indent=2, ensure_ascii=False)}\n\n"
            f"请选择下一步要调用的工具。"
        )

    def rule_based_decide_next_action(self, state: AgentState) -> Dict[str, Any]:
        """规则引擎 - 按固定优先级顺序选择工具（使用新工具名）"""
        failed_counts = state.collected_data.get("_failed_tool_counts", {})
        api_limited = state.api_rate_limited

        def _exceeded(tool_name):
            """同一工具失败 >= 2 次则禁止再调用"""
            return failed_counts.get(tool_name, 0) >= 2

        if not state.has_fixtures and not state.collected_data.get("fixtures") and not _exceeded("get_cached_fixtures"):
            return {
                "tool_name": "get_cached_fixtures",
                "arguments": {"season": state.season},
                "reason": "[rule] 需要赛程数据",
                "planner_type": "rule_fallback",
            }
        if not state.has_teams and not state.collected_data.get("teams") and not _exceeded("get_worldcup_teams"):
            return {
                "tool_name": "get_worldcup_teams",
                "arguments": {"season": state.season},
                "reason": "[rule] 需要球队数据",
                "planner_type": "rule_fallback",
            }
        if not state.has_historical_matches and not _exceeded("load_historical_matches"):
            return {
                "tool_name": "load_historical_matches",
                "arguments": {"start_year": 2018},
                "reason": "[rule] 需要历史比赛数据",
                "planner_type": "rule_fallback",
            }
        if not state.data_quality_report and not state.can_predict and not _exceeded("check_data_quality"):
            return {
                "tool_name": "check_data_quality",
                "arguments": {},
                "reason": "[rule] 需要数据质量检查",
                "planner_type": "rule_fallback",
            }
        if not state.has_team_features and not _exceeded("build_team_features"):
            return {
                "tool_name": "build_team_features",
                "arguments": {},
                "reason": "[rule] 需要构建球队特征（即使 API 数据不可用，系统有默认球队数据）",
                "planner_type": "rule_fallback",
            }
        if not state.has_group_predictions and not _exceeded("predict_group_stage"):
            return {
                "tool_name": "predict_group_stage",
                "arguments": {},
                "reason": "[rule] 需要小组赛预测",
                "planner_type": "rule_fallback",
            }
        if not state.has_knockout_predictions and not _exceeded("predict_knockout_bracket"):
            return {
                "tool_name": "predict_knockout_bracket",
                "arguments": {},
                "reason": "[rule] 需要淘汰赛推演",
                "planner_type": "rule_fallback",
            }
        if not state.has_champion_prediction and not _exceeded("predict_champion"):
            return {
                "tool_name": "predict_champion",
                "arguments": {},
                "reason": "[rule] 需要确定冠军",
                "planner_type": "rule_fallback",
            }
        if not state.has_visualization_payload and not _exceeded("build_visualization_payload"):
            return {
                "tool_name": "build_visualization_payload",
                "arguments": {},
                "reason": "[rule] 需要构建可视化数据",
                "planner_type": "rule_fallback",
            }
        if not state.has_final_explanation and not _exceeded("generate_final_explanation"):
            return {
                "tool_name": "generate_final_explanation",
                "arguments": {},
                "reason": "[rule] 需要生成冠军解释",
                "planner_type": "rule_fallback",
            }
        return {
            "tool_name": "finish",
            "arguments": {},
            "reason": "[rule] 预测流程完成或所有工具已用尽",
            "planner_type": "rule_fallback",
        }

    def decide_next_action(self, state: AgentState) -> Dict[str, Any]:
        """
        决定下一步工具调用。

        如果 use_llm=False，直接走规则引擎。
        如果 LLM 调用失败/超时/返回非法工具，自动 fallback 到规则引擎。
        每 N 步触发一次反思，评估当前策略是否有效。

        Returns:
            {"tool_name": str, "arguments": dict, "reason": str, "planner_type": str}
        """
        self._step_count += 1

        # 定期反思：评估当前策略
        if (
            self.enable_reflection
            and self._step_count - self._last_reflection_step >= self._reflection_interval
        ):
            reflection = self._reflect_on_progress(state)
            if reflection:
                logger.info(f"[LLMPlanner] Reflection at step {self._step_count}: {reflection}")
                state.add_reasoning(f"[反思@step{self._step_count}] {reflection}")
            self._last_reflection_step = self._step_count

        # 如果禁用 LLM，直接走规则
        if not self.use_llm:
            return self.rule_based_decide_next_action(state)

        # 尝试 LLM
        llm = self._get_llm()
        if llm:
            try:
                system_prompt = self._build_system_prompt(state)
                user_prompt = self._build_user_prompt(state)
                result = self._call_llm_for_decision(system_prompt, user_prompt)
                if result and self._validate_tool_call(result, state):
                    result["planner_type"] = "llm"
                    return result
                else:
                    logger.warning("[LLMPlanner] LLM returned invalid tool call, using rule fallback")
            except Exception as e:
                logger.warning(f"[LLMPlanner] LLM decision failed: {e}, using rule fallback")

        # LLM 不可用或失败，使用规则兜底
        fallback = self.rule_based_decide_next_action(state)
        return fallback

    def _reflect_on_progress(self, state: AgentState) -> Optional[str]:
        """
        反思当前进度，检测是否需要调整策略。
        
        Returns:
            反思结论字符串，或 None 表示一切正常
        """
        issues = []

        # 检测 1: 是否卡在某个步骤太久
        if self._step_count >= 6 and not state.has_team_features:
            issues.append("已执行多步但尚未构建球队特征，应直接调用 build_team_features（系统有默认数据）")

        # 检测 2: 是否有工具反复失败
        failed_counts = state.collected_data.get("_failed_tool_counts", {})
        for tool, count in failed_counts.items():
            if count >= 2:
                issues.append(f"工具 {tool} 已失败 {count} 次，应跳过并继续下一步")

        # 检测 3: API 限流但仍尝试 API 工具
        if state.api_rate_limited and self._step_count >= 3:
            completed = state.completed_tools
            if "build_team_features" not in completed:
                issues.append("API 已限流，应跳过所有 API 工具，直接调用 build_team_features")

        # 检测 4: 有淘汰赛数据但冠军未确定
        if state.has_knockout_predictions and not state.has_champion_prediction:
            issues.append("已有淘汰赛数据但未确定冠军，应调用 predict_champion 或从决赛提取")

        if issues:
            return "; ".join(issues)
        return None

    def _call_llm_for_decision(self, system_prompt: str, user_prompt: str) -> Optional[Dict]:
        """调用 LLM 获取决策（带超时）"""
        try:
            from app.core.config import get_settings
            settings = get_settings()

            try:
                from zhipuai import ZhipuAI
                client = ZhipuAI(api_key=settings.OPENAI_API_KEY)
                response = client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.1,
                    max_tokens=300,
                    timeout=self.timeout_seconds,
                )
                content = response.choices[0].message.content.strip()
                return self._extract_json(content)
            except ImportError:
                import urllib.request
                api_data = json.dumps({
                    "model": settings.OPENAI_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 300,
                }).encode("utf-8")

                base_url = settings.OPENAI_BASE_URL.rstrip("/")
                req = urllib.request.Request(
                    f"{base_url}/chat/completions",
                    data=api_data,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    },
                )
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    content = resp_data["choices"][0]["message"]["content"].strip()
                    return self._extract_json(content)
        except Exception as e:
            logger.warning(f"[LLMPlanner] LLM API call failed: {e}")
        return None

    def _extract_json(self, content: str) -> Optional[Dict]:
        """从 LLM 响应中提取 JSON（支持 thought 字段）"""
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            parsed = json.loads(content)
            # 如果有 thought 字段，记录推理过程
            if "thought" in parsed:
                logger.info(f"[LLMPlanner] CoT thought: {parsed['thought']}")
            return parsed
        except (json.JSONDecodeError, IndexError):
            return None

    def _validate_tool_call(self, tool_call: Dict, state: AgentState = None) -> bool:
        """验证工具调用是否合法，并检查是否调用了失败工具"""
        if not isinstance(tool_call, dict):
            return False
        tool_name = tool_call.get("tool_name", "")
        if tool_name not in VALID_TOOL_NAMES:
            return False
        # 检查是否调用了失败工具（finish 除外）
        if state and tool_name != "finish":
            failed_counts = state.collected_data.get("_failed_tool_counts", {})
            if failed_counts.get(tool_name, 0) >= 2:
                logger.warning(f"[LLMPlanner] LLM tried to call failed tool '{tool_name}', rejecting")
                return False
        return True
