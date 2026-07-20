"""
世界杯真实数据同步服务

从 API-Sports 拉取赛程和实时比分，upsert 到 fixtures 表。
fixtures 表只保存真实比赛数据，预测结果写入 predicted_matches 表。
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db.database import SessionLocal
from app.models.agent_models import Fixture, compute_canonical_pair
from app.tools.api_sports_tool import APISportsTool

logger = logging.getLogger(__name__)

# 状态映射规则
LIVE_STATUSES = {"1H", "HT", "2H", "ET", "P", "BT", "LIVE"}
FINISHED_STATUSES = {"FT", "AET", "PEN"}
NOT_STARTED_STATUSES = {"NS", "TBD"}

# source_level 优先级（用于 upsert 决策）
_SOURCE_LEVEL_PRIORITY = {
    "external_real": 3,
    "verified_cache": 2,
    "manual_verified": 2,
    "unverified_candidate": 1,
    "unavailable": 0,
}


def _infer_stage_from_round(round_name: str) -> str:
    """从 API-Football 的 round 字段推断比赛阶段"""
    if not round_name:
        return "group_stage"
    round_lower = round_name.lower()
    if "group" in round_lower:
        return "group_stage"
    if "32" in round_lower or "round of 32" in round_lower:
        return "round_of_32"
    if "16" in round_lower or "round of 16" in round_lower:
        return "round_of_16"
    if "quarter" in round_lower or "1/4" in round_lower:
        return "quarter_finals"
    if "semi" in round_lower or "1/2" in round_lower:
        return "semi_finals"
    if "final" in round_lower:
        return "final"
    return "group_stage"


def parse_api_fixture(raw: Dict[str, Any], season: int = 2026) -> Optional[Dict[str, Any]]:
    """将 API-Sports 原始 fixture 数据解析为 Fixture 模型字段。

    只返回 Fixture 模型上实际存在的字段，避免 setattr / **kwargs 报错。
    """
    try:
        fixture_info = raw.get("fixture", {})
        teams = raw.get("teams", {})
        goals = raw.get("goals", {})
        league = raw.get("league", {})
        status = fixture_info.get("status", {})

        home = teams.get("home", {}) or {}
        away = teams.get("away", {}) or {}

        status_short = status.get("short", "NS")

        # 判断比赛状态
        is_finished = status_short in FINISHED_STATUSES

        # source / source_level 规则
        if is_finished:
            source = "real_result"
            source_level = "external_real"
        else:
            source = "api-sports"
            source_level = "external_real"

        # 比分
        home_score = goals.get("home")
        away_score = goals.get("away")

        # 胜者
        winner = None
        if home.get("winner") is True:
            winner = home.get("name")
        elif away.get("winner") is True:
            winner = away.get("name")

        # 比赛日期
        match_date_str = fixture_info.get("date")
        match_date = None
        if match_date_str:
            try:
                match_date = datetime.fromisoformat(match_date_str.replace("Z", "+00:00"))
            except Exception:
                match_date = None

        # 阶段推断
        round_name = league.get("round", "")
        stage = _infer_stage_from_round(round_name)

        # 球队名称
        home_team = home.get("name", "Unknown") or "Unknown"
        away_team = away.get("name", "Unknown") or "Unknown"

        # 规范化配对
        canonical_pair = compute_canonical_pair(home_team, away_team)

        # fixture_id：使用 api_fixture_id 生成带前缀的唯一 ID
        api_id = fixture_info.get("id")
        fixture_id = f"af_{api_id}" if api_id else None

        return {
            "fixture_id": fixture_id,
            "api_fixture_id": str(api_id) if api_id else None,
            "home_team": home_team,
            "away_team": away_team,
            "home_team_id": str(home["id"]) if home.get("id") else None,
            "away_team_id": str(away["id"]) if away.get("id") else None,
            "match_date": match_date,
            "stage": stage,
            "status": status_short,
            "home_score": home_score,
            "away_score": away_score,
            "winner": winner,
            "source": source,
            "source_level": source_level,
            "is_verified": is_finished,
            "needs_review": False,
            "confidence_level": "medium" if not is_finished else "high",
            "evidence_count": 1,
            "evidence_sources": json.dumps(["api_football"], ensure_ascii=False),
            "canonical_pair": canonical_pair,
            "raw_payload": json.dumps(raw, ensure_ascii=False),
            "updated_at": datetime.now(timezone.utc),
        }
    except Exception as e:
        logger.error(f"[SyncService] parse_api_fixture error: {e}")
        return None


def upsert_fixture(db, fixture_data: Dict[str, Any]) -> bool:
    """将单条 fixture 数据 upsert 到 fixtures 表。

    去重逻辑：
    1. 先按 fixture_id 查找
    2. 再按逻辑键（stage + canonical_pair）查找
    3. 都不存在则插入新记录

    更新时只设置 Fixture 模型上实际存在的字段。
    """
    fixture_id = fixture_data.get("fixture_id")
    api_id = fixture_data.get("api_fixture_id")
    if not fixture_id and not api_id:
        return False

    # ── 查找已有记录 fixture_id ──
    existing = None
    if fixture_id:
        existing = db.query(Fixture).filter(Fixture.fixture_id == fixture_id).first()

    # ── 按逻辑键查找（stage + canonical_pair）──
    if not existing and fixture_data.get("stage") and fixture_data.get("canonical_pair"):
        existing = db.query(Fixture).filter(
            Fixture.stage == fixture_data["stage"],
            Fixture.canonical_pair == fixture_data["canonical_pair"],
        ).first()

    # ── Fixture 模型上实际存在的字段白名单 ──
    _FIXTURE_FIELDS = {
        "fixture_id", "api_fixture_id",
        "home_team", "away_team", "home_team_id", "away_team_id",
        "match_date", "stage", "status",
        "home_score", "away_score", "winner",
        "source", "source_level", "is_verified", "needs_review",
        "confidence_level", "evidence_count", "evidence_sources",
        "canonical_pair", "raw_payload", "fetched_at", "updated_at",
    }

    if existing:
        # 更新已有记录（只更新白名单字段）
        # 受信任的外部源列表：这些 source 值不应被覆盖
        _TRUSTED_SOURCES = {"football_data", "real_result", "api_football"}
        for key, value in fixture_data.items():
            if key in _FIXTURE_FIELDS and key not in ("fixture_id", "created_at", "fetched_at"):
                if value is not None:
                    # 防止 source 字段被降级覆盖（如 football_data → real_result）
                    if key == "source" and existing.source in _TRUSTED_SOURCES:
                        continue
                    setattr(existing, key, value)
        existing.updated_at = datetime.now(timezone.utc)
    else:
        # 插入新记录（只传白名单字段）
        clean_data = {k: v for k, v in fixture_data.items() if k in _FIXTURE_FIELDS}
        if not clean_data.get("fixture_id"):
            # 没有 fixture_id 则跳过
            return False
        fixture = Fixture(**clean_data)
        db.add(fixture)

    return True


def sync_worldcup_fixtures(season: int = 2026) -> Dict[str, Any]:
    """从 API-Sports 拉取世界杯赛程并同步到 fixtures 表"""
    api = APISportsTool()
    result = api.get_worldcup_fixtures(season)

    if not result["success"]:
        return {
            "success": False,
            "fixtures_fetched": 0,
            "fixtures_upserted": 0,
            "error": result.get("error"),
        }

    raw_fixtures = result.get("data", [])
    upserted = 0

    db = SessionLocal()
    try:
        for raw in raw_fixtures:
            parsed = parse_api_fixture(raw, season=season)
            if parsed:
                if upsert_fixture(db, parsed):
                    upserted += 1
        db.commit()
        logger.info(f"[SyncService] fixtures 同步完成: {upserted}/{len(raw_fixtures)}")
    except Exception as e:
        logger.error(f"[SyncService] DB commit error: {e}")
        db.rollback()
        return {
            "success": False,
            "fixtures_fetched": len(raw_fixtures),
            "fixtures_upserted": upserted,
            "error": str(e),
        }
    finally:
        db.close()

    return {
        "success": True,
        "fixtures_fetched": len(raw_fixtures),
        "fixtures_upserted": upserted,
        "error": None,
    }


def sync_live_fixtures() -> Dict[str, Any]:
    """从 API-Sports 拉取实时比分并同步到 fixtures 表"""
    api = APISportsTool()
    result = api.get_live_fixtures()

    if not result["success"]:
        return {
            "success": False,
            "live_fetched": 0,
            "live_upserted": 0,
            "error": result.get("error"),
        }

    raw_fixtures = result.get("data", [])
    upserted = 0

    db = SessionLocal()
    try:
        for raw in raw_fixtures:
            parsed = parse_api_fixture(raw)
            if parsed:
                if upsert_fixture(db, parsed):
                    upserted += 1
        db.commit()
        logger.info(f"[SyncService] live 同步完成: {upserted}/{len(raw_fixtures)}")
    except Exception as e:
        logger.error(f"[SyncService] DB commit error: {e}")
        db.rollback()
        return {
            "success": False,
            "live_fetched": len(raw_fixtures),
            "live_upserted": upserted,
            "error": str(e),
        }
    finally:
        db.close()

    return {
        "success": True,
        "live_fetched": len(raw_fixtures),
        "live_upserted": upserted,
        "error": None,
    }


def get_fixtures_summary() -> Dict[str, Any]:
    """获取 fixtures 表摘要统计"""
    db = SessionLocal()
    try:
        total = db.query(Fixture).count()
        finished = db.query(Fixture).filter(Fixture.status.in_(["FT", "AET", "PEN", "FINISHED"])).count()
        live = db.query(Fixture).filter(Fixture.status.in_(["LIVE", "IN_PLAY", "PAUSED"])).count()
        real_result = db.query(Fixture).filter(Fixture.source == "real_result").count()
        api_sports = db.query(Fixture).filter(Fixture.source == "api-sports").count()
        return {
            "total_fixtures": total,
            "finished_matches": finished,
            "live_matches": live,
            "real_result_count": real_result,
            "api_sports_count": api_sports,
        }
    finally:
        db.close()
