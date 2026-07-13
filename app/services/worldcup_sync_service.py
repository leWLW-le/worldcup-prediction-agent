"""
世界杯真实数据同步服务

从 API-Sports 拉取赛程和实时比分，upsert 到 fixtures 表。
fixtures 表只保存真实比赛数据，预测结果写入 predicted_matches 表。
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db.database import SessionLocal
from app.models.agent_models import Fixture
from app.tools.api_sports_tool import APISportsTool

logger = logging.getLogger(__name__)

# 状态映射规则
LIVE_STATUSES = {"1H", "HT", "2H", "ET", "P", "BT", "LIVE"}
FINISHED_STATUSES = {"FT", "AET", "PEN"}
NOT_STARTED_STATUSES = {"NS", "TBD"}


def parse_api_fixture(raw: Dict[str, Any], season: int = 2026) -> Optional[Dict[str, Any]]:
    """将 API-Sports 原始 fixture 数据解析为 Fixture 模型字段"""
    try:
        fixture_info = raw.get("fixture", {})
        teams = raw.get("teams", {})
        goals = raw.get("goals", {})
        score = raw.get("score", {})
        league = raw.get("league", {})
        status = fixture_info.get("status", {})

        home = teams.get("home", {})
        away = teams.get("away", {})

        status_short = status.get("short", "NS")

        # 判断比赛状态
        is_live = status_short in LIVE_STATUSES
        is_finished = status_short in FINISHED_STATUSES
        is_started = is_live or is_finished

        # source 规则
        if is_finished:
            source = "real_result"
        else:
            source = "api-sports"

        # 比分
        home_score = goals.get("home")
        away_score = goals.get("away")

        # 半场比分
        halftime = score.get("halftime", {})
        halftime_home = halftime.get("home") if halftime else None
        halftime_away = halftime.get("away") if halftime else None

        # 加时比分
        extra = score.get("extratime", {})
        extra_home = extra.get("home") if extra else None
        extra_away = extra.get("away") if extra else None

        # 点球比分
        penalty = score.get("penalty", {})
        penalty_home = penalty.get("home") if penalty else None
        penalty_away = penalty.get("away") if penalty else None

        # 胜者
        winner = raw.get("teams", {}).get("home", {})
        winner_team_id = None
        winner_team_name = None
        # API 中 winner 字段在 teams.home.winner / teams.away.winner
        if home.get("winner") is True:
            winner_team_id = home.get("id")
            winner_team_name = home.get("name")
        elif away.get("winner") is True:
            winner_team_id = away.get("id")
            winner_team_name = away.get("name")

        # 比赛日期
        match_date_str = fixture_info.get("date")
        match_date = None
        if match_date_str:
            try:
                match_date = datetime.fromisoformat(match_date_str.replace("Z", "+00:00"))
            except Exception:
                match_date = None

        # 场地
        venue = fixture_info.get("venue", {})
        venue_name = venue.get("name") if isinstance(venue, dict) else None
        city_name = venue.get("city") if isinstance(venue, dict) else None

        return {
            "api_fixture_id": fixture_info.get("id"),
            "season": league.get("season", season),
            "round_name": league.get("round"),
            "match_date": match_date,
            "venue": venue_name,
            "city": city_name,
            "home_team_id": home.get("id"),
            "away_team_id": away.get("id"),
            "home_team_name": home.get("name", "Unknown"),
            "away_team_name": away.get("name", "Unknown"),
            "status_short": status_short,
            "status_long": status.get("long"),
            "elapsed": status.get("elapsed"),
            "home_score": home_score,
            "away_score": away_score,
            "halftime_home_score": halftime_home,
            "halftime_away_score": halftime_away,
            "extra_home_score": extra_home,
            "extra_away_score": extra_away,
            "penalty_home_score": penalty_home,
            "penalty_away_score": penalty_away,
            "winner_team_id": winner_team_id,
            "winner_team_name": winner_team_name,
            "is_live": is_live,
            "is_started": is_started,
            "is_finished": is_finished,
            "source": source,
            "last_synced_at": datetime.now(timezone.utc),
        }
    except Exception as e:
        logger.error(f"[SyncService] parse_api_fixture error: {e}")
        return None


def upsert_fixture(db, fixture_data: Dict[str, Any]) -> bool:
    """将单条 fixture 数据 upsert 到 fixtures 表。
    已存在 api_fixture_id 则更新比分、状态、elapsed、last_synced_at。
    不存在则插入。
    """
    api_id = fixture_data.get("api_fixture_id")
    if api_id is None:
        return False

    existing = db.query(Fixture).filter(Fixture.api_fixture_id == api_id).first()

    if existing:
        # 更新已有记录
        for key, value in fixture_data.items():
            if key != "api_fixture_id" and key != "created_at":
                setattr(existing, key, value)
        existing.updated_at = datetime.now(timezone.utc)
    else:
        # 插入新记录
        fixture = Fixture(**fixture_data)
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
