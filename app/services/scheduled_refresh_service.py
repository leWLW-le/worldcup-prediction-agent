"""
全量刷新服务 — 完整刷新流水线

流程:
    1. refresh_fixtures()        — 从外部 API 拉取最新赛程/比分
    2. get_surviving_teams()     — 从 fixtures 表识别仍有夺冠可能的球队
    3. simulate_tournament()     — 只在 surviving_teams 中做 Monte Carlo 模拟
    4. _update_final_result()    — 更新 final_agent_result.json

可由以下途径触发:
    - Dashboard "刷新数据" 按钮 (POST /api/v1/data/full-refresh)
    - APScheduler 每日定时任务 (06:00)
    - 手动调用 scripts/run_full_refresh.py
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def run_full_refresh_pipeline(
    season: int = 2026,
    n_simulations: int = 10000,
) -> Dict[str, Any]:
    """
    执行完整刷新流水线。

    Returns:
        包含每一步结果的字典
    """
    result = {
        "success": False,
        "steps": {},
        "started_at": datetime.utcnow().isoformat(),
    }

    # ── Step 1: 刷新 fixtures ──
    try:
        from app.services.data_source_manager import DataSourceManager

        mgr = DataSourceManager()
        fixture_result = mgr.refresh_fixtures(season=season)
        result["steps"]["refresh_fixtures"] = {
            "success": True,
            "detail": fixture_result,
        }
        logger.info("[FullRefresh] Step 1 完成: fixtures 刷新成功")
    except Exception as e:
        logger.warning("[FullRefresh] Step 1 失败: %s — 继续使用已有 fixtures", e)
        result["steps"]["refresh_fixtures"] = {
            "success": False,
            "error": str(e),
        }

    # ── Step 2: 识别 surviving_teams ──
    try:
        from app.db.database import SessionLocal
        from app.services.tournament_state_service import get_surviving_teams_from_fixtures

        db = SessionLocal()
        try:
            state = get_surviving_teams_from_fixtures(db, season=season)
            surviving_teams = state["surviving_teams"]
            stage = state["stage"]
            result["steps"]["identify_surviving"] = {
                "success": True,
                "stage": stage,
                "surviving_teams": surviving_teams,
                "eliminated_count": len(state.get("eliminated_teams", [])),
            }
            logger.info(
                "[FullRefresh] Step 2 完成: stage=%s, surviving=%s",
                stage, surviving_teams,
            )
        finally:
            db.close()
    except Exception as e:
        logger.error("[FullRefresh] Step 2 失败: %s", e)
        result["steps"]["identify_surviving"] = {
            "success": False,
            "error": str(e),
        }
        result["finished_at"] = datetime.utcnow().isoformat()
        return result

    if not surviving_teams:
        logger.error("[FullRefresh] 没有找到 surviving_teams，流水线终止")
        result["steps"]["simulation"] = {"success": False, "error": "no surviving teams"}
        result["finished_at"] = datetime.utcnow().isoformat()
        return result

    # ── Step 3: Monte Carlo 模拟 ──
    try:
        from scripts.run_champion_simulation import simulate_tournament

        sim_result = simulate_tournament(
            n_simulations=n_simulations,
            surviving_teams=surviving_teams,
        )
        if sim_result:
            result["steps"]["simulation"] = {
                "success": True,
                "n_simulations": n_simulations,
                "top_champion": sim_result.get("top_champion"),
                "top_probability": sim_result.get("top_probability"),
            }
            logger.info(
                "[FullRefresh] Step 3 完成: top=%s (%.1f%%)",
                sim_result.get("top_champion"),
                (sim_result.get("top_probability") or 0) * 100,
            )
        else:
            result["steps"]["simulation"] = {
                "success": False,
                "error": "simulate_tournament returned None",
            }
            result["finished_at"] = datetime.utcnow().isoformat()
            return result
    except Exception as e:
        logger.error("[FullRefresh] Step 3 失败: %s", e)
        result["steps"]["simulation"] = {"success": False, "error": str(e)}
        result["finished_at"] = datetime.utcnow().isoformat()
        return result

    # ── Step 4: 更新 final_agent_result.json ──
    try:
        _update_final_result(sim_result, surviving_teams, stage)
        result["steps"]["update_result"] = {"success": True}
        logger.info("[FullRefresh] Step 4 完成: final_agent_result.json 已更新")
    except Exception as e:
        logger.error("[FullRefresh] Step 4 失败: %s", e)
        result["steps"]["update_result"] = {"success": False, "error": str(e)}
        result["finished_at"] = datetime.utcnow().isoformat()
        return result

    result["success"] = True
    result["finished_at"] = datetime.utcnow().isoformat()
    logger.info("[FullRefresh] 全量刷新流水线完成 ✓")
    return result


def _update_final_result(
    sim_result: Dict,
    surviving_teams: list,
    stage: str,
):
    """
    用最新模拟结果更新 final_agent_result.json。

    保留已有的 bracket_payload、data_status、model_status 等不变，
    只更新冠军概率、top5、surviving_teams、stage 等字段。
    """
    out_path = DATA_DIR / "final_agent_result.json"

    # 加载已有结果（如果存在）
    existing = {}
    if out_path.exists():
        try:
            with open(out_path, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass

    # 从模拟结果提取
    top5 = sim_result.get("top5", [])
    top_champ = sim_result.get("top_champion", "")
    top_prob = sim_result.get("top_probability", 0)

    # 更新字段
    existing["champion"] = top_champ
    existing["predicted_champion"] = top_champ
    existing["champion_probability"] = round(top_prob, 4) if top_prob <= 1 else round(top_prob / 100, 4)
    existing["top5"] = top5
    existing["surviving_teams"] = surviving_teams
    existing["stage"] = stage
    existing["simulation_count"] = sim_result.get("n_simulations", 10000)
    existing["generated_at"] = datetime.utcnow().isoformat()

    # 更新 explanation（如果 champion_explanation_service 可用）
    try:
        _regenerate_explanation(existing, surviving_teams, stage)
    except Exception as e:
        logger.warning("[FullRefresh] 重新生成解释失败: %s", e)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    logger.info("[FullRefresh] final_agent_result.json 已写入: %s", out_path.resolve())


def _regenerate_explanation(result: Dict, surviving_teams: list, stage: str):
    """尝试用 ChampionExplanationService 重新生成冠军解释"""
    try:
        from app.services.champion_explanation_service import ChampionExplanationService

        # 构建 simulation_data 格式
        sim_dist_path = DATA_DIR / "simulation_distribution.json"
        if not sim_dist_path.exists():
            return

        with open(sim_dist_path, encoding="utf-8") as f:
            sim_data = json.load(f)

        service = ChampionExplanationService()
        explanation = service.generate(
            simulation_data=sim_data,
            surviving_teams=surviving_teams,
            stage=stage,
        )
        if explanation:
            result["explanation"] = explanation
            logger.info("[FullRefresh] 冠军解释已重新生成")
    except Exception as e:
        logger.warning("[FullRefresh] ChampionExplanationService 不可用: %s", e)
