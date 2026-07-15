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
    同步更新 champion、champion_probability、top5、top_candidates、explanation、run_id。
    保存前执行 _validate_prediction_snapshot 一致性校验。
    """
    from copy import deepcopy
    import hashlib

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

    # ══════════════════════════════════════════════════════
    # Step 1: 强制 champion / champion_probability 来自 top5[0]
    # ══════════════════════════════════════════════════════
    if top5:
        top_champ = top5[0].get("team", top_champ)
        top1_prob = top5[0].get("probability", 0)
        champ_prob_01 = top1_prob if top1_prob <= 1 else top1_prob / 100.0
        champ_prob_01 = round(champ_prob_01, 4)
    else:
        champ_prob_01 = round(top_prob, 4) if top_prob <= 1 else round(top_prob / 100, 4)

    # ══════════════════════════════════════════════════════
    # Step 2: 生成 run_id
    # ══════════════════════════════════════════════════════
    run_ts = datetime.utcnow().isoformat()
    run_id_raw = f"{top_champ}:{champ_prob_01}:{run_ts}"
    run_id = "run_" + hashlib.md5(run_id_raw.encode()).hexdigest()[:12]

    # ══════════════════════════════════════════════════════
    # Step 3: 同步更新所有预测字段（top_candidates = deepcopy(top5)）
    # ══════════════════════════════════════════════════════
    existing["champion"] = top_champ
    existing["predicted_champion"] = top_champ
    existing["champion_probability"] = champ_prob_01
    existing["top5"] = top5
    existing["top_candidates"] = deepcopy(top5)
    existing["surviving_teams"] = surviving_teams
    existing["stage"] = stage
    existing["simulation_count"] = sim_result.get("n_simulations", 10000)
    existing["generated_at"] = run_ts
    existing["run_id"] = run_id
    existing["status"] = "completed"

    # ══════════════════════════════════════════════════════
    # Step 4: 重新生成 explanation（使用最终 champion / probability / run_id）
    # ══════════════════════════════════════════════════════
    try:
        _regenerate_explanation(existing, surviving_teams, stage,
                                champion=top_champ,
                                champion_probability=champ_prob_01,
                                run_id=run_id)
    except Exception as e:
        logger.warning("[FullRefresh] 重新生成解释失败: %s", e)

    # ══════════════════════════════════════════════════════
    # Step 5: 强制覆盖 explanation 绑定字段（双保险）
    # ══════════════════════════════════════════════════════
    explanation_data = existing.get("explanation", {})
    if isinstance(explanation_data, dict):
        explanation_data["champion"] = top_champ
        explanation_data["champion_probability"] = champ_prob_01
        explanation_data["probability"] = round(champ_prob_01 * 100, 2)
        explanation_data["run_id"] = run_id

    # ══════════════════════════════════════════════════════
    # Step 6: 一致性校验（保存前）
    # ══════════════════════════════════════════════════════
    try:
        from app.agents.worldcup_agent import _validate_prediction_snapshot
        _validate_prediction_snapshot(existing)
        logger.info("[FullRefresh] _validate_prediction_snapshot 通过")
    except AssertionError as e:
        logger.error("[FullRefresh] 一致性校验失败，拒绝保存: %s", e)
        raise RuntimeError(f"预测数据一致性校验失败: {e}")

    # ── Step 6b: 标准化 + 淘汰赛路径一致性校验 ──
    bp_for_validation = existing.get("bracket_payload", {})
    bracket_errors = []
    if bp_for_validation:
        try:
            from app.tools.bracket_tool import normalize_bracket_payload, validate_bracket_integrity
            existing["bracket_payload"] = normalize_bracket_payload(bp_for_validation)
            bracket_errors = validate_bracket_integrity(existing["bracket_payload"])
            if bracket_errors:
                logger.error("[FullRefresh] bracket_integrity 校验失败（%d 个问题），拒绝保存: %s",
                             len(bracket_errors), bracket_errors[:3])
            else:
                logger.info("[FullRefresh] bracket_integrity 校验通过 ✓")
        except Exception as e:
            logger.warning("[FullRefresh] bracket_integrity 校验异常: %s", e)

    # ══════════════════════════════════════════════════════
    # Step 7: 保存（校验通过才写入）
    # ══════════════════════════════════════════════════════
    if bracket_errors:
        # ── 校验失败：不覆盖 JSON，不写 DB，保留上一份有效快照 ──
        existing["status"] = "bracket_error"
        existing["bracket_integrity_errors"] = bracket_errors

        # 写入诊断文件
        diag_path = DATA_DIR / "bracket_error_diagnostic.json"
        try:
            with open(diag_path, "w", encoding="utf-8") as df:
                json.dump({
                    "run_id": run_id,
                    "generated_at": run_ts,
                    "bracket_integrity_errors": bracket_errors,
                    "champion": top_champ,
                    "champion_probability": champ_prob_01,
                }, df, ensure_ascii=False, indent=2)
        except Exception:
            pass

        logger.error("[FullRefresh] bracket 校验失败，已跳过 JSON 和 DB 保存。上一份有效快照保持不变。")
        raise RuntimeError(f"bracket_integrity 校验失败: {bracket_errors[:3]}")

    # ── 校验通过：正常保存 ──
    existing["status"] = "completed"
    from app.agents.worldcup_agent import atomic_write_json
    atomic_write_json(out_path, existing)
    logger.info("[FullRefresh] final_agent_result.json 已写入: %s (champion=%s, prob=%.4f, run_id=%s)",
                out_path.resolve(), top_champ, champ_prob_01, run_id)

    # ── DB 持久化 ──
    try:
        from app.services.prediction_snapshot_service import save_prediction_snapshot
        save_prediction_snapshot(existing)
    except Exception as e:
        logger.warning("[FullRefresh] DB snapshot 保存失败: %s", e)


def _regenerate_explanation(result: Dict, surviving_teams: list, stage: str,
                            champion: str = "", champion_probability: float = 0,
                            run_id: str = ""):
    """重新生成冠军解释，确保与最终 snapshot 一致。

    使用 _generate_champion_explanation 的简化逻辑：
    从 simulation_distribution.json 读取 stage 信息，
    但 champion / probability / run_id 必须由调用方传入。
    """
    if not champion:
        logger.warning("[FullRefresh] _regenerate_explanation: champion 为空，跳过")
        return

    prob_pct = round(champion_probability * 100, 2)

    # 检查环境变量：定时刷新是否启用 LLM
    import os
    enable_refresh_llm = os.environ.get("ENABLE_REFRESH_LLM", "false").lower() == "true"

    # 尝试使用 ChampionExplanationService 生成内容
    content = ""
    source = "fallback"
    fallback_reason = ""
    try:
        from app.services.champion_explanation_service import ChampionExplanationService

        sim_dist_path = DATA_DIR / "simulation_distribution.json"
        if sim_dist_path.exists():
            with open(sim_dist_path, encoding="utf-8") as f:
                sim_data = json.load(f)

            service = ChampionExplanationService(use_llm=enable_refresh_llm)
            explanation = service.generate(
                champion=champion,
                champion_probability=champion_probability,
                top_contenders=[],
                team_features={},
                knockout_predictions=[],
                simulation_data=sim_data,
                surviving_teams=surviving_teams,
                stage=stage,
            )
            if explanation and explanation.get("content"):
                content = explanation["content"]
                source = explanation.get("source", "fallback")
                if source == "fallback":
                    fallback_reason = explanation.get("fallback_reason", "service_fallback")
            else:
                fallback_reason = "service_empty_response"
        else:
            fallback_reason = "simulation_distribution_not_found"
    except Exception as e:
        err_type = type(e).__name__
        err_msg = str(e)[:100]
        fallback_reason = f"service_error: {err_type}: {err_msg}"
        logger.warning("[FullRefresh] ChampionExplanationService 不可用: %s", e)

    if not enable_refresh_llm and not fallback_reason:
        fallback_reason = "llm_disabled_by_env(ENABLE_REFRESH_LLM=false)"

    # Fallback 内容
    if not content:
        stage_desc = ""
        if stage == "semi_finals" and surviving_teams:
            teams_text = "、".join(surviving_teams)
            stage_desc = f"当前赛事已进入四强阶段，系统只在{teams_text}四支仍有夺冠可能的球队中进行模拟分析。\n\n"
        elif stage == "final" and surviving_teams:
            teams_text = "、".join(surviving_teams)
            stage_desc = f"当前赛事已进入决赛阶段，{teams_text}两支球队争夺大力神杯。\n\n"

        content = (
            f"## 为什么预测 {champion} 夺冠？\n\n"
            f"{stage_desc}"
            f"根据已结束比赛结果和后续对阵形势，{champion} 展现出较强的夺冠实力，"
            f"系统给出 {prob_pct}% 的夺冠概率。"
            f"球队在攻防两端表现均衡，是当前最有可能捧起大力神杯的队伍。\n"
            f"\n### 核心优势\n- 综合实力均衡，各位置无明显短板。\n"
            f"\n### 关键因素\n- {champion}在综合评估中表现突出，是当前最具竞争力的球队。\n"
            f"\n### AI综合判断\n\n"
            f"综合各方面分析，{champion} 以 {prob_pct}% 的夺冠概率领跑群雄。"
            f"球队整体实力突出，晋级形势有利，是最有可能夺冠的球队。\n"
        )

    result["explanation"] = {
        "title": f"为什么预测 {champion} 夺冠？",
        "content": content,
        "key_reasons": [],
        "source": source,
        "fallback_reason": fallback_reason if source != "llm" else "",
        "probability": prob_pct,
        "champion": champion,
        "champion_probability": champion_probability,
        "run_id": run_id,
    }
    logger.info("[FullRefresh] 冠军解释已重新生成: champion=%s, prob=%.2f%%", champion, prob_pct)
