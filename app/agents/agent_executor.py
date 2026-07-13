"""
Agent 工具执行器

负责执行 LLMPlannerAgent 选择的工具，
校验参数、捕获异常、写入 AgentState、记录 tool_trace。
支持同一工具失败次数保护。

所有工具通过 tool_adapters.py 的 adapter 函数调用，
返回统一格式：{success, data, error_type, message, state_updates}
"""

import logging
from typing import Any, Dict

from app.agents.agent_state import AgentState
from app.agents.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentExecutor:
    """工具执行器 - 唯一工具执行入口"""

    def __init__(self, registry: ToolRegistry, max_failures_per_tool: int = 2):
        self.registry = registry
        self.max_failures_per_tool = max_failures_per_tool

    def execute(self, tool_call: Dict[str, Any], state: AgentState) -> Dict[str, Any]:
        """
        执行工具调用并更新状态。

        流程：
        1. 接收 LLM 返回的 tool_name 和 arguments。
        2. 检查 tool_name 是否存在于 ToolRegistry。
        3. 校验 arguments。
        4. 执行对应 tool adapter。
        5. 获取工具返回的 state_updates。
        6. 更新 AgentState。
        7. 记录 tool_trace。

        Args:
            tool_call: {"tool_name": str, "arguments": dict, "reason": str, "planner_type": str}
            state: AgentState

        Returns:
            {"success": bool, "error": str|None, "skipped": bool, "error_type": str|None}
        """
        tool_name = tool_call.get("tool_name", "")
        arguments = tool_call.get("arguments", {})
        reason = tool_call.get("reason", "")
        planner_type = tool_call.get("planner_type", "unknown")
        step_num = len(state.tool_trace) + 1

        # 确保 arguments 是 dict
        if not isinstance(arguments, dict):
            arguments = {}

        # 初始化失败计数
        failed_counts = state.collected_data.setdefault("_failed_tool_counts", {})

        trace_entry = {
            "step": step_num,
            "tool_name": tool_name,
            "arguments": arguments,
            "reason": reason,
            "planner_type": planner_type,
            "success": False,
            "error_type": None,
            "message": None,
            "state_updates": {},
        }

        try:
            # 1. 校验工具存在
            if not self.registry.has_tool(tool_name):
                error_msg = f"Tool '{tool_name}' not in ToolRegistry"
                trace_entry["error_type"] = "tool_not_found"
                trace_entry["message"] = error_msg
                state.tool_trace.append(trace_entry)
                state.add_error(error_msg)
                state.mark_tool_failed(tool_name)
                state.add_reasoning(
                    f"Step {step_num}: [{planner_type}] Tool '{tool_name}' not found"
                )
                return {"success": False, "error": error_msg, "skipped": False, "error_type": "tool_not_found"}

            # 2. 检查失败次数限制
            fail_count = failed_counts.get(tool_name, 0)
            if fail_count >= self.max_failures_per_tool:
                error_msg = f"Tool '{tool_name}' failed {fail_count} times, skipping"
                trace_entry["error_type"] = "max_failures_reached"
                trace_entry["message"] = error_msg
                trace_entry["success"] = False
                state.tool_trace.append(trace_entry)
                state.add_warning(f"Step {step_num}: {error_msg}")
                state.add_reasoning(f"Step {step_num}: [{planner_type}] {error_msg}")
                return {"success": False, "error": error_msg, "skipped": True, "error_type": "max_failures_reached"}

            # 3. 执行工具
            logger.info(
                f"[Executor] Step {step_num}: [{planner_type}] {tool_name}({arguments})"
            )
            result = self.registry.call(tool_name, state=state, **arguments)

            # 提取统一返回字段
            success = result.get("success", False)
            data = result.get("data")
            error_type = result.get("error_type")
            message = result.get("message", "")
            state_updates = result.get("state_updates", {})

            trace_entry["message"] = message
            trace_entry["state_updates"] = state_updates

            if not success:
                trace_entry["error_type"] = error_type or "unknown_error"
                state.tool_trace.append(trace_entry)
                state.add_warning(f"Step {step_num}: {tool_name} failed - {message}")
                state.add_reasoning(
                    f"Step {step_num}: [{planner_type}] {tool_name} failed: {message}"
                )
                # 增加失败计数
                failed_counts[tool_name] = fail_count + 1
                state.mark_tool_failed(tool_name)

                # 如果 rate_limited，标记 state
                if error_type == "rate_limited":
                    state.api_rate_limited = True

                return {"success": False, "error": message, "skipped": False, "error_type": error_type}

            # 4. 应用 state_updates 到 AgentState
            self._apply_state_updates(tool_name, data, state_updates, state)

            # 5. 记录成功
            trace_entry["success"] = True
            state.tool_trace.append(trace_entry)
            state.mark_tool_completed(tool_name)
            state.add_reasoning(
                f"Step {step_num}: [{planner_type}] {tool_name} success - {message}"
            )

            return {"success": True, "error": None, "skipped": False, "error_type": None}

        except Exception as e:
            logger.error(
                f"[Executor] Step {step_num}: {tool_name} exception: {e}",
                exc_info=True,
            )
            trace_entry["error_type"] = "exception"
            trace_entry["message"] = str(e)
            state.tool_trace.append(trace_entry)
            state.add_error(f"Step {step_num}: {tool_name} exception - {str(e)}")
            # 增加失败计数
            failed_counts[tool_name] = failed_counts.get(tool_name, 0) + 1
            state.mark_tool_failed(tool_name)
            return {"success": False, "error": str(e), "skipped": False, "error_type": "exception"}

    def _apply_state_updates(
        self, tool_name: str, data: Any, state_updates: Dict, state: AgentState
    ):
        """将工具返回的 state_updates 应用到 AgentState"""

        # 通用字段直接设置
        simple_fields = [
            "has_fixtures", "has_real_results", "has_teams",
            "has_historical_matches", "has_team_features",
            "has_group_predictions", "has_knockout_predictions",
            "has_champion_prediction", "has_visualization_payload",
            "has_final_explanation", "data_quality_score",
            "can_predict", "api_rate_limited",
        ]
        for field_name in simple_fields:
            if field_name in state_updates:
                setattr(state, field_name, state_updates[field_name])

        # 列表字段追加
        list_fields = ["missing_fields", "failed_tools", "completed_tools"]
        for field_name in list_fields:
            if field_name in state_updates:
                val = state_updates[field_name]
                current = getattr(state, field_name, [])
                if isinstance(val, list):
                    for item in val:
                        if item not in current:
                            current.append(item)

        # collected_data 字段
        if "data_quality_report" in state_updates:
            state.data_quality_report = state_updates["data_quality_report"]

        # team_features
        if "team_features" in state_updates:
            state.team_features = state_updates["team_features"]

        # group_predictions
        if "group_predictions" in state_updates:
            state.group_predictions = state_updates["group_predictions"]
        if "group_standings" in state_updates:
            state.group_standings = state_updates["group_standings"]
        if "qualified_teams" in state_updates:
            state.qualified_teams = state_updates["qualified_teams"]

        # knockout
        if "knockout_predictions" in state_updates:
            state.knockout_predictions = state_updates["knockout_predictions"]
        if "predicted_champion" in state_updates:
            state.predicted_champion = state_updates["predicted_champion"]
        if "predicted_runner_up" in state_updates:
            state.predicted_runner_up = state_updates["predicted_runner_up"]
        if "final_match" in state_updates:
            state.final_match = state_updates["final_match"]

        # visualization
        if "visualization_payload" in state_updates:
            state.visualization_payload = state_updates["visualization_payload"]

        # explanation
        if "final_explanation" in state_updates:
            state.final_explanation = state_updates["final_explanation"]
        if "bracket_payload" in state_updates:
            state.bracket_payload = state_updates["bracket_payload"]

        # 内部中间数据（以 _ 开头存入 collected_data）
        for key, val in state_updates.items():
            if key.startswith("_"):
                state.collected_data[key] = val

        # 同时把 data 存入 collected_data（供 workflow fallback 使用）
        if data is not None:
            if tool_name == "get_cached_fixtures" or tool_name == "refresh_real_fixtures":
                if isinstance(data, dict):
                    state.collected_data["fixtures"] = data.get("fixtures", [])
            elif tool_name == "get_worldcup_teams":
                if isinstance(data, dict):
                    state.collected_data["teams"] = data.get("teams", [])
            elif tool_name == "load_historical_matches":
                if isinstance(data, dict):
                    state.collected_data["historical"] = data.get("historical_matches")
