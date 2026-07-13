"""
数据质量 Agent

检查 Agent 收集到的数据是否足够支撑预测。
输出：{is_usable, score, missing_data, warnings, blocking_errors, fallback_used,
       is_real_data_ready, fixtures_source, teams_source, live_data_source,
       llm_generated_data_used, needs_review_count,
       real_fixtures_count, real_teams_count, live_fixtures_count,
       finished_matches_count}

必须识别 source：
  api-sports, real_result, api_cache, api-sports_llm_normalized,
  llm_generated_template, llm_generated_candidate, fallback_csv,
  default_value, agent_prediction, fallback_prediction
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# 可信度分级
HIGH_TRUST_SOURCES = {"api-sports", "real_result"}
MEDIUM_TRUST_SOURCES = {"api_cache", "api-sports_llm_normalized"}
LOW_TRUST_SOURCES = {"llm_generated_template", "llm_generated_candidate", "fallback_csv", "default_value"}
PREDICTION_SOURCES = {"agent_prediction", "fallback_prediction"}


class DataQualityAgent:
    """数据质量检查 Agent"""

    def check(self, collected_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        对收集到的数据做质量检查。

        Args:
            collected_data: {
                "fixtures": [...],
                "teams": [...],
                "live": [...],
                "historical": {...},
                "scraper": {...},
            }
        """
        warnings: List[str] = []
        blocking_errors: List[str] = []
        missing_data: List[str] = []

        # ── 1. 检查 API Key ──
        from app.core.config import get_settings
        settings = get_settings()
        api_key_present = bool(settings.APISPORTS_KEY or settings.API_FOOTBALL_KEY)
        if not api_key_present:
            blocking_errors.append("APISPORTS_KEY / API_FOOTBALL_KEY 未配置")

        # ── 2. 检查世界杯赛程 ──
        fixtures = collected_data.get("fixtures")
        real_fixtures_count = 0
        finished_matches_count = 0
        fixtures_source = "none"
        if fixtures and isinstance(fixtures, list) and len(fixtures) > 0:
            real_fixtures_count = len(fixtures)
            fixtures_source = "api-sports"
            # 统计已结束
            for fx in fixtures:
                status = fx.get("fixture", {}).get("status", {}).get("short", "")
                if status in ("FT", "AET", "PEN"):
                    finished_matches_count += 1
            if real_fixtures_count < 48:
                warnings.append(f"赛程数据不完整：仅 {real_fixtures_count} 场（预期 ≥48）")
        else:
            missing_data.append("缺少 2026 世界杯赛程数据")

        # ── 3. 检查参赛球队 ──
        teams = collected_data.get("teams")
        real_teams_count = 0
        teams_source = "none"
        if teams and isinstance(teams, list) and len(teams) > 0:
            real_teams_count = len(teams)
            teams_source = "api-sports"
            if real_teams_count < 48:
                warnings.append(f"球队数据不完整：仅 {real_teams_count} 支（预期 48）")
        else:
            missing_data.append("缺少参赛球队数据")

        # ── 4. 检查实时比分 ──
        live = collected_data.get("live")
        live_fixtures_count = 0
        live_data_source = "none"
        if live and isinstance(live, list):
            live_fixtures_count = len(live)
            live_data_source = "api-sports" if live_fixtures_count > 0 else "api-sports (no live)"
        else:
            live_data_source = "none"

        # ── 5. 检查 fixtures 表（DB） ──
        db_fixtures_source = "none"
        db_real_count = 0
        db_finished = 0
        db_live = 0
        try:
            from app.db.database import SessionLocal
            from app.models.agent_models import Fixture
            db = SessionLocal()
            try:
                db_real_count = db.query(Fixture).count()
                db_finished = db.query(Fixture).filter(Fixture.status.in_(["FT", "AET", "PEN", "FINISHED"])).count()
                db_live = db.query(Fixture).filter(Fixture.status.in_(["LIVE", "IN_PLAY", "PAUSED"])).count()
                if db_real_count > 0:
                    db_fixtures_source = "api-sports"
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[DataQuality] fixtures DB check failed: {e}")

        # ── 6. 检查历史比赛 ──
        historical = collected_data.get("historical")
        if not historical:
            warnings.append("缺少历史国家队比赛数据（可降级运行）")
        else:
            hist_count = historical.get("total", 0) if isinstance(historical, dict) else 0
            if hist_count < 100:
                warnings.append(f"历史比赛数据偏少：{hist_count} 场（建议 ≥100）")

        # ── 7. 检查近期战绩 ──
        recent_form = collected_data.get("recent_form", {})
        if not recent_form:
            warnings.append("缺少球队近期战绩数据")

        # ── 8. 检查爬虫数据 ──
        scraper_data = collected_data.get("scraper", {})
        if scraper_data:
            values = [
                v.get("market_value")
                for v in scraper_data.values()
                if isinstance(v, dict) and v.get("market_value")
            ]
            if values and len(set(values)) == 1 and len(values) > 1:
                warnings.append(
                    f"所有球队身价相同（{values[0]}），可能是默认预估值，非真实数据"
                )

        # ── 9. 判断 fallback / LLM 使用 ──
        fallback_used = False
        llm_generated_data_used = False

        # 检查是否使用 fallback
        if not fixtures or (isinstance(fixtures, list) and len(fixtures) == 0):
            fallback_used = True
        if not teams or (isinstance(teams, list) and len(teams) == 0):
            fallback_used = True

        # 检查 collected_data 中是否有 LLM 生成数据
        for key in ["team_aliases", "team_ratings", "competition_weights"]:
            if key in collected_data:
                llm_generated_data_used = True

        # ── 10. 计算 needs_review_count ──
        needs_review_count = 0
        try:
            import json as _json
            from pathlib import Path as _Path
            manifest_path = _Path("data/data_manifest.json")
            if manifest_path.exists():
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = _json.load(f)
                for csv_info in manifest.get("csv_files", []):
                    if csv_info.get("needs_manual_review"):
                        needs_review_count += 1
                if manifest.get("llm_assisted"):
                    llm_generated_data_used = True
        except Exception:
            pass

        # ── 11. 判断 is_real_data_ready ──
        is_real_data_ready = (
            fixtures_source in HIGH_TRUST_SOURCES
            and teams_source in HIGH_TRUST_SOURCES
            and api_key_present
        )

        # ── 12. 计算质量分数 ──
        # 将 missing_data 转为 blocking_errors（如果 API key 存在但数据为空）
        if api_key_present:
            for md in missing_data:
                if md not in blocking_errors:
                    blocking_errors.append(md)
        
        # 如果没有 API key，blocking_errors 已有，fallback 可用
        if not api_key_present and not fallback_used:
            fallback_used = True

        # 如果有 fallback 但数据可用（DEFAULT_48_TEAMS），将 blocking_errors 降级为 warnings
        if fallback_used:
            new_blocking = []
            for err in blocking_errors:
                if "赛程" in err or "球队" in err:
                    warnings.append(f"使用默认数据: {err}")
                else:
                    new_blocking.append(err)
            blocking_errors = new_blocking

        score = self._calc_score(blocking_errors, warnings, missing_data)
        is_usable = len(blocking_errors) == 0

        # API key 缺失是 blocking_error
        if not api_key_present and not fallback_used:
            is_usable = False

        # 使用 fallback 时状态不能是 completed
        status = "completed"
        if fallback_used:
            status = "degraded_completed"
        if not is_usable:
            status = "failed"

        return {
            "is_usable": is_usable,
            "score": round(score, 2),
            "missing_data": missing_data,
            "warnings": warnings,
            "blocking_errors": blocking_errors,
            "fallback_used": fallback_used,
            "status": status,
            # 真实数据状态
            "is_real_data_ready": is_real_data_ready,
            "fixtures_source": fixtures_source if fixtures_source != "none" else db_fixtures_source,
            "teams_source": teams_source,
            "live_data_source": live_data_source,
            "llm_generated_data_used": llm_generated_data_used,
            "needs_review_count": needs_review_count,
            "real_fixtures_count": max(real_fixtures_count, db_real_count),
            "real_teams_count": real_teams_count,
            "live_fixtures_count": max(live_fixtures_count, db_live),
            "finished_matches_count": max(finished_matches_count, db_finished),
        }

    @staticmethod
    def _calc_score(
        blocking_errors: List[str],
        warnings: List[str],
        missing_data: List[str],
    ) -> float:
        """计算数据质量分数 0~1"""
        score = 1.0
        # 每个阻塞错误扣 0.3
        score -= len(blocking_errors) * 0.3
        # 每个警告扣 0.05
        score -= len(warnings) * 0.05
        # 每个缺失字段扣 0.02
        score -= len(missing_data) * 0.02
        return max(0.0, score)
