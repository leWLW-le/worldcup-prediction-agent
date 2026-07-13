"""
Agent Memory 系统

记录历史预测结果、工具调用轨迹、成功/失败模式，
供 LLM Planner 在后续运行中参考，实现"学习"能力。

存储位置：data/agent_memory.json
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MEMORY_FILE = Path("data/agent_memory.json")


class AgentMemory:
    """
    Agent 记忆系统 - 跨运行持久化学习
    
    记录内容：
    1. 历史预测结果（冠军、数据质量、模式）
    2. 工具调用轨迹（成功/失败模式）
    3. 工具可靠性评分
    4. 常见失败模式与应对策略
    """

    def __init__(self, max_history: int = 50):
        self.max_history = max_history
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        """加载记忆数据"""
        if MEMORY_FILE.exists():
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"[AgentMemory] 加载失败: {e}")
        return {
            "prediction_history": [],
            "tool_reliability": {},
            "failure_patterns": [],
            "lessons_learned": [],
        }

    def _save(self):
        """保存记忆数据"""
        try:
            MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[AgentMemory] 保存失败: {e}")

    def record_prediction(self, state) -> None:
        """记录一次预测运行的结果"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "season": getattr(state, "season", 2026),
            "mode": getattr(state, "mode", "unknown"),
            "predicted_champion": getattr(state, "predicted_champion", None),
            "status": getattr(state, "status", "unknown"),
            "data_quality_score": getattr(state, "data_quality_score", None),
            "knockout_count": len(getattr(state, "knockout_predictions", [])),
            "tool_trace_summary": self._summarize_tool_trace(
                getattr(state, "tool_trace", [])
            ),
            "errors": getattr(state, "errors", [])[-3:],
            "warnings": getattr(state, "warnings", [])[-3:],
        }
        self._data["prediction_history"].append(entry)
        # 限制历史记录数量
        if len(self._data["prediction_history"]) > self.max_history:
            self._data["prediction_history"] = self._data["prediction_history"][
                -self.max_history :
            ]
        self._save()

    def record_tool_result(self, tool_name: str, success: bool, error_type: Optional[str] = None) -> None:
        """记录工具调用结果，更新可靠性评分"""
        reliability = self._data["tool_reliability"].get(tool_name, {
            "total": 0, "success": 0, "failures": [], "last_status": None
        })
        reliability["total"] += 1
        if success:
            reliability["success"] += 1
            reliability["last_status"] = "success"
        else:
            reliability["last_status"] = "failed"
            if error_type:
                reliability["failures"].append(error_type)
                # 只保留最近 10 次失败类型
                reliability["failures"] = reliability["failures"][-10:]
        self._data["tool_reliability"][tool_name] = reliability
        self._save()

    def record_lesson(self, lesson: str, context: str = "") -> None:
        """记录经验教训"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "lesson": lesson,
            "context": context,
        }
        self._data["lessons_learned"].append(entry)
        # 只保留最近 20 条
        if len(self._data["lessons_learned"]) > 20:
            self._data["lessons_learned"] = self._data["lessons_learned"][-20:]
        self._save()

    def get_tool_reliability_summary(self) -> Dict[str, Any]:
        """获取工具可靠性摘要（供 LLM Planner 参考）"""
        summary = {}
        for tool_name, data in self._data["tool_reliability"].items():
            total = data["total"]
            success = data["success"]
            rate = success / total if total > 0 else 0.0
            common_failures = []
            if data["failures"]:
                from collections import Counter
                common_failures = [
                    f for f, _ in Counter(data["failures"]).most_common(3)
                ]
            summary[tool_name] = {
                "total_calls": total,
                "success_rate": round(rate, 2),
                "last_status": data["last_status"],
                "common_failures": common_failures,
            }
        return summary

    def get_recent_predictions(self, limit: int = 5) -> List[Dict]:
        """获取最近预测记录"""
        return self._data["prediction_history"][-limit:]

    def get_lessons(self, limit: int = 5) -> List[Dict]:
        """获取经验教训"""
        return self._data["lessons_learned"][-limit:]

    def get_planner_context(self) -> Dict[str, Any]:
        """
        为 LLM Planner 构建记忆上下文。
        包含：工具可靠性、最近预测、经验教训。
        """
        return {
            "tool_reliability": self.get_tool_reliability_summary(),
            "recent_predictions": self.get_recent_predictions(3),
            "lessons_learned": [l["lesson"] for l in self.get_lessons(5)],
        }

    def auto_detect_patterns(self, state) -> None:
        """
        自动检测失败模式并记录教训。
        在每次预测运行结束后调用。
        """
        errors = getattr(state, "errors", [])
        warnings = getattr(state, "warnings", [])
        failed_tools = getattr(state, "failed_tools", [])
        mode = getattr(state, "mode", "unknown")
        champion = getattr(state, "predicted_champion", None)

        # 检测：API 限流导致的问题
        if getattr(state, "api_rate_limited", False):
            self.record_lesson(
                "API 限流时，应跳过 API 工具直接调用 build_team_features（系统有默认球队数据）",
                context=f"mode={mode}",
            )

        # 检测：工具反复失败
        if len(failed_tools) >= 2:
            self.record_lesson(
                f"工具 {failed_tools} 反复失败，应尽早 fallback 到默认数据",
                context=f"mode={mode}",
            )

        # 检测：冠军未确定
        if not champion and getattr(state, "knockout_predictions", []):
            self.record_lesson(
                "有淘汰赛数据但冠军未确定时，应从决赛或最后淘汰赛提取冠军",
                context=f"mode={mode}",
            )

        # 检测：LLM 规划器未完成
        if mode in ("llm_planner_safe", "llm_planner_strict") and getattr(state, "status", "") in ("planner_incomplete", "degraded_completed"):
            self.record_lesson(
                "LLM 规划器未完成时，应确保 fallback 到 workflow 补全缺失步骤",
                context=f"mode={mode}, status={state.status}",
            )

    def _summarize_tool_trace(self, tool_trace: List[Dict]) -> Dict[str, Any]:
        """简化工具调用轨迹"""
        if not tool_trace:
            return {}
        summary = {}
        for t in tool_trace:
            name = t.get("tool_name", "unknown")
            success = t.get("success", False)
            summary[name] = summary.get(name, {"success": 0, "fail": 0})
            if success:
                summary[name]["success"] += 1
            else:
                summary[name]["fail"] += 1
        return summary

    def clear(self):
        """清空记忆"""
        self._data = {
            "prediction_history": [],
            "tool_reliability": {},
            "failure_patterns": [],
            "lessons_learned": [],
        }
        self._save()
