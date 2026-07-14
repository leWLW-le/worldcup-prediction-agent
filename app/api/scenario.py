"""
冠军路径沙盘 API

POST /scenario/simulate       — 运行沙盘推演
GET  /scenario/latest          — 获取最新沙盘结果（含过期检测）
GET  /scenario/pending-matches — 获取可选的未结束比赛列表（阶段感知）
GET  /scenario/stage-info      — 获取当前赛事阶段信息
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/scenario", tags=["scenario"])


class ScenarioSimulateRequest(BaseModel):
    match_id: str
    forced_winner: str
    simulation_count: int = 3000


@router.get("/stage-info")
def get_stage_info():
    """
    获取当前赛事阶段信息。
    包含 stage、surviving_teams、sandbox_enabled 等。
    """
    from app.db.database import SessionLocal
    from app.services.tournament_state_service import get_current_tournament_stage

    db = SessionLocal()
    try:
        stage_info = get_current_tournament_stage(db)
        return {"success": True, **stage_info}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        db.close()


@router.post("/simulate")
def simulate_scenario(request: ScenarioSimulateRequest):
    """
    运行沙盘推演。

    用户选择一场未结束比赛并指定假设晋级队，
    系统在假设条件下重新模拟后续比赛，
    输出新的冠军概率、可能决赛对阵和 AI 解释。

    如果当前阶段沙盘已关闭（决赛/已结束），返回 disabled 状态。
    """
    from app.services.scenario_simulation_service import run_scenario_simulation

    result = run_scenario_simulation(
        match_id=request.match_id,
        forced_winner=request.forced_winner,
        simulation_count=request.simulation_count,
    )
    return result


@router.get("/latest")
def get_latest_scenario():
    """
    获取最新的沙盘推演结果。
    如果沙盘结果已过期（阶段已变化），返回 is_stale=true 和提示信息。
    """
    from app.services.scenario_simulation_service import load_latest_scenario

    return load_latest_scenario()


@router.get("/pending-matches")
def get_pending_matches():
    """
    获取当前阶段未结束的淘汰赛比赛列表（阶段感知）。
    如果沙盘已关闭（决赛/已结束），返回空列表和原因。
    同时返回 stage_info 供前端使用。
    """
    from app.db.database import SessionLocal
    from app.services.tournament_state_service import get_current_tournament_stage

    db = SessionLocal()
    try:
        stage_info = get_current_tournament_stage(db)
        return {
            "success": True,
            "matches": stage_info.get("pending_scenario_matches", []),
            "stage": stage_info["stage"],
            "stage_label": stage_info["stage_label"],
            "sandbox_enabled": stage_info["sandbox_enabled"],
            "sandbox_message": stage_info.get("sandbox_message", ""),
        }
    except Exception as e:
        return {"success": False, "error": str(e), "matches": [],
                "sandbox_enabled": False, "sandbox_message": str(e)}
    finally:
        db.close()
