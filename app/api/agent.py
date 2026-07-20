"""
Agent FastAPI 接口

POST /api/v1/agent/run-prediction  - 一键运行完整预测（支持 mode 参数）
POST /api/v1/agent/refresh-data    - 仅刷新 API 数据
GET  /api/v1/agent/status          - 最近一次 Agent 运行状态
GET  /api/v1/agent/latest-result   - 获取最近一次预测结果
"""

import json
import logging
import threading
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])

# ── 全局状态（最近一次运行结果） ──
_last_run_result: Optional[Dict[str, Any]] = None
_last_run_time: Optional[str] = None

# ── 并发锁：同一时间只允许一个完整预测运行 ──
_prediction_lock = threading.Lock()


def _save_to_db(state_dict: Dict):
    """将 Agent 运行结果持久化到数据库"""
    try:
        from app.db.database import SessionLocal
        from app.models.agent_models import (
            AgentRun, AgentReasoningStep, PredictedMatch, TeamFeature
        )

        db = SessionLocal()
        try:
            run = AgentRun(
                objective=state_dict.get("objective", ""),
                season=state_dict.get("season", 2026),
                predicted_champion=state_dict.get("predicted_champion"),
                predicted_runner_up=state_dict.get("predicted_runner_up"),
                data_quality_score=state_dict.get("data_quality_report", {}).get("score"),
                final_explanation=state_dict.get("final_explanation"),
                status=state_dict.get("status", "completed"),
                errors_json=json.dumps(state_dict.get("errors", []), ensure_ascii=False),
            )
            db.add(run)
            db.flush()
            run_id = run.id

            # 推理步骤
            for i, step in enumerate(state_dict.get("reasoning_steps", []), 1):
                db.add(AgentReasoningStep(
                    agent_run_id=run_id, step_order=i, step_text=step
                ))

            # 预测比赛
            for m in state_dict.get("knockout_predictions", []):
                db.add(PredictedMatch(
                    agent_run_id=run_id,
                    stage=m.get("round", ""),
                    home_team=m.get("home_team", ""),
                    away_team=m.get("away_team", ""),
                    predicted_home_score=m.get("predicted_home_score"),
                    predicted_away_score=m.get("predicted_away_score"),
                    predicted_winner=m.get("winner"),
                    confidence=m.get("confidence"),
                    source=m.get("source", "agent_prediction"),
                ))

            # 球队特征
            for name, feat in state_dict.get("team_features", {}).items():
                if isinstance(feat, dict):
                    db.add(TeamFeature(
                        agent_run_id=run_id,
                        team_name=feat.get("team_name", name),
                        elo_rating=feat.get("elo_rating"),
                        fifa_rank=feat.get("fifa_rank"),
                        recent_win_rate=feat.get("recent_win_rate"),
                        recent_goals_for_avg=feat.get("recent_goals_for_avg"),
                        recent_goals_against_avg=feat.get("recent_goals_against_avg"),
                        attack_score=feat.get("attack_score"),
                        defense_score=feat.get("defense_score"),
                        power_score=feat.get("power_score"),
                        data_confidence=feat.get("data_confidence"),
                    ))

            db.commit()
            logger.info(f"[Agent] 运行结果已保存到 DB，run_id={run_id}")
        except Exception as e:
            logger.error(f"[Agent] DB 保存失败: {e}")
            db.rollback()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[Agent] DB 连接失败: {e}")


class RunPredictionRequest(BaseModel):
    """运行预测请求体"""
    season: int = Field(default=2026, description="世界杯赛季")
    mode: str = Field(
        default="workflow",
        description="Agent 模式: workflow / llm_planner / llm_planner_safe / llm_planner_strict",
    )
    use_llm: bool = Field(default=True, description="是否使用真实 LLM（llm_planner 模式下有效）")


@router.post("/run-prediction")
def run_prediction(request: RunPredictionRequest, background_tasks: BackgroundTasks):
    """一键运行完整冠军预测 Agent"""
    global _last_run_result, _last_run_time

    # ── 并发锁：同一时间只允许一个完整预测 ──
    if not _prediction_lock.acquire(blocking=False):
        return JSONResponse(
            status_code=409,
            content={
                "status": "conflict",
                "message": "已有一个预测任务正在运行，请等待完成后再试",
            },
        )

    try:
        from app.agents.worldcup_agent import WorldCupPredictionAgent

        valid_modes = ("workflow", "llm_planner", "llm_planner_safe", "llm_planner_strict")
        mode = request.mode if request.mode in valid_modes else "workflow"
        agent = WorldCupPredictionAgent(seed=42)
        state = agent.run(season=request.season, mode=mode, use_llm=request.use_llm)
        result = state.to_dict()

        _last_run_result = result
        _last_run_time = datetime.utcnow().isoformat()

        # 异步保存到数据库
        background_tasks.add_task(_save_to_db, result)

        return result
    finally:
        _prediction_lock.release()


class RefreshDataRequest(BaseModel):
    """刷新真实数据请求体"""
    season: int = Field(default=2026, description="世界杯赛季")
    live_only: bool = Field(default=False, description="仅同步实时比分")
    fixtures_only: bool = Field(default=False, description="仅同步赛程")


@router.post("/refresh-data")
def refresh_data(request: RefreshDataRequest = None):
    """仅刷新 API-Sports 真实数据，不运行预测，不读取 fallback"""
    from app.services.worldcup_sync_service import (
        sync_worldcup_fixtures,
        sync_live_fixtures,
        get_fixtures_summary,
    )
    from app.tools.api_sports_tool import APISportsTool

    if request is None:
        request = RefreshDataRequest()

    api = APISportsTool()
    if not api.api_key_detected:
        return {
            "success": False,
            "error": "APISPORTS_KEY / API_FOOTBALL_KEY 未配置",
            "fixtures": {"success": False},
            "teams": {"success": False},
            "live": {"success": False},
        }

    result = {
        "success": True,
        "season": request.season,
        "errors": [],
    }

    # 同步赛程
    if not request.live_only:
        fx = sync_worldcup_fixtures(season=request.season)
        result["fixtures_sync"] = fx
        if not fx.get("success"):
            result["success"] = False
            result["errors"].append(f"fixtures: {fx.get('error')}")

    # 同步实时比分
    if not request.fixtures_only:
        lv = sync_live_fixtures()
        result["live_sync"] = lv
        if not lv.get("success"):
            result["success"] = False
            result["errors"].append(f"live: {lv.get('error')}")

    # 统计
    result["fixtures_summary"] = get_fixtures_summary()

    return result


@router.get("/status")
def agent_status():
    """返回最近一次 Agent 运行状态"""
    if _last_run_result is None:
        return {
            "status": "no_run",
            "message": "尚未运行过 Agent，请调用 POST /api/v1/agent/run-prediction",
        }
    return {
        "status": _last_run_result.get("status", "unknown"),
        "predicted_champion": _last_run_result.get("predicted_champion"),
        "predicted_runner_up": _last_run_result.get("predicted_runner_up"),
        "data_quality_score": _last_run_result.get("data_quality_report", {}).get("score"),
        "reasoning_steps_count": len(_last_run_result.get("reasoning_steps", [])),
        "errors_count": len(_last_run_result.get("errors", [])),
        "last_run_time": _last_run_time,
    }


@router.get("/latest-result")
def latest_result():
    """获取最近一次预测结果完整数据"""
    if _last_run_result is None:
        return {
            "status": "no_run",
            "message": "尚未运行过 Agent，请调用 POST /api/v1/agent/run-prediction",
        }
    return _last_run_result


@router.get("/final-result")
def final_result():
    """
    获取最终预测结果 — 前端展示的唯一数据源。

    读取优先级：
    1. PostgreSQL 最新 completed snapshot
    2. JSON 文件 fallback（验证通过）
    3. 两者均无效时返回 503

    返回前执行一致性校验，校验失败返回 503。
    """
    from pathlib import Path

    data = None
    source = "none"

    # ── 优先级 1: PostgreSQL ──
    try:
        from app.services.prediction_snapshot_service import load_latest_prediction_snapshot
        data = load_latest_prediction_snapshot()
        if data:
            source = "database"
            logger.info("[API] final-result 从 DB 加载成功, top-level keys: %s",
                        list(data.keys())[:8])
    except Exception as e:
        logger.warning("[API] DB 加载失败: %s", e)

    # ── 优先级 2: JSON fallback ──
    if data is None:
        result_path = Path(__file__).parent.parent.parent / "data" / "final_agent_result.json"
        resolved = result_path.resolve()
        logger.info("[API] DB 无数据，尝试 JSON fallback: %s (exists=%s)", resolved, result_path.exists())

        if not result_path.exists():
            return JSONResponse(
                status_code=503,
                content={
                    "status": "no_result",
                    "message": "尚未生成预测结果，请先运行 POST /api/v1/agent/run-prediction",
                },
            )
        try:
            with open(result_path, encoding="utf-8") as f:
                data = json.load(f)
            source = "json"
            logger.info("[API] final-result 从 JSON 加载成功, top-level keys: %s",
                        list(data.keys())[:8])
        except Exception as e:
            logger.error("[API] JSON 读取失败: %s", e)
            return JSONResponse(
                status_code=503,
                content={"status": "error", "message": f"JSON 读取失败: {str(e)}"},
            )

    if data is None:
        return JSONResponse(
            status_code=503,
            content={
                "status": "no_result",
                "message": "DB 和 JSON 均无有效预测数据",
            },
        )

    # ── 返回前一致性校验 ──
    try:
        from app.agents.worldcup_agent import _validate_prediction_snapshot
        _validate_prediction_snapshot(data)
    except AssertionError as e:
        logger.error("[API] final-result 校验失败 (source=%s): %s", source, e)
        return JSONResponse(
            status_code=503,
            content={
                "status": "validation_failed",
                "message": f"预测数据一致性校验失败: {str(e)}",
                "detail": str(e),
                "source": source,
            },
        )

    # ── 从 DB 实时重建 bracket_payload（确保反映最新真实比分）──
    # 静态快照中的 bracket 可能过时（如决赛已踢完但快照仍是预测状态）
    try:
        from app.services.fixture_repository import FixtureRepository
        from app.tools.bracket_tool import BracketTool
        from app.tools.match_predictor_tool import MatchPredictorTool

        repo = FixtureRepository()
        db_knockout = repo.get_knockout_fixtures()

        if db_knockout:
            logger.info("[API] 从 DB 读取 %d 场淘汰赛 fixtures，重建 bracket_payload", len(db_knockout))
            bracket_tool = BracketTool(seed=42)
            predictor = MatchPredictorTool(seed=42)
            team_features = data.get("team_features", {})
            # 空 bracket 表示所有淘汰赛数据都从 DB 读取
            empty_bracket = {"group_results": [], "third_places_ranking": []}
            rebuilt = bracket_tool.predict_knockout_stage(
                empty_bracket, team_features, predictor
            )
            rebuilt_bp = rebuilt.get("bracket_payload", {})
            if rebuilt_bp:
                data["bracket_payload"] = rebuilt_bp
                # 如果重建后的决赛已结束，同步更新顶层 champion
                rebuilt_knockout = rebuilt.get("knockout_predictions", [])
                final_matches = [m for m in rebuilt_knockout if m.get("round") == "final"]
                if final_matches:
                    fm = final_matches[0]
                    f_status = (fm.get("status") or "").upper()
                    if f_status in ("FT", "AET", "PEN", "FINISHED"):
                        f_home_score = fm.get("predicted_home_score") or fm.get("home_score")
                        f_away_score = fm.get("predicted_away_score") or fm.get("away_score")
                        if f_home_score is not None and f_away_score is not None:
                            if f_home_score > f_away_score:
                                real_champion = fm["home_team"]
                            elif f_away_score > f_home_score:
                                real_champion = fm["away_team"]
                            else:
                                real_champion = fm.get("winner", "Unknown")
                            data["champion"] = real_champion
                            data["predicted_champion"] = real_champion
                            logger.info("[API] 决赛已结束，更新冠军为: %s (%d-%d)",
                                        real_champion, f_home_score, f_away_score)
    except Exception as e:
        logger.warning("[API] bracket 重建失败，使用快照中的 bracket: %s", e)

    # ── 淘汰赛路径标准化 + 一致性校验 ──
    # normalize 仅作用于返回副本，不修改 DB/JSON 源数据
    bp = data.get("bracket_payload", {})
    if bp:
        try:
            from copy import deepcopy
            from app.tools.bracket_tool import normalize_bracket_payload, validate_bracket_integrity
            bp_copy = deepcopy(bp)
            bp_normalized = normalize_bracket_payload(bp_copy)
            bracket_errors = validate_bracket_integrity(bp_normalized)
            if bracket_errors:
                logger.error("[API] final-result bracket_integrity 校验失败 (source=%s, %d 个问题): %s",
                             source, len(bracket_errors), bracket_errors[:3])
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "bracket_error",
                        "message": f"淘汰赛数据一致性校验失败: {bracket_errors[0]}",
                        "bracket_integrity_errors": bracket_errors,
                        "source": source,
                    },
                )
            # normalize 通过 → 使用标准化后的 bracket
            data["bracket_payload"] = bp_normalized
        except Exception as e:
            logger.warning("[API] bracket_integrity 校验异常: %s", e)

    # 标注数据来源（便于调试）
    data["_source"] = source
    return data
