"""
Agent FastAPI 接口

POST /api/v1/agent/run-prediction  - 一键运行完整预测（支持 mode 参数）
POST /api/v1/agent/refresh-data    - 仅刷新 API 数据
GET  /api/v1/agent/status          - 最近一次 Agent 运行状态
GET  /api/v1/agent/latest-result   - 获取最近一次预测结果
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])

# ── 全局状态（最近一次运行结果） ──
_last_run_result: Optional[Dict[str, Any]] = None
_last_run_time: Optional[str] = None


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
    获取 data/final_agent_result.json — 前端展示的唯一数据源。
    如果文件不存在，返回 404 提示。
    """
    from pathlib import Path
    result_path = Path(__file__).parent.parent.parent / "data" / "final_agent_result.json"
    resolved = result_path.resolve()
    logger.info("[API] 读取路径: %s (exists=%s)", resolved, result_path.exists())
    if not result_path.exists():
        return {
            "status": "no_result",
            "message": "尚未生成预测结果，请先运行 POST /api/v1/agent/run-prediction",
        }
    try:
        with open(result_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to read final_agent_result.json: %s", e)
        return {"status": "error", "message": str(e)}
