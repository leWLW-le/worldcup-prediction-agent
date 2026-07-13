"""
recent_form_service - 近期状态计算服务

基于 fixtures 表中已结束比赛计算每支球队近期状态。
只使用已验证的真实比赛结果，不使用预测比赛。
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_FINISHED_STATUSES = {"FINISHED", "FT", "AET", "PEN"}


def compute_recent_form(fixtures: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    根据已结束比赛计算每支球队近期状态。

    只使用 status in _FINISHED_STATUSES 且 is_verified=true 且 needs_review=false 的比赛。

    Returns:
        {team_name: {matches_played, wins, draws, losses, goals_for, goals_against,
                     goal_difference, points, win_rate, goals_for_per_match,
                     goals_against_per_match, clean_sheets, form_score}}
    """
    # 过滤有效比赛
    valid = []
    for fx in fixtures:
        status = (fx.get("status") or "").upper()
        if status not in _FINISHED_STATUSES:
            continue
        if fx.get("needs_review", True):
            continue
        if not fx.get("is_verified", False):
            continue
        hs = fx.get("home_score")
        aws = fx.get("away_score")
        if hs is None or aws is None:
            continue
        valid.append(fx)

    logger.info("recent_form: %d valid finished fixtures out of %d total", len(valid), len(fixtures))

    # 统计每支球队
    stats: Dict[str, Dict[str, Any]] = {}

    def _ensure(team: str):
        if team not in stats:
            stats[team] = {
                "team": team,
                "matches_played": 0,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "goals_for": 0,
                "goals_against": 0,
                "clean_sheets": 0,
            }

    for fx in valid:
        home = fx.get("home_team", "")
        away = fx.get("away_team", "")
        hs = int(fx.get("home_score", 0))
        aws = int(fx.get("away_score", 0))
        winner = fx.get("winner", "")

        if not home or not away:
            continue

        _ensure(home)
        _ensure(away)

        # Home team
        stats[home]["matches_played"] += 1
        stats[home]["goals_for"] += hs
        stats[home]["goals_against"] += aws
        if hs == 0:
            stats[away]["clean_sheets"] += 1

        # Away team
        stats[away]["matches_played"] += 1
        stats[away]["goals_for"] += aws
        stats[away]["goals_against"] += hs
        if aws == 0:
            stats[home]["clean_sheets"] += 1

        # Win/Draw/Loss
        if winner and winner.upper() not in ("DRAW", ""):
            if winner == home or (winner != away and winner != "Draw"):
                # Home wins if winner == home or winner is not away and not Draw
                if winner == home:
                    stats[home]["wins"] += 1
                    stats[away]["losses"] += 1
                elif winner == away:
                    stats[away]["wins"] += 1
                    stats[home]["losses"] += 1
                else:
                    # winner name doesn't match either team - use score
                    if hs > aws:
                        stats[home]["wins"] += 1
                        stats[away]["losses"] += 1
                    elif aws > hs:
                        stats[away]["wins"] += 1
                        stats[home]["losses"] += 1
                    else:
                        stats[home]["draws"] += 1
                        stats[away]["draws"] += 1
            else:
                if winner == away:
                    stats[away]["wins"] += 1
                    stats[home]["losses"] += 1
        else:
            # Draw
            if hs > aws:
                stats[home]["wins"] += 1
                stats[away]["losses"] += 1
            elif aws > hs:
                stats[away]["wins"] += 1
                stats[home]["losses"] += 1
            else:
                stats[home]["draws"] += 1
                stats[away]["draws"] += 1

    # 计算衍生指标
    result = {}
    for team, s in stats.items():
        mp = s["matches_played"]
        if mp == 0:
            continue
        gd = s["goals_for"] - s["goals_against"]
        pts = s["wins"] * 3 + s["draws"]
        win_rate = s["wins"] / mp if mp > 0 else 0
        gf_pm = s["goals_for"] / mp if mp > 0 else 0
        ga_pm = s["goals_against"] / mp if mp > 0 else 0

        # form_score: 综合评分 (0-1)
        form_score = (
            win_rate * 0.4
            + min(gf_pm / 3.0, 1.0) * 0.25
            + max(0, 1 - ga_pm / 3.0) * 0.2
            + min(max(gd / mp, -3), 3) / 6 * 0.15 + 0.15 * 0.5
        )
        form_score = max(0.0, min(1.0, form_score))

        result[team] = {
            "team": team,
            "matches_played": mp,
            "wins": s["wins"],
            "draws": s["draws"],
            "losses": s["losses"],
            "goals_for": s["goals_for"],
            "goals_against": s["goals_against"],
            "goal_difference": gd,
            "points": pts,
            "win_rate": round(win_rate, 4),
            "goals_for_per_match": round(gf_pm, 3),
            "goals_against_per_match": round(ga_pm, 3),
            "clean_sheets": s["clean_sheets"],
            "form_score": round(form_score, 4),
        }

    logger.info("recent_form computed for %d teams", len(result))
    return result
