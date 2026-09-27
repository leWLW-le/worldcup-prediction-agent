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


def completed_snapshot(original, fallback):
    """Keep the legacy fixed-bracket path for fully observed competitions.

    This does not infer group rankings from missing conduct data: the provider's
    actual knockout participants and winners must form a complete consistent tree.
    """
    from collections import Counter
    from copy import deepcopy

    from app.domain.contracts import FixtureNode, TournamentInput
    from app.tournament.bracket import BracketGraph

    rows = deepcopy(fallback["fixtures"])
    expected = {
        "GROUP_STAGE": 72,
        "LAST_32": 16,
        "LAST_16": 8,
        "QUARTER_FINALS": 4,
        "SEMI_FINALS": 2,
        "THIRD_PLACE": 1,
        "FINAL": 1,
    }
    if Counter(r["round"] for r in rows) != expected or any(
        r["status"] not in ("FT", "AET", "PEN") for r in rows
    ):
        raise ValueError(
            "备用通道仅在完整 104 场赛果已确认时生成已结束赛事结果；赛中完整规则仍需纪律数据"
        )
    nodes, parents = [], {}
    stages = [
        ("LAST_32", "round_of_32"),
        ("LAST_16", "round_of_16"),
        ("QUARTER_FINALS", "quarter_finals"),
        ("SEMI_FINALS", "semi_finals"),
        ("FINAL", "final"),
    ]
    for label, stage in stages:
        next_parents = {}
        for r in [r for r in rows if r["round"] == label]:
            if not r["home"] or not r["away"] or r["winner"] not in (r["home"], r["away"]):
                raise ValueError("真实淘汰赛参与者或胜者缺失")
            sources = []
            for team in (r["home"], r["away"]):
                if stage == "round_of_32":
                    sources.append("team:" + team)
                elif team in parents:
                    sources.append("winner:" + parents[team])
                else:
                    raise ValueError("真实淘汰赛对阵与上一轮胜者不一致")
            node = FixtureNode(
                fixture_id=r["fixture_id"],
                stage=stage,
                home_source=sources[0],
                away_source=sources[1],
                kickoff=r["kickoff"],
                status="finished",
                actual_winner=r["winner"],
            )
            nodes.append(node)
            next_parents[r["winner"]] = r["fixture_id"]
            r["official_match_id"] = r["fixture_id"]
        parents = next_parents
    BracketGraph(nodes)
    return TournamentInput(
        season=original.season,
        as_of=fallback["fetched_at"],
        provenance="verified",
        source="football-data.org current World Cup results; validated complete observed knockout tree",
        history=original.history,
        fixtures=tuple(nodes),
        provider_fixtures=tuple(rows),
        warnings=(
            "104 场真实赛果已获取；淘汰赛对阵和胜者逐轮校验。",
            "已结束赛事：冠军为已确认赛果，不是赛前预测准确率。",
            "缺少纪律证据，因此本通道保留实际淘汰赛图，不重算小组排名；原有完整小组赛引擎仍保留。",
        ),
    )
