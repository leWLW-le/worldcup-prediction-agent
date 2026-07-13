"""
Agent 全局状态记录

使用 dataclass 记录 Agent 每一步执行状态，
包括数据计划、采集结果、质量报告、预测结果和推理过程。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime


@dataclass
class AgentState:
    """Agent 全局状态"""

    objective: str = ""
    season: int = 2026
    # workflow / llm_planner / llm_planner_safe / llm_planner_strict
    mode: str = "workflow"
    use_llm: bool = False  # 是否使用真实 LLM 进行规划

    # 数据计划与采集
    data_plan: List[str] = field(default_factory=list)
    collected_data: Dict[str, Any] = field(default_factory=dict)
    data_quality_report: Dict[str, Any] = field(default_factory=dict)

    # 球队特征
    team_features: Dict[str, Any] = field(default_factory=dict)

    # 小组赛结果
    group_predictions: List[Dict[str, Any]] = field(default_factory=list)
    group_standings: Dict[str, Any] = field(default_factory=dict)
    qualified_teams: List[str] = field(default_factory=list)

    # 淘汰赛结果
    knockout_predictions: List[Dict[str, Any]] = field(default_factory=list)

    predicted_champion: Optional[str] = None
    predicted_runner_up: Optional[str] = None
    champion_probability: Optional[float] = None
    final_match: Optional[Dict[str, Any]] = None

    # 推理与解释
    reasoning_steps: List[str] = field(default_factory=list)
    final_explanation: Optional[str] = None
    visualization_payload: Dict[str, Any] = field(default_factory=dict)

    # 规划器摘要（llm_planner 模式）
    planner_summary: Dict[str, Any] = field(default_factory=dict)

    # 数据来源状态（验收用）
    data_status: Dict[str, Any] = field(default_factory=dict)

    # 工具调用轨迹（llm_planner 模式）
    tool_trace: List[Dict[str, Any]] = field(default_factory=list)

    # ── 增强特征与 LLM 解释 ──
    champion_explanation: Dict[str, Any] = field(default_factory=dict)
    bracket_payload: Dict[str, Any] = field(default_factory=dict)
    enhanced_features: Dict[str, Any] = field(default_factory=dict)
    top_contenders: List[Dict[str, Any]] = field(default_factory=list)
    representative_path_champion: Optional[Dict[str, Any]] = None  # bracket 路径冠军（Monte Carlo 覆盖时保存）

    # ── 进度跟踪字段（供 LLM Planner 感知当前状态） ──
    has_fixtures: bool = False
    has_real_results: bool = False
    has_teams: bool = False
    has_historical_matches: bool = False
    has_team_features: bool = False
    has_group_predictions: bool = False
    has_knockout_predictions: bool = False
    has_champion_prediction: bool = False
    has_visualization_payload: bool = False
    has_final_explanation: bool = False

    # 数据质量
    data_quality_score: Optional[float] = None
    missing_fields: List[str] = field(default_factory=list)
    can_predict: bool = False

    # API / 工具失败追踪
    api_rate_limited: bool = False
    failed_tools: List[str] = field(default_factory=list)
    completed_tools: List[str] = field(default_factory=list)

    # 错误与状态
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    # pending / running / completed / degraded_completed / failed / planner_incomplete
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.utcnow)

    def add_reasoning(self, step: str):
        """添加推理步骤"""
        self.reasoning_steps.append(step)

    def add_error(self, error: str):
        """添加错误信息"""
        self.errors.append(error)

    def add_warning(self, warning: str):
        """添加警告信息"""
        self.warnings.append(warning)

    def mark_tool_completed(self, tool_name: str):
        """标记工具已完成"""
        if tool_name not in self.completed_tools:
            self.completed_tools.append(tool_name)

    def mark_tool_failed(self, tool_name: str):
        """标记工具已失败"""
        if tool_name not in self.failed_tools:
            self.failed_tools.append(tool_name)

    def update_progress_from_data(self):
        """根据 collected_data 自动更新进度布尔字段"""
        self.has_fixtures = bool(self.collected_data.get("fixtures"))
        self.has_teams = bool(self.collected_data.get("teams"))
        self.has_historical_matches = bool(
            self.collected_data.get("historical")
            or self.collected_data.get("historical_matches")
        )
        self.has_team_features = bool(self.team_features)
        self.has_group_predictions = bool(self.group_predictions)
        self.has_knockout_predictions = bool(self.knockout_predictions)
        self.has_champion_prediction = bool(self.predicted_champion)
        self.has_visualization_payload = bool(self.visualization_payload)
        self.has_final_explanation = bool(self.final_explanation)
        if self.data_quality_report:
            self.data_quality_score = self.data_quality_report.get("score")

    def to_dict(self) -> Dict[str, Any]:
        """转为可序列化的字典"""
        d = {
            "objective": self.objective,
            "season": self.season,
            "mode": self.mode,
            "data_plan": self.data_plan,
            "collected_data": {k: v for k, v in self.collected_data.items() if not k.startswith("_")},
            "data_quality_report": self.data_quality_report,
            "team_features": self.team_features,
            "group_predictions": self.group_predictions,
            "group_standings": self.group_standings,
            "qualified_teams": self.qualified_teams,
            "knockout_predictions": self.knockout_predictions,
            "predicted_champion": self.predicted_champion,
            "champion": self.predicted_champion,  # 顶层别名
            "predicted_runner_up": self.predicted_runner_up,
            "champion_probability": self.champion_probability,
            "final_match": self.final_match,
            "reasoning_steps": self.reasoning_steps,
            "final_explanation": self.final_explanation,
            "visualization_payload": self.visualization_payload,
            "tool_trace": self.tool_trace,
            "planner_summary": self.planner_summary,
            "data_status": self.data_status,
            "champion_explanation": self.champion_explanation,
            "bracket_payload": self.bracket_payload,
            "enhanced_features": self.enhanced_features,
            "top_contenders": self.top_contenders,
            "use_llm": self.use_llm,
            # 进度跟踪字段
            "has_fixtures": self.has_fixtures,
            "has_real_results": self.has_real_results,
            "has_teams": self.has_teams,
            "has_historical_matches": self.has_historical_matches,
            "has_team_features": self.has_team_features,
            "has_group_predictions": self.has_group_predictions,
            "has_knockout_predictions": self.has_knockout_predictions,
            "has_champion_prediction": self.has_champion_prediction,
            "has_visualization_payload": self.has_visualization_payload,
            "has_final_explanation": self.has_final_explanation,
            "data_quality_score": self.data_quality_score,
            "missing_fields": self.missing_fields,
            "can_predict": self.can_predict,
            "api_rate_limited": self.api_rate_limited,
            "failed_tools": self.failed_tools,
            "completed_tools": self.completed_tools,
            # 错误与状态
            "errors": self.errors,
            "warnings": self.warnings,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        return d
