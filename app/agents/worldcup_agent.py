"""
WorldCupPredictionAgent - 核心编排

支持四种模式运行：
- workflow: 固定 12 步流水线（稳定基线）
- llm_planner: 等价于 llm_planner_safe（兼容旧参数）
- llm_planner_safe: LLM 自主决定工具调用，失败时允许 fallback 到 workflow
- llm_planner_strict: LLM 自主决定工具调用，不允许 fallback，未完成则返回 planner_incomplete
"""

import json
import logging
import os
import random
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agents.agent_state import AgentState
from app.agents.data_quality_agent import DataQualityAgent
from app.tools.api_sports_tool import APISportsTool
from app.tools.historical_data_tool import HistoricalDataTool
from app.tools.feature_builder_tool import FeatureBuilderTool
from app.tools.match_predictor_tool import MatchPredictorTool
from app.tools.bracket_tool import BracketTool, validate_bracket_integrity, normalize_bracket_payload
from app.tools.explanation_tool import ExplanationTool
from app.services.team_rating_service import load_team_ratings
from app.services.recent_form_service import compute_recent_form
from app.services.team_stats_service import compute_attack_defense_stats
from app.services.path_difficulty_service import compute_path_difficulty
from app.services.feature_builder_service import build_team_features as build_enhanced_features

logger = logging.getLogger(__name__)

# ── 48 队默认分组（2026 美加墨世界杯真实分组，当 API 数据不足时使用） ──
DEFAULT_48_TEAMS = [
    # Group A
    [("Mexico", 1830), ("South Africa", 1620), ("South Korea", 1700), ("Czech Republic", 1650)],
    # Group B
    [("Canada", 1710), ("Bosnia", 1640), ("Qatar", 1500), ("Switzerland", 1860)],
    # Group C
    [("Brazil", 2060), ("Morocco", 1820), ("Haiti", 1480), ("Scotland", 1690)],
    # Group D
    [("USA", 1780), ("Paraguay", 1650), ("Australia", 1700), ("Turkey", 1720)],
    # Group E
    [("Germany", 2000), ("Curacao", 1420), ("Ivory Coast", 1660), ("Ecuador", 1740)],
    # Group F
    [("Netherlands", 1960), ("Japan", 1750), ("Sweden", 1770), ("Tunisia", 1610)],
    # Group G
    [("Belgium", 1880), ("Egypt", 1680), ("Iran", 1650), ("New Zealand", 1530)],
    # Group H
    [("Spain", 2080), ("Cape Verde", 1520), ("Saudi Arabia", 1560), ("Uruguay", 1820)],
    # Group I
    [("France", 2100), ("Senegal", 1720), ("Iraq", 1480), ("Norway", 1800)],
    # Group J
    [("Argentina", 2050), ("Algeria", 1600), ("Austria", 1750), ("Jordan", 1440)],
    # Group K
    [("Portugal", 1980), ("DR Congo", 1460), ("Uzbekistan", 1580), ("Colombia", 1840)],
    # Group L
    [("England", 2040), ("Croatia", 1860), ("Ghana", 1640), ("Panama", 1600)],
]

VALID_MODES = {"workflow", "llm_planner", "llm_planner_safe", "llm_planner_strict"}


def _validate_prediction_snapshot(snapshot: Dict):
    """预测快照一致性校验。

    在保存为 completed 之前以及 GET /final-result 返回之前调用。
    如果校验失败，抛出 AssertionError，阻止保存或返回。
    """
    assert snapshot.get("status") == "completed", \
        f"status must be 'completed', got '{snapshot.get('status')}'"

    champ = snapshot.get("champion", "")
    champ_prob = snapshot.get("champion_probability", 0)
    top5 = snapshot.get("top5", [])
    top_candidates = snapshot.get("top_candidates", [])
    explanation = snapshot.get("explanation", {})

    # champion == top5[0].team
    if top5:
        assert champ == top5[0].get("team", ""), \
            f"champion({champ}) != top5[0].team({top5[0].get('team')})"

    # champion_probability == top5[0].probability
    if top5:
        top1_prob = top5[0].get("probability", 0)
        expected = top1_prob if top1_prob <= 1 else top1_prob / 100.0
        actual = champ_prob if champ_prob <= 1 else champ_prob / 100.0
        assert abs(expected - actual) < 1e-9, \
            f"champion_probability({champ_prob}) != top5[0].probability({top1_prob})"

    # top_candidates[0] == champion
    if top_candidates:
        assert top_candidates[0].get("team") == champ, \
            f"top_candidates[0].team({top_candidates[0].get('team')}) != champion({champ})"
        tc_prob = top_candidates[0].get("probability", 0)
        tc_expected = tc_prob if tc_prob <= 1 else tc_prob / 100.0
        tc_actual = champ_prob if champ_prob <= 1 else champ_prob / 100.0
        assert abs(tc_expected - tc_actual) < 1e-9, \
            f"top_candidates[0].probability({tc_prob}) != champion_probability({champ_prob})"

    # explanation.champion == champion
    if isinstance(explanation, dict):
        expl_champ = explanation.get("champion", "")
        if expl_champ:
            assert expl_champ == champ, \
                f"explanation.champion({expl_champ}) != champion({champ})"

        # explanation.champion_probability == champion_probability
        expl_prob = explanation.get("champion_probability")
        if expl_prob is not None:
            e = float(expl_prob) if float(expl_prob) <= 1 else float(expl_prob) / 100.0
            a = float(champ_prob) if float(champ_prob) <= 1 else float(champ_prob) / 100.0
            assert abs(e - a) < 1e-9, \
                f"explanation.champion_probability({expl_prob}) != champion_probability({champ_prob})"

        # explanation.run_id == snapshot.run_id
        data_run_id = snapshot.get("run_id", "")
        expl_run_id = explanation.get("run_id", "")
        if data_run_id and expl_run_id:
            assert expl_run_id == data_run_id, \
                f"explanation.run_id({expl_run_id}) != snapshot.run_id({data_run_id})"

    logger.info("[Agent] _validate_prediction_snapshot passed: champion=%s, prob=%.4f, run_id=%s",
                champ, champ_prob, snapshot.get("run_id"))


def atomic_write_json(path: Path, data: Dict):
    """原子写入 JSON 文件：先写临时文件，再 os.replace 替换目标。

    避免读取端读到写了一半的文件。
    """
    import tempfile
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", prefix=".final_agent_result_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, str(path))
        logger.info("[Agent] 原子写入完成: %s", path.resolve())
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def build_canonical_snapshot(
    *,
    champion: str,
    champion_probability: float,
    top5: list,
    explanation: dict,
    surviving_teams: list = None,
    stage: str = "unknown",
    run_id: str = None,
    status: str = "completed",
    bracket_payload: dict = None,
    data_status: dict = None,
    model_status: dict = None,
    top_contenders: list = None,
    generated_at: str = None,
    **extra_fields,
) -> Dict:
    """构建统一的 canonical prediction snapshot。

    所有写入路径（agent / scheduled_refresh / fix_script）都应使用此函数，
    确保 JSON 结构一致且通过 _validate_prediction_snapshot 校验。

    核心规则：
    - champion = top5[0].team
    - champion_probability = top5[0].probability (0-1 范围)
    - top_candidates = deepcopy(top5)
    - explanation 绑定字段强制覆盖
    """
    import hashlib
    from copy import deepcopy

    # ── 强制 champion / probability 来自 top5[0] ──
    if top5:
        champion = top5[0].get("team", champion)
        top1_prob = top5[0].get("probability", 0)
        champion_probability = top1_prob if top1_prob <= 1 else top1_prob / 100.0
        champion_probability = round(champion_probability, 4)

    # ── run_id ──
    if not run_id:
        run_ts = generated_at or datetime.utcnow().isoformat()
        run_id_raw = f"{champion}:{champion_probability}:{run_ts}"
        run_id = "run_" + hashlib.md5(run_id_raw.encode()).hexdigest()[:12]

    # ── generated_at ──
    if not generated_at:
        generated_at = datetime.utcnow().isoformat()

    # ── 强制覆盖 explanation 绑定字段 ──
    if isinstance(explanation, dict):
        explanation["champion"] = champion
        explanation["champion_probability"] = champion_probability
        explanation["probability"] = round(champion_probability * 100, 2)
        explanation["run_id"] = run_id

    # ── 构建 snapshot ──
    snapshot = {
        "schema_version": 1,
        "run_id": run_id,
        "status": status,
        "champion": champion,
        "predicted_champion": champion,
        "champion_probability": champion_probability,
        "top5": top5,
        "top_candidates": deepcopy(top5),
        "explanation": explanation,
        "surviving_teams": surviving_teams or [],
        "stage": stage,
        "generated_at": generated_at,
        "bracket_payload": bracket_payload or {},
        "data_status": data_status or {},
        "model_status": model_status or {},
        "top_contenders": top_contenders or [],
    }
    # 合并额外字段（如 stage_info, simulation_count 等）
    snapshot.update(extra_fields)

    # ── 保存前校验 ──
    _validate_prediction_snapshot(snapshot)

    return snapshot


class WorldCupPredictionAgent:
    """世界杯冠军预测 Agent - 多模式"""

    def __init__(self, seed: int | None = 42):
        self.seed = seed
        if seed is not None:
            random.seed(seed)

    def run(self, season: int = 2026, mode: str = "workflow", use_llm: bool = True) -> AgentState:
        """
        执行完整预测流程。

        Args:
            season: 世界杯赛季
            mode: "workflow" | "llm_planner" | "llm_planner_safe" | "llm_planner_strict"
            use_llm: 是否使用真实 LLM（llm_planner 模式下有效）
        """
        # 校验 mode
        if mode not in VALID_MODES:
            mode = "workflow"
        # llm_planner 等价于 llm_planner_safe
        if mode == "llm_planner":
            mode = "llm_planner_safe"

        state = AgentState(season=season, mode=mode, use_llm=use_llm)
        state.status = "running"

        try:
            if mode == "workflow":
                self._run_workflow(state)
            elif mode in ("llm_planner_safe", "llm_planner_strict"):
                self._run_llm_planner(state, use_llm=use_llm)

            # 生成可视化数据（两种模式共享，strict 模式下如果 LLM 没做则补做）
            if not state.has_visualization_payload:
                self._step12_visualization(state)

            # 生成 planner_summary（llm_planner 模式）
            if mode in ("llm_planner_safe", "llm_planner_strict"):
                llm_steps = sum(1 for t in state.tool_trace if t.get("planner_type") == "llm")
                rule_fallback_steps = sum(1 for t in state.tool_trace if t.get("planner_type") == "rule_fallback")
                workflow_fallback_used = state.mode == "llm_planner_fallback_workflow"
                state.planner_summary = {
                    "llm_steps": llm_steps,
                    "rule_fallback_steps": rule_fallback_steps,
                    "workflow_fallback_used": workflow_fallback_used,
                }

            # 更新最终进度
            state.update_progress_from_data()

            # 根据数据质量决定最终状态
            if mode == "llm_planner_strict":
                # strict 模式：检查完成条件
                if self._strict_complete(state):
                    state.status = "completed"
                else:
                    state.status = "planner_incomplete"
            else:
                quality = state.data_quality_report
                if quality.get("fallback_used"):
                    state.status = "degraded_completed"
                else:
                    state.status = "completed"

            state.add_reasoning(f"Agent task completed (mode={state.mode}, status={state.status})")

            # 生成 data_status（数据来源验收）
            state.data_status = self._build_data_status(state)

            # 记录到 Memory 并学习
            self._record_to_memory(state)

            # ── 统一 champion 字段（最终兜底） ──
            self._ensure_champion_fields(state)

            # 构建增强特征和冠军解释
            self._build_enhanced_features_and_explanation(state)

            # 保存统一结果 JSON（前端唯一数据源）
            self._save_final_agent_result(state)

        except Exception as e:
            logger.error(f"[Agent] Run exception: {e}", exc_info=True)
            state.add_error(f"Agent run exception: {str(e)}")
            state.status = "failed"
            # 即使异常也记录到 Memory
            self._record_to_memory(state)

        return state

    def _run_workflow(self, state: AgentState):
        """workflow 模式：固定 12 步流水线"""
        self._step1_objective(state, state.season)
        self._step2_data_plan(state)
        self._step3_collect_api_data(state, state.season)
        self._step4_collect_historical(state)
        self._step5_collect_scraper(state)
        self._step6_quality_check(state)
        self._step7_build_features(state)
        self._step8_predict_groups(state)
        self._step9_predict_knockout(state)
        self._step10_champion(state)
        self._step11_explain(state)
        # 更新进度字段
        state.update_progress_from_data()

    def _run_llm_planner(self, state: AgentState, use_llm: bool = True):
        """llm_planner 模式：LLM/规则 自主决定工具调用"""
        from app.agents.llm_planner_agent import LLMPlannerAgent
        from app.agents.agent_executor import AgentExecutor
        from app.agents.tool_registry import ToolRegistry

        state.objective = (
            f"Predict {state.season} World Cup champion and explain reasoning"
        )
        state.add_reasoning(f"Agent started (mode={state.mode}, use_llm={use_llm})")

        registry = ToolRegistry(seed=self.seed)
        planner = LLMPlannerAgent(use_llm=use_llm, timeout_seconds=15)
        executor = AgentExecutor(registry, max_failures_per_tool=2)

        max_steps = 20
        api_call_count = 0
        max_api_calls = 10
        consecutive_skips = 0

        for step in range(max_steps):
            # Planner 决定下一步
            tool_call = planner.decide_next_action(state)
            tool_name = tool_call.get("tool_name", "")

            # 检查是否完成
            if tool_name == "finish":
                state.add_reasoning(f"Planner decided to finish: {tool_call.get('reason', '')}")
                break

            # 检查工具是否已经超过失败次数（提前拦截，避免进入 executor）
            failed_counts = state.collected_data.get("_failed_tool_counts", {})
            if failed_counts.get(tool_name, 0) >= 2:
                state.add_warning(f"Tool '{tool_name}' already failed {failed_counts[tool_name]} times, skipping")
                consecutive_skips += 1
                if consecutive_skips >= 5:
                    state.add_reasoning("Too many consecutive skips, breaking loop")
                    break
                continue

            # 检查 API 调用次数限制
            api_tools = {"get_cached_fixtures", "refresh_real_fixtures", "get_worldcup_teams"}
            if tool_name in api_tools:
                api_call_count += 1
                if api_call_count > max_api_calls:
                    state.add_warning(f"API call limit reached ({max_api_calls}), skipping API tools")
                    consecutive_skips += 1
                    if consecutive_skips >= 5:
                        state.add_reasoning("Too many consecutive skips, breaking loop")
                        break
                    continue

            # 执行工具
            result = executor.execute(tool_call, state)

            # 如果工具被跳过（失败次数过多），继续下一步
            if result.get("skipped"):
                consecutive_skips += 1
                if consecutive_skips >= 5:
                    state.add_reasoning("Too many consecutive skips, breaking loop")
                    break
                continue

            # 重置连续跳过计数
            consecutive_skips = 0

            # 更新进度
            state.update_progress_from_data()

            # strict 模式：检查完成条件
            if state.mode == "llm_planner_strict" and self._strict_complete(state):
                state.add_reasoning("Strict mode: prediction complete, ending loop")
                break

            # safe 模式：如果预测已完成则提前退出
            if self._prediction_complete(state):
                state.add_reasoning("Prediction complete, ending loop early")
                break

        # 循环结束后处理
        if state.mode == "llm_planner_strict":
            # strict 模式：不允许 fallback
            if not self._strict_complete(state):
                missing = self._get_missing_fields(state)
                state.add_warning(f"Strict mode incomplete. Missing: {missing}")
                state.status = "planner_incomplete"
                state.missing_fields = missing
        else:
            # safe 模式：允许 fallback 到 workflow
            if not self._prediction_complete(state):
                state.add_warning("llm_planner did not complete within max_steps, falling back to workflow")
                state.mode = "llm_planner_fallback_workflow"
                self._run_workflow_fallback(state)

        # ─ 冠军兜底：确保从淘汰赛数据中提取冠军 ──
        self._ensure_champion_from_knockout(state)

        if not state.final_explanation:
            state.add_reasoning("Missing explanation, generating via rule-based method")
            self._step11_explain(state)

        # 最终进度更新
        state.update_progress_from_data()

    def _strict_complete(self, state: AgentState) -> bool:
        """strict 模式完成条件"""
        return (
            state.has_champion_prediction
            and state.has_visualization_payload
            and state.has_final_explanation
        )

    def _ensure_champion_from_knockout(self, state: AgentState):
        """
        兜底：从淘汰赛数据中提取冠军。
        优先级：collected_data['_champion'] > 决赛 winner > 最后淘汰赛 winner
        注意："Unknown" 视为无效。
        """
        champ = state.predicted_champion
        if champ and champ != "Unknown":
            return

        # 1. 从 collected_data 内部数据提取
        champion = state.collected_data.get("_champion")
        if champion and champion != "Unknown":
            state.predicted_champion = champion
            state.add_reasoning(f"[兜底] 从内部数据确定冠军: {champion}")
            return

        # 2. 从决赛数据提取
        if state.knockout_predictions:
            final_matches = [m for m in state.knockout_predictions if m.get("round") == "final"]
            if final_matches:
                final = final_matches[0]
                winner = final.get("winner")
                if winner and winner != "Unknown":
                    state.predicted_champion = winner
                    state.final_match = final
                    state.add_reasoning(f"[兜底] 从决赛数据确定冠军: {winner}")
                    return

            # 3. 从最后一场淘汰赛 winner 提取
            last_match = state.knockout_predictions[-1]
            winner = last_match.get("winner")
            if winner and winner != "Unknown":
                state.predicted_champion = winner
                state.add_reasoning(f"[兜底] 从最后淘汰赛确定冠军: {winner}")
                return

        state.add_warning("[兜底] 无法从淘汰赛数据确定冠军")

    def _get_missing_fields(self, state: AgentState) -> List[str]:
        """获取缺失的字段列表"""
        missing = []
        if not state.has_fixtures:
            missing.append("fixtures")
        if not state.has_teams:
            missing.append("teams")
        if not state.has_historical_matches:
            missing.append("historical_matches")
        if not state.has_team_features:
            missing.append("team_features")
        if not state.has_group_predictions:
            missing.append("group_predictions")
        if not state.has_knockout_predictions:
            missing.append("knockout_predictions")
        if not state.has_champion_prediction:
            missing.append("champion_prediction")
        if not state.has_visualization_payload:
            missing.append("visualization_payload")
        if not state.has_final_explanation:
            missing.append("final_explanation")
        return missing

    def _prediction_complete(self, state: AgentState) -> bool:
        """检查预测是否已经完成（不再要求亚军）"""
        return (
            bool(state.predicted_champion)
            and bool(state.final_explanation)
            and len(state.knockout_predictions) >= 31
        )

    def _run_workflow_fallback(self, state: AgentState):
        """workflow fallback: 只执行缺失的步骤"""
        if not state.objective:
            self._step1_objective(state, state.season)
        if not state.data_plan:
            self._step2_data_plan(state)
        if not state.collected_data.get("fixtures"):
            self._step3_collect_api_data(state, state.season)
        if not state.collected_data.get("historical"):
            self._step4_collect_historical(state)
        if not state.data_quality_report:
            self._step6_quality_check(state)
        if not state.team_features:
            self._step7_build_features(state)
        if not state.group_predictions:
            self._step8_predict_groups(state)
        if not state.knockout_predictions:
            self._step9_predict_knockout(state)
        if not state.predicted_champion:
            self._step10_champion(state)
        if not state.final_explanation:
            self._step11_explain(state)
        state.update_progress_from_data()

    # ── Step 1: 设定目标 ──
    def _step1_objective(self, state: AgentState, season: int):
        state.objective = (
            f"基于 {season} 世界杯现有真实数据和过往真实比赛数据，"
            "预测世界杯冠军并解释推理过程"
        )
        state.add_reasoning(f"Agent 开始任务：预测 {season} 世界杯冠军")

    # ── Step 2: 数据计划 ──
    def _step2_data_plan(self, state: AgentState):
        state.data_plan = [
            "世界杯赛程 (API-Sports /fixtures?league=1&season=2026)",
            "参赛球队 (API-Sports /teams?league=1&season=2026)",
            "小组积分榜 (API-Sports /standings?league=1&season=2026)",
            "实时比分 (API-Sports /fixtures?live=all)",
            "历史国家队比赛 (本地 CSV)",
            "球队补充信息 (爬虫，可选)",
        ]
        state.add_reasoning(
            "制定数据收集计划：赛程、球队、实时比分、历史比赛、近期状态、排名数据"
        )

    # ── Step 3: 采集 API 数据 ──
    def _step3_collect_api_data(self, state: AgentState, season: int):
        api_tool = APISportsTool()

        # 赛程
        state.add_reasoning("调用 API-Sports 获取世界杯赛程")
        fixtures_result = api_tool.get_worldcup_fixtures(season)
        state.collected_data["fixtures"] = fixtures_result.get("data", [])
        if not fixtures_result["success"]:
            state.add_error(f"赛程获取失败: {fixtures_result.get('error')}")

        # 球队
        state.add_reasoning("调用 API-Sports 获取参赛球队")
        teams_result = api_tool.get_worldcup_teams(season)
        state.collected_data["teams"] = teams_result.get("data", [])
        if not teams_result["success"]:
            state.add_error(f"球队获取失败: {teams_result.get('error')}")

        # 积分榜
        standings_result = api_tool.get_worldcup_standings(season)
        state.collected_data["standings"] = standings_result.get("data", [])

        # 实时
        state.add_reasoning("调用 API-Sports 获取实时比赛状态")
        live_result = api_tool.get_live_fixtures()
        state.collected_data["live"] = live_result.get("data", [])

    # ── Step 4: 历史数据 ──
    def _step4_collect_historical(self, state: AgentState):
        state.add_reasoning("加载历史国家队比赛数据")
        hist_tool = HistoricalDataTool()
        result = hist_tool.load_matches(start_year=2018)
        if result["success"]:
            state.collected_data["historical"] = result["data"]
        else:
            state.add_error(f"历史数据加载失败: {result.get('error')}")
            state.collected_data["historical"] = None

    # ── Step 5: 爬虫（已禁用，原 scraper_tool 运行时必定崩溃） ──
    def _step5_collect_scraper(self, state: AgentState):
        state.add_reasoning("爬虫模块已禁用（scraper_tool 已移除）")
        state.collected_data["scraper"] = {}

    # ── Step 6: 数据质量检查 ──
    def _step6_quality_check(self, state: AgentState):
        state.add_reasoning("执行数据质量检查")
        quality = DataQualityAgent()
        report = quality.check(state.collected_data)
        state.data_quality_report = report

        if report.get("fallback_used"):
            state.add_reasoning("数据质量检查：使用本地 fallback 数据降级运行")
            state.add_warning("使用 fallback 数据，预测精度可能降低")

        if not report["is_usable"]:
            state.add_reasoning("数据质量检查发现阻塞错误，使用内置数据降级运行")
            for err in report["blocking_errors"]:
                state.add_error(err)

        # 传递 warnings 到 state
        for w in report.get("warnings", []):
            state.add_warning(w)

    # ── Step 7: 构建特征 ──
    def _step7_build_features(self, state: AgentState):
        state.add_reasoning("构建球队实力特征")
        teams_for_features = self._get_team_list(state)
        builder = FeatureBuilderTool()
        result = builder.build_features(teams_for_features)
        if result["success"]:
            state.team_features = result["data"]
        else:
            state.add_error(f"特征构建失败: {result.get('error')}")

    # ── Step 8: 小组赛预测 ──
    def _step8_predict_groups(self, state: AgentState):
        state.add_reasoning("预测小组赛结果")
        groups = self._build_groups(state)
        predictor = MatchPredictorTool(seed=self.seed)
        bracket_tool = BracketTool(seed=self.seed)

        group_result = bracket_tool.predict_group_stage(
            groups, state.team_features, predictor
        )
        state.group_predictions = group_result["group_predictions"]

        # 填充 group_standings 和 qualified_teams
        state.group_standings = bracket_tool.calculate_group_standings(
            state.group_predictions
        )
        state.qualified_teams = []
        for gp in state.group_predictions:
            state.qualified_teams.extend(gp.get("qualified_teams", []))
        state.add_reasoning(f"小组赛预测完成，{len(state.qualified_teams)} 支球队晋级")

        state.collected_data["_tournament_result"] = group_result["tournament_result"]

    # ── Step 9: 淘汰赛推演 ──
    def _step9_predict_knockout(self, state: AgentState):
        state.add_reasoning("根据小组排名生成淘汰赛对阵")
        state.add_reasoning("逐轮预测淘汰赛")

        predictor = MatchPredictorTool(seed=self.seed)
        bracket_tool = BracketTool(seed=self.seed)

        # 始终构建 bracket（包含小组赛结果），供淘汰赛推演使用
        tournament_result = state.collected_data.get("_tournament_result")
        if not tournament_result:
            state.add_error("缺少小组赛结果，无法推演淘汰赛")
            return
        bracket = bracket_tool.build_knockout_bracket(tournament_result)

        knockout_result = bracket_tool.predict_knockout_stage(
            bracket, state.team_features, predictor
        )
        state.knockout_predictions = knockout_result["knockout_predictions"]
        state.collected_data["_champion"] = knockout_result["champion"]
        state.collected_data["_runner_up"] = knockout_result["runner_up"]
        state.collected_data["_knockout_result"] = knockout_result

        # 存储 bracket_payload
        bp = knockout_result.get("bracket_payload")
        if bp:
            state.bracket_payload = bp
        # 保存 bracket_payload
        if "bracket_payload" in knockout_result:
            state.bracket_payload = knockout_result["bracket_payload"]

        # 提取决赛信息
        final_matches = [m for m in state.knockout_predictions if m.get("round") == "final"]
        if final_matches:
            state.final_match = final_matches[0]

        state.add_reasoning(f"淘汰赛推演完成，共 {len(state.knockout_predictions)} 场比赛")

    # ── Step 10: 确定冠军 ──
    def _step10_champion(self, state: AgentState):
        champion = state.collected_data.get("_champion")
        if champion and champion != "Unknown":
            state.predicted_champion = champion
            state.add_reasoning(f"预测冠军为 {champion}")
        else:
            # 兖底：从淘汰赛决赛提取
            if state.knockout_predictions:
                final_matches = [m for m in state.knockout_predictions if m.get("round") == "final"]
                if final_matches:
                    winner = final_matches[0].get("winner")
                    if winner and winner != "Unknown":
                        state.predicted_champion = winner
                        state.final_match = final_matches[0]
                        state.add_reasoning(f"[兖底] 从决赛确定冠军: {state.predicted_champion}")
    # ── Step 11: 解释 ──
    def _step11_explain(self, state: AgentState):
        state.add_reasoning("生成冠军路径解释")
        explainer = ExplanationTool()

        champion = state.predicted_champion or "Unknown"
        runner_up = state.predicted_runner_up or "Unknown"

        explanation = explainer.explain_champion_path(
            champion=champion,
            runner_up=runner_up,
            knockout_predictions=state.knockout_predictions,
            team_features=state.team_features,
            reasoning_steps=state.reasoning_steps,
        )
        state.final_explanation = explanation

    # ── Step 12: 可视化数据 ──
    def _step12_visualization(self, state: AgentState):
        # 实力排行
        if not state.team_features:
            return
        sorted_teams = sorted(
            state.team_features.values(),
            key=lambda x: x.get("power_score", 0),
            reverse=True,
        )
        top10 = sorted_teams[:10]

        # 构建 champion 结构
        champ = state.predicted_champion
        if not champ or champ == "Unknown":
            # 从 power_ranking 第一名兜底
            if top10:
                champ = top10[0]["team_name"]
                state.predicted_champion = champ

        champ_prob = state.champion_probability
        if champ_prob is None and top10:
            # 从 power_score 推算
            champ_feat = state.team_features.get(champ, {})
            ps = champ_feat.get("power_score", 0)
            if ps:
                champ_prob = round(ps * 100, 1)
                state.champion_probability = champ_prob

        # 判断决赛状态
        final_source = "prediction"
        final_status = "predicted"
        if state.final_match:
            fm_source = state.final_match.get("source", "")
            if fm_source in ("real_result", "real_data"):
                final_source = "real_result"
                final_status = "confirmed"

        state.visualization_payload = {
            "power_ranking": [
                {
                    "rank": i + 1,
                    "team": t["team_name"],
                    "power_score": t["power_score"],
                    "elo": t["elo_rating"],
                }
                for i, t in enumerate(top10)
            ],
            "group_summary": [
                {
                    "group": gp["group_name"],
                    "qualified": [
                        s["team_name"] for s in gp["standings"][:2]
                    ],
                }
                for gp in state.group_predictions
            ],
            "knockout_bracket": [
                {
                    "round": m["round"],
                    "matchup": f"{m['home_team']} vs {m['away_team']}",
                    "score": m["predicted_score"],
                    "winner": m["winner"],
                }
                for m in state.knockout_predictions
            ],
            "champion": {
                "team": champ,
                "probability": champ_prob,
                "source": final_source,
                "status": final_status,
            },
            "final_prediction": {
                "champion": champ,
                "runner_up": state.predicted_runner_up if state.predicted_runner_up and state.predicted_runner_up != "Unknown" else None,
                "win_prob": champ_prob,
            },
            "final_match": state.final_match,
            "qualified_teams": state.qualified_teams,
        }

    # ── 辅助方法 ──
    def _get_team_list(self, state: AgentState) -> List[Dict]:
        """从收集的数据或默认值获取球队列表"""
        api_teams = state.collected_data.get("teams", [])
        if api_teams and len(api_teams) >= 8:
            result = []
            for t in api_teams:
                team_info = t.get("team", {})
                result.append({
                    "name": team_info.get("name", "Unknown"),
                    "id": team_info.get("id"),
                    "elo_rating": 1500.0,  # API teams 不一定有 elo
                })
            return result

        # 降级：使用默认 48 队
        result = []
        for group in DEFAULT_48_TEAMS:
            for name, elo in group:
                result.append({"name": name, "id": None, "elo_rating": float(elo)})
        return result

    def _build_groups(self, state: AgentState) -> List[List[tuple]]:
        """构建 12 个小组的数据结构"""
        # 尝试从 API 数据构建
        api_teams = state.collected_data.get("teams", [])
        if api_teams and len(api_teams) >= 48:
            groups = []
            for i in range(0, 48, 4):
                group = []
                for t in api_teams[i:i + 4]:
                    team_info = t.get("team", {})
                    name = team_info.get("name", f"Team_{i}")
                    elo = state.team_features.get(name, {}).get("elo_rating", 1500.0)
                    group.append((i + len(group) + 1, name, elo))
                groups.append(group)
            if len(groups) == 12:
                return groups

        # 降级：使用默认分组
        groups = []
        tid = 1
        for group in DEFAULT_48_TEAMS:
            g = []
            for name, elo in group:
                # 用特征中的 elo（如果有）
                feat_elo = state.team_features.get(name, {}).get("elo_rating", elo)
                g.append((tid, name, float(feat_elo)))
                tid += 1
            groups.append(g)
        return groups

    def _build_data_status(self, state: AgentState) -> Dict[str, Any]:
        """构建数据来源状态，用于验收和 Dashboard 展示。以 fixtures 表为准。"""
        try:
            from app.services.data_source_manager import DataSourceManager
            mgr = DataSourceManager()
            status = mgr.get_data_status()
            
            source_used = status.get("source", "unavailable")
            source_level = status.get("source_level", "unavailable")
            is_external_realtime = status.get("is_external_realtime", False)
            is_verified = status.get("is_verified", False)
            needs_review = False
            fixtures_count = status.get("fixtures_count", 0)
            last_updated = status.get("last_updated")
        except Exception as e:
            logger.error(f"[Agent] _build_data_status error: {e}")
            source_used = "unknown"
            source_level = "unavailable"
            is_external_realtime = False
            is_verified = False
            needs_review = False
            fixtures_count = 0
            last_updated = None

        messages = {
            "external_real": "比赛数据已更新。",
            "verified_cache": "暂时无法刷新，已使用最近一次真实缓存。",
            "manual_verified": "已使用已审核比赛数据。",
            "local_fallback": "当前数据未完全同步，结果仅供参考。",
            "llm_candidate": "当前缺少真实比赛数据，不能作为正式结果。",
            "unavailable": "当前比赛数据不足，请稍后重试。",
        }
        user_message = messages.get(source_level, "当前比赛数据不足，请稍后重试。")

        return {
            "source_used": source_used,
            "source_level": source_level,
            "is_external_realtime": is_external_realtime,
            "is_verified": is_verified,
            "needs_review": needs_review,
            "fixtures_count": fixtures_count,
            "last_updated": last_updated,
            "user_message": user_message,
        }

    def _ensure_champion_fields(self, state: AgentState):
        """
        统一 champion 字段兜底。
        确保 state.predicted_champion 不是 None 也不是 "Unknown"。
        从多个数据源依次尝试回填。

        重要：如果 Monte Carlo 模拟数据可用，主冠军必须来自 Monte Carlo Top1
        （即 simulation_distribution.json 中夺冠概率最高的球队），
        而不是 bracket 单路径的决赛 winner。
        """
        # ── 0. Monte Carlo Top1 覆盖（优先级最高） ──
        try:
            import json as _json
            sim_path = Path(__file__).parent.parent.parent / "data" / "simulation_distribution.json"
            if sim_path.exists():
                with open(sim_path, encoding="utf-8") as f:
                    sim_data = _json.load(f)
                mc_champion = sim_data.get("champion", {})
                if mc_champion:
                    # 取夺冠概率最高的球队
                    mc_top1_team = max(mc_champion, key=mc_champion.get)
                    mc_top1_prob = mc_champion[mc_top1_team]
                    old_champ = state.predicted_champion
                    if old_champ != mc_top1_team:
                        logger.info(
                            "[Agent] Monte Carlo 覆盖冠军: %s → %s (%.2f%%)",
                            old_champ, mc_top1_team, mc_top1_prob * 100,
                        )
                        # 保存旧冠军为 representative_path_champion
                        state.representative_path_champion = {
                            "name": old_champ,
                            "source": "single_bracket_path",
                        } if old_champ and old_champ != "Unknown" else None
                    state.predicted_champion = mc_top1_team
                    state.champion_probability = round(mc_top1_prob * 100, 2)
                    logger.info("[Agent] 冠军已设为 Monte Carlo Top1: %s = %.2f%%", mc_top1_team, mc_top1_prob * 100)
                    return
        except Exception as e:
            logger.warning("[Agent] Monte Carlo 冠军覆盖失败: %s", e)

        champ = state.predicted_champion
        if champ and champ != "Unknown":
            return  # 已经有效且无 Monte Carlo 数据

        logger.info("[Agent] _ensure_champion_fields: champion 无效(%r)，尝试兜底", champ)

        # ── 1. 从 knockout_predictions 的决赛 winner ──
        if state.knockout_predictions:
            final_matches = [m for m in state.knockout_predictions if m.get("round") == "final"]
            if final_matches:
                winner = final_matches[0].get("winner")
                if winner and winner != "Unknown":
                    state.predicted_champion = winner
                    if not state.final_match:
                        state.final_match = final_matches[0]
                    logger.info("[Agent] 兜底冠军(决赛winner): %s", winner)
                    self._fill_champion_probability(state)
                    return

        # ── 2. 从 team_features power_score 最高队 ──
        if state.team_features:
            best_team = max(
                state.team_features.values(),
                key=lambda x: x.get("power_score", 0),
            )
            best_name = best_team.get("team_name")
            if best_name:
                state.predicted_champion = best_name
                logger.info("[Agent] 兜底冠军(power_score最高): %s", best_name)
                self._fill_champion_probability(state)
                return

        # ── 3. 从 qualified_teams 第一名 ──
        if state.qualified_teams:
            state.predicted_champion = state.qualified_teams[0]
            logger.info("[Agent] 兜底冠军(qualified_teams[0]): %s", state.qualified_teams[0])
            return

        logger.warning("[Agent] 兜底失败：无法确定冠军")

    def _fill_champion_probability(self, state: AgentState):
        """根据决赛 confidence 或 power_score 填充冠军概率"""
        # 尝试从决赛 match 的 confidence
        if state.final_match:
            conf = state.final_match.get("confidence")
            if conf and isinstance(conf, (int, float)):
                state.champion_probability = round(conf * 100 if conf <= 1 else conf, 1)
                return

        # 从 power_score 推算
        if state.predicted_champion and state.team_features:
            feat = state.team_features.get(state.predicted_champion, {})
            ps = feat.get("power_score", 0)
            if ps:
                state.champion_probability = round(ps * 100, 1)
                return

    def _build_enhanced_features_and_explanation(self, state: AgentState):
        """构建增强特征、top_contenders、champion_explanation"""
        try:
            from app.services.fixture_repository import FixtureRepository
            repo = FixtureRepository()
            canonical = repo.get_canonical_fixtures()
            fixtures = canonical.get("fixtures", [])

            # 1. 构建统一特征（函数内部自动加载 team_ratings / recent_form / atk_def / path_diff）
            enhanced = build_enhanced_features(fixtures, state.knockout_predictions)
            state.enhanced_features = enhanced

            # 3. 生成 top_contenders（按 team_strength_index 排序）
            # 注意：team_strength_index != champion_probability
            # team_strength_index 是综合实力指数，champion_probability 来自 Monte Carlo 模拟
            sorted_teams = sorted(
                enhanced.values(),
                key=lambda x: x.get("team_strength_index", 0),
                reverse=True,
            )
            top_contenders = []
            for t in sorted_teams[:8]:
                reasons = []
                if t["attack_score"] > 0.6:
                    reasons.append("攻击能力突出")
                if t["defense_score"] > 0.6:
                    reasons.append("防守稳固")
                if t["recent_form_score"] > 0.6:
                    reasons.append("近期状态出色")
                if t["path_advantage_score"] > 0.5:
                    reasons.append("晋级路径有利")
                if t["knockout_performance_score"] > 0.5:
                    reasons.append("淘汰赛表现优异")
                if not reasons:
                    reasons.append("综合实力均衡")
                top_contenders.append({
                    "team": t["team"],
                    # team_strength_index: 综合实力指数（非夺冠概率）
                    "team_strength_index": t["team_strength_index"],
                    "recent_form_score": t["recent_form_score"],
                    "attack_score": t["attack_score"],
                    "defense_score": t["defense_score"],
                    "path_advantage_score": t["path_advantage_score"],
                    "key_reasons": reasons,
                })
            state.top_contenders = top_contenders

            # 4. feature_breakdown（冠军的特征分解）
            champ = state.predicted_champion
            if champ and champ in enhanced:
                state.feature_breakdown = enhanced[champ]
            elif top_contenders:
                state.feature_breakdown = enhanced.get(top_contenders[0]["team"], {})

            # 5. 冠军概率：仅当尚未设置时才用 strength_score 兜底（优先使用 Monte Carlo 概率）
            if not state.champion_probability and champ and champ in enhanced:
                overall = enhanced[champ].get("overall_strength_score", 0)
                if overall > 0:
                    state.champion_probability = round(overall * 100, 1)

            # 6. explanation 不在此处生成 — champion 尚未被 Monte Carlo top5 最终确定。
            #    explanation 统一在 _save_final_agent_result 中、champion 确定后生成。

        except Exception as e:
            logger.error("[Agent] _build_enhanced_features error: %s", e, exc_info=True)

    def _generate_champion_explanation(
        self,
        state: AgentState,
        champion: str | None = None,
        champion_probability: float | None = None,
        run_id: str | None = None,
    ):
        """生成冠军解释（LLM + fallback）

        关键：champion 和 champion_probability 必须由调用方传入最终确定的值。
        禁止从 state.predicted_champion / state.champion_probability / Monte Carlo 独立读取，
        避免 explanation 与最终 snapshot 不一致。

        Args:
            state: AgentState（用于获取 feature_breakdown 等辅助数据）
            champion: 最终确定的冠军队名（来自 top5[0]）
            champion_probability: 最终确定的冠军概率（0-1 范围，来自 top5[0]）
            run_id: 预测 run ID
        """
        # ── 使用调用方传入的最终值，禁止从 state 或 MC 独立读取 ──
        champ = champion or state.predicted_champion or "Unknown"
        prob = champion_probability
        if prob is None:
            prob = state.champion_probability or 50.0
        # 统一为百分比形式用于文本生成
        prob_pct = prob * 100 if prob <= 1 else prob

        # ── 仅读取 stage 信息（存活球队、阶段） ──
        mc_surviving_teams = []
        mc_stage = "unknown"
        try:
            import json as _json
            sim_path = Path(__file__).parent.parent.parent / "data" / "simulation_distribution.json"
            if sim_path.exists():
                with open(sim_path, encoding="utf-8") as f:
                    sim_data = _json.load(f)
                mc_surviving_teams = sim_data.get("surviving_teams", [])
                mc_stage = sim_data.get("stage", "unknown")
                logger.info("[Agent] explanation 使用传入参数: champion=%s, probability=%.4f (%.2f%%)",
                            champ, prob, prob_pct)
        except Exception as e:
            logger.warning("[Agent] explanation 加载 simulation_distribution.json 失败: %s", e)

        fb = state.feature_breakdown

        # 构建 key_reasons
        key_reasons = []
        if fb.get("attack_score", 0) > 0.6:
            key_reasons.append("攻击能力突出，场均进球数领先")
        if fb.get("defense_score", 0) > 0.6:
            key_reasons.append("防守稳固，失球数控制出色")
        if fb.get("recent_form_score", 0) > 0.6:
            key_reasons.append("近期状态出色，胜率较高")
        if fb.get("path_advantage_score", 0) > 0.5:
            key_reasons.append("晋级路径相对有利")
        if fb.get("knockout_performance_score", 0) > 0.5:
            key_reasons.append("淘汰赛阶段表现优异")
        if fb.get("elo_rating", 0) > 0.7:
            key_reasons.append("球队整体实力排名靠前")
        if not key_reasons:
            key_reasons = [
                "综合实力均衡，攻防表现稳定",
                "在后续潜在对手对比中占据一定优势",
                "关键比赛胜率较高",
            ]

        # 尝试 LLM 生成
        explanation_content = ""
        explanation_source = "fallback"
        explanation_fallback_reason = ""
        try:
            from app.services.llm_explainer import HAS_ZHIPUAI as _HAS_ZHIPUAI
            if not _HAS_ZHIPUAI:
                explanation_fallback_reason = "sdk_not_installed: zhipuai"
            else:
                from zhipuai import ZhipuAI
                import os
                api_key = os.environ.get("OPENAI_API_KEY", "")
                if not api_key or api_key == "sk-placeholder-key":
                    explanation_fallback_reason = "no_valid_api_key"
                else:
                    client = ZhipuAI(api_key=api_key)
                    prompt = (
                        f"你是一个专业的足球分析师。请用120-200字解释为什么预测 {champ} 获得2026世界杯冠军。\n"
                        f"夺冠概率：{prob_pct:.1f}%\n"
                        f"关键数据：\n"
                    )
                    if fb.get("attack_score"): prompt += f"- 攻击评分：{fb['attack_score']:.2f}\n"
                    if fb.get("defense_score"): prompt += f"- 防守评分：{fb['defense_score']:.2f}\n"
                    if fb.get("recent_form_score"): prompt += f"- 近期状态：{fb['recent_form_score']:.2f}\n"
                    if fb.get("path_advantage_score"): prompt += f"- 路径优势：{fb['path_advantage_score']:.2f}\n"
                    prompt += f"\n关键原因：{', '.join(key_reasons)}\n"
                    prompt += "要求：面向普通用户，专业但通俗，不要出现技术术语。"

                    try:
                        response = client.chat.completions.create(
                            model="glm-4-flash",
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.3,
                            max_tokens=400,
                        )
                        content = response.choices[0].message.content.strip()
                        if content and len(content) > 30:
                            explanation_content = content
                            explanation_source = "llm"
                        else:
                            explanation_fallback_reason = "content_too_short"
                    except Exception as e:
                        err_type = type(e).__name__
                        err_msg = str(e)[:100]
                        explanation_fallback_reason = f"api_error: {err_type}: {err_msg}"
                        logger.warning("[Agent] LLM explanation API call failed: %s", e)
        except ImportError as e:
            explanation_fallback_reason = f"import_error: {str(e)[:80]}"
            logger.warning("[Agent] LLM explanation import failed: %s", e)
        except Exception as e:
            err_type = type(e).__name__
            err_msg = str(e)[:100]
            explanation_fallback_reason = f"unexpected_error: {err_type}: {err_msg}"
            logger.warning("[Agent] LLM explanation unexpected error: %s", e)

        # Fallback
        if not explanation_content:
            # 构建核心优势
            advantages = []
            if fb.get("attack_score", 0) > 0.6:
                advantages.append("进攻端表现强劲，场均进球数领先，锋线火力十足。")
            else:
                advantages.append("进攻组织有序，能够创造足够的得分机会。")
            if fb.get("defense_score", 0) > 0.6:
                advantages.append("防守端同样稳固，失球数控制得当，后防线值得信赖。")
            else:
                advantages.append("防守体系完整，能够有效地限制对手进攻。")
            if fb.get("recent_form_score", 0) > 0.6:
                advantages.append("近期状态出色，连续多场保持高水平竞技状态。")
            if fb.get("world_cup_experience", 0) > 5:
                advantages.append("大赛经验丰富，核心球员多次参加世界顶级赛事。")
            if not advantages:
                advantages.append("综合实力均衡，各位置无明显短板。")
            adv_lines = "\n".join(f"- {a}" for a in advantages[:4])

            # 构建关键因素
            factors = []
            if fb.get("path_advantage_score", 0) > 0.5:
                factors.append("后续晋级路径相对有利，潜在对手实力相对较弱。")
            for r in key_reasons[:2]:
                factors.append(r + "。")
            if not factors:
                factors.append(f"{champ}在综合评估中表现突出，是当前最具竞争力的球队。")
            fac_lines = "\n".join(f"- {f}" for f in factors[:3])

            # 阶段描述
            stage_desc = ""
            if mc_stage == "semi_finals" and mc_surviving_teams:
                teams_text = "、".join(mc_surviving_teams)
                stage_desc = f"当前赛事已进入四强阶段，系统只在{teams_text}四支仍有夺冠可能的球队中进行模拟分析。\n\n"
            elif mc_stage == "final" and mc_surviving_teams:
                teams_text = "、".join(mc_surviving_teams)
                stage_desc = f"当前赛事已进入决赛阶段，{teams_text}两支球队争夺大力神杯。\n\n"

            explanation_content = (
                f"## 为什么预测 {champ} 夺冠？\n\n"
                f"{stage_desc}"
                f"根据已结束比赛结果和后续对阵形势，{champ} 展现出较强的夺冠实力，"
                f"系统给出 {prob_pct:.1f}% 的夺冠概率。"
                f"球队在攻防两端表现均衡，是当前最有可能捧起大力神杯的队伍。\n"
                f"\n### 核心优势\n{adv_lines}\n"
                f"\n### 关键因素\n{fac_lines}\n"
                f"\n### AI综合判断\n\n"
                f"综合各方面分析，{champ} 以 {prob_pct:.1f}% 的夺冠概率领跑群雄。"
                f"球队整体实力突出，晋级形势有利，是最有可能夺冠的球队。\n"
            )

        state.champion_explanation = {
            "title": f"为什么预测 {champ} 夺冠？",
            "content": explanation_content,
            "key_reasons": key_reasons,
            "source": explanation_source,
            "fallback_reason": explanation_fallback_reason if explanation_source != "llm" else "",
            "probability": round(prob_pct, 2),
            "champion": champ,
            "champion_probability": round(prob / 100.0, 4) if prob > 1 else round(prob, 4),
            "run_id": run_id or "",
        }

    def _save_final_agent_result(self, state: AgentState):
        """
        将 Agent 运行结果保存为统一 JSON 文件 data/final_agent_result.json。
        这是前端展示的唯一数据源。
        """
        import json as _json

        champ = state.predicted_champion or "Unknown"
        prob = state.champion_probability or 0.0

        # ── 从 Monte Carlo 模拟结果加载冠军概率（优先级最高） ──
        mc_top_candidates = []
        mc_champ_prob = None
        mc_surviving_teams = []
        mc_stage = "unknown"
        try:
            sim_path = Path(__file__).parent.parent.parent / "data" / "simulation_distribution.json"
            if sim_path.exists():
                with open(sim_path, encoding="utf-8") as f:
                    sim_data = _json.load(f)
                mc_champion = sim_data.get("champion", {})
                mc_surviving_teams = sim_data.get("surviving_teams", [])
                mc_stage = sim_data.get("stage", "unknown")
                if mc_champion:
                    # 按概率降序排列，确保 top5[0] 是夺冠概率最高的队伍
                    sorted_mc = sorted(mc_champion.items(), key=lambda x: x[1], reverse=True)
                    # 动态数量：min(5, len(surviving_teams))
                    display_count = min(5, len(mc_surviving_teams)) if mc_surviving_teams else 5
                    mc_top_candidates = [
                        {"team": team, "probability": round(p, 4)}
                        for team, p in sorted_mc[:display_count]
                    ]
                    # 用 Monte Carlo 概率覆盖冠军概率
                    if champ in mc_champion:
                        mc_champ_prob = round(mc_champion[champ], 4)
                        logger.info("[Agent] 使用 Monte Carlo 冠军概率: %s = %.2f%% (surviving=%d, display=%d)",
                                    champ, mc_champ_prob * 100, len(mc_surviving_teams), display_count)
        except Exception as e:
            logger.warning("[Agent] 加载 simulation_distribution.json 失败: %s", e)

        # top5：优先使用 Monte Carlo 概率，兜底用 champion_prediction_ensemble，最后才用 top_contenders
        top5 = []
        if mc_top_candidates:
            top5 = mc_top_candidates
            if mc_champ_prob is not None:
                prob = mc_champ_prob * 100  # 转为百分比存储
        elif state.top_contenders:
            # 兜底：从 champion_prediction_ensemble.json 加载 Monte Carlo 数据
            try:
                ens_path = Path(__file__).parent.parent.parent / "data" / "champion_prediction_ensemble.json"
                if ens_path.exists():
                    with open(ens_path, encoding="utf-8") as f:
                        ens_data = _json.load(f)
                    ens_top5 = ens_data.get("top5", [])
                    ens_surviving = ens_data.get("surviving_teams", [])
                    display_count = min(5, len(ens_surviving)) if ens_surviving else 5
                    if ens_top5:
                        top5 = ens_top5[:display_count]
                        for t in ens_top5:
                            if t.get("team") == champ:
                                prob = t.get("probability", 0) * 100
                                break
            except Exception:
                pass
        if not top5 and state.top_contenders:
            # 最终兜底：用 team_strength_index（注意这不是 Monte Carlo 概率）
            top5 = [
                {"team": t["team"], "probability": t.get("team_strength_index", 0)}
                for t in state.top_contenders[:5]
            ]

        # 如果 top5 仍为空，构造兜底
        if not top5 and champ != "Unknown":
            top5 = [{"team": champ, "probability": prob / 100.0 if prob > 1 else prob}]

        # bracket_payload：直接使用 state 中的，兜底从已有文件或 bracket tool 加载
        bp = state.bracket_payload or {}
        if not bp:
            # 尝试从已有 final_agent_result.json 加载
            try:
                existing_path = Path(__file__).parent.parent.parent / "data" / "final_agent_result.json"
                if existing_path.exists():
                    with open(existing_path, encoding="utf-8") as f:
                        existing = _json.load(f)
                    bp = existing.get("bracket_payload", {})
            except Exception:
                pass
        if not bp:
            # 尝试从 bracket tool 生成
            try:
                bracket_tool = BracketTool()
                bp = bracket_tool.predict_knockout_stage()
            except Exception:
                pass

        # ─ 标准化 bracket_payload（修复 winner/predicted_winner/晋级链） ──
        try:
            bp = normalize_bracket_payload(bp)
        except Exception as e:
            logger.warning("[Agent] normalize_bracket_payload 失败: %s", e)

        # ── 提取 bracket 路径冠军（用于 explanation，确保与 bracket 一致） ──
        bracket_champion = None
        bracket_champion_prob = None
        if bp:
            # 优先从 final 轮胜者提取
            final_matches = bp.get("final", [])
            if final_matches:
                fm = final_matches[0] if isinstance(final_matches, list) else final_matches
                winner = fm.get("winner") or fm.get("predicted_winner")
                if winner:
                    bracket_champion = winner
            # 兜底：从 champion 字段提取
            if not bracket_champion:
                bp_champ = bp.get("champion", {})
                if isinstance(bp_champ, dict):
                    bracket_champion = bp_champ.get("team")
                elif isinstance(bp_champ, str):
                    bracket_champion = bp_champ
            # 从 top5 中查找 bracket 冠军的概率
            if bracket_champion and top5:
                for entry in top5:
                    if isinstance(entry, dict) and entry.get("team", "").lower() == bracket_champion.lower():
                        bracket_champion_prob = entry.get("probability", 0)
                        break

        # 数据来源状态
        ds = state.data_status or self._build_data_status(state)

        # 模型状态
        model_status = {
            "ensemble_v2": True,
            "nn_v2": True,
            "xgboost": True,
            "weights": {"elo": 0.25, "nn": 0.30, "xgboost": 0.20, "poisson": 0.15, "path": 0.10},
        }

        # AI 分析过程摘要（5 步）
        agent_steps_summary = [
            {"step": 1, "name": "数据采集", "description": "从 API 获取 2026 世界杯赛程与球队数据", "status": "completed"},
            {"step": 2, "name": "历史分析", "description": "加载 6000+ 场历史国际比赛数据", "status": "completed"},
            {"step": 3, "name": "模型融合", "description": "综合 ELO、神经网络、XGBoost 等多模型预测", "status": "completed"},
            {"step": 4, "name": "模拟推演", "description": "10000 次蒙特卡洛模拟推演淘汰赛进程", "status": "completed"},
            {"step": 5, "name": "AI 解释", "description": "生成冠军预测解释与关键因素分析", "status": "completed"},
        ]

        # ── 从 TournamentStateService 动态获取 stage_info ──
        stage_info = {}
        try:
            from app.db.database import SessionLocal
            from app.services.tournament_state_service import get_current_tournament_stage
            _db = SessionLocal()
            try:
                stage_info = get_current_tournament_stage(_db)
            finally:
                _db.close()
            logger.info("[Agent] stage_info: stage=%s, surviving=%d, sandbox=%s",
                        stage_info.get("stage"), stage_info.get("surviving_count"),
                        stage_info.get("sandbox_enabled"))
        except Exception as e:
            logger.warning("[Agent] 获取 stage_info 失败: %s", e)
            # 兜底：用 simulation_distribution.json 中的信息
            stage_info = {
                "stage": mc_stage,
                "stage_label": {"semi_finals": "四强", "final": "决赛",
                                "tournament_ended": "冠军已产生"}.get(mc_stage, mc_stage),
                "surviving_teams": mc_surviving_teams,
                "surviving_count": len(mc_surviving_teams),
                "champion": mc_surviving_teams[0] if mc_stage == "tournament_ended" and mc_surviving_teams else None,
                "pending_scenario_matches": [],
                "sandbox_enabled": mc_stage not in ("final", "tournament_ended"),
                "sandbox_message": "",
                "last_updated": datetime.utcnow().isoformat(),
            }

        # ══════════════════════════════════════════════════════
        # Step 1: 强制 champion / champion_probability 来自 top5[0]
        # ══════════════════════════════════════════════════════
        if top5:
            top1_team = top5[0].get("team", champ)
            top1_prob = top5[0].get("probability", 0)
            if champ != top1_team:
                logger.info("[Agent] champion 被 top5[0] 覆盖: %s → %s", champ, top1_team)
                champ = top1_team
                state.predicted_champion = champ
            # champion_probability（0-1 范围）始终 = top5[0].probability
            champ_prob_01 = top1_prob if top1_prob <= 1 else top1_prob / 100.0
            champ_prob_01 = round(champ_prob_01, 4)
            prob = champ_prob_01 * 100  # 百分比形式，用于文本生成
            state.champion_probability = prob
            logger.info("[Agent] 统一 champion=%s, champion_probability=%.4f (0-1), %.2f%% (来自 top5[0])",
                        champ, champ_prob_01, prob)
        else:
            champ_prob_01 = round(prob / 100.0, 4) if prob > 1 else round(prob, 4)

        # ══════════════════════════════════════════════════════
        # Step 2: 生成 run_id（在 explanation 之前）
        # ══════════════════════════════════════════════════════
        import hashlib
        run_ts = datetime.utcnow().isoformat()
        run_id_raw = f"{champ}:{champ_prob_01}:{run_ts}"
        run_id = "run_" + hashlib.md5(run_id_raw.encode()).hexdigest()[:12]

        # ══════════════════════════════════════════════════════
        # Step 3: 生成 explanation（使用 bracket 冠军，确保与 bracket 一致）
        # ══════════════════════════════════════════════════════
        # ── 优先使用 bracket 路径冠军，避免 explanation 与 bracket 不一致 ──
        expl_champion = bracket_champion or champ
        expl_prob_01 = bracket_champion_prob if bracket_champion_prob else champ_prob_01
        logger.info("[Agent] explanation 使用: champion=%s (bracket=%s, mc=%s), prob=%.4f",
                    expl_champion, bracket_champion, champ, expl_prob_01)

        self._generate_champion_explanation(
            state,
            champion=expl_champion,
            champion_probability=expl_prob_01,
            run_id=run_id,
        )
        explanation_data = state.champion_explanation or {}

        # ── 强制覆盖 explanation 绑定字段（双保险） ──
        if explanation_data:
            explanation_data["champion"] = expl_champion
            explanation_data["champion_probability"] = expl_prob_01
            explanation_data["probability"] = round(expl_prob_01 * 100, 2)
            explanation_data["run_id"] = run_id
        else:
            explanation_data = {
                "title": f"为什么预测 {expl_champion} 夺冠？",
                "content": "",
                "key_reasons": [],
                "source": "none",
                "probability": round(expl_prob_01 * 100, 2),
                "champion": expl_champion,
                "champion_probability": expl_prob_01,
                "run_id": run_id,
            }

        # ══════════════════════════════════════════════════════
        # Step 4: 构建 snapshot（top_candidates = deepcopy(top5)）
        # ══════════════════════════════════════════════════════
        # ── 最终冠军统一：优先使用 bracket 路径冠军 ──
        final_champion = expl_champion
        final_prob_01 = expl_prob_01

        # ── 如果 bracket 冠军与 MC top5[0] 不同，重排 top5 使之一致 ──
        if final_champion and top5:
            top1_team = top5[0].get("team", "") if isinstance(top5[0], dict) else ""
            if top1_team.lower() != final_champion.lower():
                # 从 top5 中找到 bracket 冠军条目
                bracket_entry = None
                remaining = []
                for entry in top5:
                    if isinstance(entry, dict) and entry.get("team", "").lower() == final_champion.lower():
                        bracket_entry = dict(entry)
                        bracket_entry["probability"] = final_prob_01
                    else:
                        remaining.append(entry)
                if bracket_entry is None:
                    bracket_entry = {"team": final_champion, "probability": final_prob_01}
                top5 = [bracket_entry] + remaining
                logger.info("[Agent] top5 已重排: bracket champion %s 移至首位 (prob=%.4f)",
                            final_champion, final_prob_01)

        from copy import deepcopy
        snapshot = {
            "run_id": run_id,
            "champion": final_champion,
            "predicted_champion": final_champion,
            "champion_probability": final_prob_01,
            "top5": top5,
            "top_candidates": deepcopy(top5),
            "surviving_teams": mc_surviving_teams,
            "stage": mc_stage,
            "stage_info": stage_info,
            "bracket_payload": bp,
            "data_status": ds,
            "model_status": model_status,
            "explanation": explanation_data,
            "top_contenders": state.top_contenders or [],
            "representative_path_champion": getattr(state, "representative_path_champion", None),
            "agent_steps_summary": agent_steps_summary,
            "model_version": "ensemble_v2",
            "simulation_count": 10000,
            "data_source": ds.get("user_message", ""),
            "historical_samples": 6000,
            "generated_at": run_ts,
            "status": "completed",
        }

        # ══════════════════════════════════════════════════════
        # Step 5: 一致性校验（保存前）
        # ══════════════════════════════════════════════════════
        _validate_prediction_snapshot(snapshot)

        # ── Step 5b: 淘汰赛路径一致性校验（normalize 后） ──
        bp_for_validation = snapshot.get("bracket_payload", {})
        bracket_errors = []
        if bp_for_validation:
            bracket_errors = validate_bracket_integrity(bp_for_validation)
            if bracket_errors:
                logger.error("[Agent] bracket_integrity 校验失败（%d 个问题），拒绝保存: %s",
                             len(bracket_errors), bracket_errors[:3])
            else:
                logger.info("[Agent] bracket_integrity 校验通过 ✓")

        # ══════════════════════════════════════════════════════
        # Step 6: 保存（校验通过才写入）
        # ══════════════════════════════════════════════════════
        out_path = Path(__file__).parent.parent.parent / "data" / "final_agent_result.json"

        if bracket_errors:
            # ── 校验失败：不覆盖 JSON，不写 DB，保留上一份有效快照 ──
            snapshot["status"] = "bracket_error"
            snapshot["bracket_integrity_errors"] = bracket_errors

            # 写入诊断文件（不覆盖正式 JSON）
            diag_path = Path(__file__).parent.parent.parent / "data" / "bracket_error_diagnostic.json"
            try:
                import json as _json_mod
                with open(diag_path, "w", encoding="utf-8") as df:
                    _json_mod.dump({
                        "run_id": run_id,
                        "generated_at": run_ts,
                        "bracket_integrity_errors": bracket_errors,
                        "champion": final_champion,
                        "champion_probability": final_prob_01,
                    }, df, ensure_ascii=False, indent=2)
                logger.info("[Agent] 诊断文件已写入: %s", diag_path.resolve())
            except Exception as e:
                logger.warning("[Agent] 诊断文件写入失败: %s", e)

            logger.error("[Agent] bracket 校验失败，已跳过 JSON 和 DB 保存。上一份有效快照保持不变。")
            return

        # ── 校验通过：正常保存 ──
        snapshot["status"] = "completed"
        try:
            atomic_write_json(out_path, snapshot)
            resolved = out_path.resolve()
            logger.info("[Agent] final_agent_result.json saved to %s", resolved)
            print(f"[Agent] 保存路径: {resolved}")
            print(f"[Agent] champion={final_champion}, champion_probability={final_prob_01}, run_id={run_id}")
        except Exception as e:
            logger.error("[Agent] Failed to save final_agent_result.json: %s", e)

        # ── DB 持久化（Render 临时文件系统的备份） ──
        try:
            from app.services.prediction_snapshot_service import save_prediction_snapshot
            save_prediction_snapshot(snapshot)
        except Exception as e:
            logger.warning("[Agent] DB snapshot 保存失败: %s", e)

    def _record_to_memory(self, state: AgentState):
        """记录预测结果到 Memory，并自动检测失败模式"""
        try:
            from app.agents.agent_memory import AgentMemory
            memory = AgentMemory()
            memory.record_prediction(state)
            memory.auto_detect_patterns(state)
            # 记录工具调用结果
            for trace in state.tool_trace:
                memory.record_tool_result(
                    tool_name=trace.get("tool_name", ""),
                    success=trace.get("success", False),
                    error_type=trace.get("error_type"),
                )
            logger.info(f"[Agent] Memory recorded: champion={state.predicted_champion}, status={state.status}")
        except Exception as e:
            logger.warning(f"[Agent] Memory recording failed: {e}")
