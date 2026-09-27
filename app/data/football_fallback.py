"""Retain the original secondary API as an explicitly labelled factual feed.

Missing discipline coverage is a prediction limitation, not a reason to hide scores.
"""

from datetime import datetime, timezone

import httpx

from app.data.football_sync import canonical


def normalize_match(match, season):
    if match.get("competition", {}).get("code") != "WC":
        raise ValueError("备用接口返回了不同赛事")
    kickoff = datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00"))
    if kickoff.year != season:
        raise ValueError("备用接口返回了不同年份的比赛")
    score = match.get("score") or {}
    duration = score.get("duration")
    complete = match["status"] == "FINISHED"
    status = {
        "SCHEDULED": "NS",
        "TIMED": "NS",
        "POSTPONED": "PST",
        "IN_PLAY": "LIVE",
        "PAUSED": "HT",
    }.get(match["status"], match["status"])
    if complete:
        status = {"REGULAR": "FT", "EXTRA_TIME": "AET", "PENALTY_SHOOTOUT": "PEN"}.get(
            duration, "FT"
        )

    def pair(value):
        value = value or {}
        result = {s: value.get(s) for s in ("home", "away")}
        if any(v is not None and (type(v) is not int or v < 0 or v > 99) for v in result.values()):
            raise ValueError("备用接口比分无效")
        return result

    home, away = canonical(match["homeTeam"]["name"]), canonical(match["awayTeam"]["name"])
    return {
        "fixture_id": "fd_" + str(match["id"]),
        "provider_id": match["id"],
        "home": home,
        "away": away,
        "kickoff": kickoff.isoformat(),
        "status": status,
        "round": match.get("stage", "unknown"),
        "source": "football-data.org",
        "score": pair(score.get("fullTime")),
        "score_90": pair(
            score.get("fullTime") if duration == "REGULAR" else score.get("regularTime")
        ),
        "score_extra_time": pair(score.get("extraTime")),
        "score_penalties": pair(score.get("penalties")),
        "winner": {"HOME_TEAM": home, "AWAY_TEAM": away}.get(score.get("winner"))
        if complete
        else None,
    }


def fetch_fallback(store, settings, season, transport=None):
    result = {
        "provider": "football-data.org",
        "fixtures": [],
        "error": None,
        "prediction_ready": False,
        "limitation": "备用接口保留真实比分展示；尚未核验纪律数据，不能替代完整赛事预测输入。",
    }
    try:
        store.consume_budget("football-data", settings.API_FOOTBALL_MAX_DAILY_CALLS)
        with httpx.Client(timeout=15, transport=transport) as client:
            response = client.get(
                "https://api.football-data.org/v4/competitions/WC/matches",
                params={"season": season},
                headers={"X-Auth-Token": settings.football_data_api_key},
            )
        if not response.is_success:
            raise ValueError(f"football-data.org HTTP {response.status_code}")
        rows = response.json().get("matches", [])
        if not rows:
            raise ValueError("football-data.org 未返回该赛季比赛")
        result["fixtures"] = [normalize_match(m, season) for m in rows]
        result["fetched_at"] = datetime.now(timezone.utc).isoformat()
    except (httpx.HTTPError, ValueError, KeyError, RuntimeError):
        result["error"] = "football-data.org 请求失败或未返回可核验的该赛季比赛"
    return result
