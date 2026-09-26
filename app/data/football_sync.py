"""API-Football -> persisted factual feed -> immutable V2 prediction input.

Scores remain visible even when missing provider coverage prevents prediction.
The API key is used only as a request header, never persisted in feed/error data.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone

import httpx

from app.domain.contracts import HistoricalGame, TournamentInput
from app.tournament.group_rules import KNOCKOUT, qualified_slots, rank_group

FINISHED = {"FT", "AET", "PEN"}
PENDING = {"NS", "TBD", "PST"}
ALIASES = {
    "USA": "United States",
    "United States of America": "United States",
    "South Korea": "South Korea",
    "Korea Republic": "South Korea",
    "Korea, Republic of": "South Korea",
    "Congo DR": "DR Congo",
    "Congo Democratic Republic": "DR Congo",
    "Congo, The Democratic Republic": "DR Congo",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote D'Ivoire": "Ivory Coast",
    "IR Iran": "Iran",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Czechia": "Czech Republic",
    "Curacao": "Curaçao",
    "Cabo Verde": "Cape Verde",
    "Korea Rep.": "South Korea",
    "Türkiye": "Turkey",
    "Turkiye": "Turkey",
}
ROUNDS = {
    "Round of 32": "round_of_32",
    "16th Finals": "round_of_32",
    "Round of 16": "round_of_16",
    "8th Finals": "round_of_16",
    "Quarter-finals": "quarter_finals",
    "Quarter Finals": "quarter_finals",
    "Semi-finals": "semi_finals",
    "Semi Finals": "semi_finals",
    "3rd Place Final": "third_place",
    "Third Place": "third_place",
    "Final": "final",
}


def now():
    return datetime.now(timezone.utc)


def canonical(name):
    return ALIASES.get(name, name)


def round_name(number):
    return (
        "round_of_32"
        if number <= 88
        else "round_of_16"
        if number <= 96
        else "quarter_finals"
        if number <= 100
        else "semi_finals"
        if number <= 102
        else "third_place"
        if number == 103
        else "final"
    )


def normalize(raw, season):
    if raw["league"]["id"] != 1 or raw["league"]["season"] != season:
        raise ValueError("API-Football returned a different competition/season")
    fixture, teams = raw["fixture"], raw["teams"]
    kickoff = datetime.fromisoformat(fixture["date"].replace("Z", "+00:00"))
    if kickoff.tzinfo is None:
        raise ValueError("Provider kickoff lacks timezone")
    scores = raw.get("score") or {}

    def pair(value):
        value = value or {}
        for side in ("home", "away"):
            v = value.get(side)
            if v is not None and (type(v) is not int or not 0 <= v <= 99):
                raise ValueError("Invalid provider score")
        return {side: value.get(side) for side in ("home", "away")}

    status = fixture["status"]["short"]
    winners = [
        canonical(teams[s]["name"]) for s in ("home", "away") if teams[s].get("winner") is True
    ]
    if len(winners) > 1:
        raise ValueError("Provider reported two winners")
    label = raw["league"].get("round", "")
    return {
        "fixture_id": "af_" + str(fixture["id"]),
        "provider_id": fixture["id"],
        "home": canonical(teams["home"]["name"]),
        "away": canonical(teams["away"]["name"]),
        "home_id": teams["home"]["id"],
        "away_id": teams["away"]["id"],
        "kickoff": kickoff.isoformat(),
        "status": status,
        "elapsed": fixture["status"].get("elapsed"),
        "stage": "group" if "group" in label.lower() else ROUNDS.get(label, "unknown"),
        "round": label,
        "score": pair(raw.get("goals")),
        "score_90": pair(scores.get("fulltime")),
        "score_extra_time": pair(scores.get("extratime")),
        "score_penalties": pair(scores.get("penalty")),
        "winner": winners[0] if status in FINISHED and winners else None,
        "source": "API-Football",
        "venue": fixture.get("venue"),
    }


class FootballClient:
    def __init__(self, settings, store, transport=None):
        self.settings, self.store = settings, store
        self.client = httpx.Client(timeout=25, transport=transport)

    def get(self, path, **params):
        if not self.settings.api_football_key:
            raise ValueError(
                "API-Football 未配置：请在后端设置 API_FOOTBALL / API_FOOTBALL_KEY / APISPORTS_KEY"
            )
        self.store.consume_budget("api-football", self.settings.API_FOOTBALL_MAX_DAILY_CALLS)
        response = self.client.get(
            "https://v3.football.api-sports.io/" + path,
            params=params,
            headers={"x-apisports-key": self.settings.api_football_key},
        )
        if not response.is_success:
            raise ValueError(f"API-Football HTTP {response.status_code}；请检查账号权限或配额")
        payload = response.json()
        if payload.get("errors"):
            # Provider error text can contain request parameters: do not echo it.
            raise ValueError("API-Football 拒绝请求；请检查密钥、套餐覆盖年份或请求配额")
        if payload.get("paging", {}).get("total", 1) > 1:
            raise ValueError("API-Football 返回分页数据；未把部分赛程当成完整数据")
        rows = payload.get("response")
        if not isinstance(rows, list):
            raise ValueError("API-Football 响应格式异常")
        return rows

    def close(self):
        self.client.close()


def conduct(raw):
    """One sanction per person; second-yellow dismissals are not direct reds."""
    if not isinstance(raw.get("events"), list):
        raise ValueError("缺少比赛纪律事件，不能把未知红黄牌当成零")
    people = defaultdict(list)
    teams = {raw["teams"][s]["id"] for s in ("home", "away")}
    seen = set()
    for event in raw["events"]:
        if event.get("type") != "Card":
            continue
        team, person = event.get("team", {}).get("id"), event.get("player", {}).get("id")
        if team not in teams or person is None:
            raise ValueError("纪律事件缺少球队或人员 ID，需核验")
        identity = (
            team,
            person,
            str(event.get("time")),
            event.get("detail"),
            event.get("comments"),
        )
        if identity in seen:
            continue
        seen.add(identity)
        detail = (str(event.get("detail", "")) + " " + str(event.get("comments") or "")).lower()
        if "second yellow" in detail or "second yellow card" in detail:
            sanction = "second_yellow"
        elif "yellow" in detail:
            sanction = "yellow"
        elif "red" in detail:
            sanction = "red"
        else:
            raise ValueError("未知纪律事件类型")
        people[(team, person)].append(sanction)
    deductions = {t: 0 for t in teams}
    for (team, _), cards in people.items():
        if "second_yellow" in cards or cards.count("yellow") >= 2:
            penalty = -3
        elif "red" in cards:
            penalty = -5 if "yellow" in cards else -4
        else:
            penalty = -1
        deductions[team] += penalty
    return tuple(deductions[raw["teams"][s]["id"]] for s in ("home", "away"))


def to_snapshot(original, feed):
    if not original.group_stage:
        raise ValueError("此同步工作流需要完整的 2026 赛事结构")
    rows = feed["fixtures"]
    stage = original.group_stage.model_dump(mode="json")
    group_rows = [r for r in rows if r["stage"] == "group"]
    if len(group_rows) != 72:
        raise ValueError(f"已获取 {len(group_rows)}/72 场小组赛；尚不能计算完整赛事")
    if any(r["status"] not in FINISHED | PENDING for r in rows):
        raise ValueError("已显示进行中/中断比赛的真实比分；当前赛前模型不计算进行中比赛")
    details = feed.get("details", {})
    matches = []
    history = list(original.history)
    # Replace prior provider observations; avoid counting a CSV game a second time.
    history = [g for g in history if not g.match_id.startswith("af_")]
    keys = {(g.date.date(), frozenset((g.home, g.away))) for g in history}
    for old in original.group_stage.matches:
        candidates = [r for r in group_rows if {r["home"], r["away"]} == {old.home, old.away}]
        if len(candidates) != 1:
            raise ValueError(f"赛程球队映射不唯一：{old.home} / {old.away}")
        r = candidates[0]
        m = dict(
            fixture_id=r["fixture_id"],
            group=old.group,
            home=r["home"],
            away=r["away"],
            kickoff=r["kickoff"],
            neutral=old.neutral,
        )
        if r["status"] in FINISHED:
            if r["status"] != "FT" or any(v is None for v in r["score_90"].values()):
                raise ValueError("小组赛完场比分缺失或出现异常加时状态")
            if not feed.get("events_covered"):
                raise ValueError("真实比分已保存；API 套餐未确认纪律事件覆盖，预测暂缓")
            detail = details.get(str(r["provider_id"]), {})
            if detail and normalize(detail, original.season)["score_90"] != r["score_90"]:
                raise ValueError("赛程比分与纪律详情版本不一致，请稍后刷新")
            hc, ac = conduct(detail)
            m.update(
                home_score=r["score_90"]["home"],
                away_score=r["score_90"]["away"],
                home_conduct=hc,
                away_conduct=ac,
            )
        matches.append(m)
    stage["matches"] = matches
    stage["knockout_winners"], stage["knockout_completed_at"] = {}, {}
    completed_ko = [r for r in rows if r["stage"] != "group" and r["status"] in FINISHED]
    if completed_ko or all(m.get("home_score") is not None for m in matches):
        if any(m.get("home_score") is None for m in matches):
            raise ValueError("淘汰赛已结束但小组赛数据不完整")
        tables = {
            g: rank_group(teams, [m for m in matches if m["group"] == g], stage["fifa_rankings"])
            for g, teams in stage["groups"].items()
        }
        slots, _ = qualified_slots(tables, stage["fifa_rankings"])
        used = set()
        for match_id, hs, aws in KNOCKOUT:
            if hs not in slots or aws not in slots:
                continue
            pair = {slots[hs], slots[aws]}
            candidates = [
                r
                for r in rows
                if r["stage"] == round_name(int(match_id)) and {r["home"], r["away"]} == pair
            ]
            if len(candidates) > 1:
                raise ValueError("重复淘汰赛赛程")
            if not candidates:
                continue
            r = candidates[0]
            r["official_match_id"] = match_id
            if r["status"] not in FINISHED:
                continue
            if r["winner"] not in pair:
                raise ValueError("淘汰赛缺少经确认的晋级球队")
            used.add(r["fixture_id"])
            stage["knockout_winners"][match_id] = r["winner"]
            # An observation timestamp, not an invented full-time whistle time.
            stage["knockout_completed_at"][match_id] = feed["fetched_at"]
            slots["W" + match_id] = r["winner"]
            slots["L" + match_id] = next(t for t in pair if t != r["winner"])
        if len(used) != len(completed_ko):
            raise ValueError("淘汰赛真实对阵与小组排名/官方晋级图不一致，需核验")
    for r in rows:
        if r["status"] not in FINISHED or any(v is None for v in r["score_90"].values()):
            continue
        date = datetime.fromisoformat(r["kickoff"])
        key = (date.date(), frozenset((r["home"], r["away"])))
        if key not in keys:
            history.append(
                HistoricalGame(
                    match_id=r["fixture_id"],
                    date=date,
                    home=r["home"],
                    away=r["away"],
                    home_score=r["score_90"]["home"],
                    away_score=r["score_90"]["away"],
                    source="API-Football / score.fulltime",
                    competition="FIFA World Cup",
                    score_basis="90_minutes",
                )
            )
            keys.add(key)
    return TournamentInput.model_validate(
        {
            **original.model_dump(mode="json"),
            "as_of": (
                datetime.fromisoformat(feed["fetched_at"]) + timedelta(microseconds=1)
            ).isoformat(),
            "source": "API-Football World Cup fixtures; historical training provenance retained",
            "group_stage": stage,
            "provider_fixtures": rows,
            "history": history,
            "warnings": [w for w in original.warnings if "历史回放" not in w and "00:00" not in w]
            + [
                "API-Football 实际赛果已锁定；仅未完赛比赛使用模型模拟。",
                "FIFA 排名沿用快照标注的发布版本；阵容/伤停不属于现有模型输入。",
            ],
        }
    )


def sync(store, settings, original, transport=None):
    """Persist factual feed first; failed prediction conversion never hides scores."""
    previous = store.feed(original.season) or {}
    stamp = now().isoformat()
    client = FootballClient(settings, store, transport)
    feed = dict(previous, last_attempt_at=stamp, last_error=None)
    try:
        raw = client.get("fixtures", league=1, season=original.season)
        if not raw:
            raise ValueError("API-Football 未返回赛程；保留上一次真实数据")
        fixtures = [normalize(r, original.season) for r in raw]
        if len({r["fixture_id"] for r in fixtures}) != len(fixtures):
            raise ValueError("API-Football 返回重复比赛 ID")
        feed.update(
            fixtures=fixtures,
            fetched_at=stamp,
            snapshot_id=None,
            prediction_ready=False,
            prediction_error=None,
        )
        store.save_feed(original.season, feed)
        coverage_age = (
            now() - datetime.fromisoformat(feed.get("coverage_at", "2000-01-01T00:00:00+00:00"))
        ).total_seconds()
        if coverage_age > 21600:
            leagues = client.get("leagues", id=1, season=original.season)
            editions = [
                s
                for league in leagues
                for s in league.get("seasons", [])
                if s.get("year") == original.season
            ]
            feed["events_covered"] = bool(
                editions and editions[0].get("coverage", {}).get("fixtures", {}).get("events")
            )
            feed["coverage_at"] = stamp
        details = feed.setdefault("details", {})
        timestamps = feed.setdefault("detail_timestamps", {})
        needed = []
        for r in fixtures:
            if r["status"] not in FINISHED or r["stage"] != "group":
                continue
            key = str(r["provider_id"])
            old = details.get(key)
            expired = (
                now() - datetime.fromisoformat(timestamps.get(key, "2000-01-01T00:00:00+00:00"))
            ).total_seconds() > 21600
            if old is None or expired or old.get("score", {}).get("fulltime") != r["score_90"]:
                needed.append(key)
        if feed.get("events_covered"):
            for start in range(0, len(needed), 20):
                batch = client.get("fixtures", ids="-".join(needed[start : start + 20]))
                for r in batch:
                    normalized = normalize(r, original.season)
                    key = str(normalized["provider_id"])
                    if key not in needed[start : start + 20]:
                        raise ValueError("Provider detail IDs differ from request")
                    details[key] = r
                    timestamps[key] = stamp
        try:
            snapshot = to_snapshot(original, feed)
            feed["snapshot_id"] = store.put_input(snapshot)
            feed["prediction_ready"] = True
        except ValueError as exc:
            feed["prediction_error"] = str(exc)
        store.save_feed(original.season, feed)
        return feed
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        feed["last_error"] = (
            "API-Football 网络请求失败" if isinstance(exc, httpx.HTTPError) else str(exc)
        )
        store.save_feed(original.season, feed)
        raise ValueError(feed["last_error"]) from None
    finally:
        client.close()


def public_feed(store, settings, season=2026):
    feed = store.feed(season) or {}
    return {
        "provider": "API-Football",
        "configured": bool(settings.api_football_key),
        **{
            key: feed.get(key)
            for key in (
                "fetched_at",
                "last_attempt_at",
                "last_error",
                "prediction_error",
                "snapshot_id",
                "prediction_ready",
            )
        },
        "fixtures": feed.get("fixtures", []),
    }
