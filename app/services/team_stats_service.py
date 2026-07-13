"""
team_stats_service - 攻防统计服务

基于 fixtures 已结束比赛计算 attack_score / defense_score /
knockout_performance_score / momentum_score。
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_FINISHED_STATUSES = {"FINISHED", "FT", "AET", "PEN"}
_KNOCKOUT_STAGES = {"round_of_32", "round_of_16", "quarter_finals",
                    "semi_finals", "final",
                    "last_32", "last_16", "quarterfinals", "semifinals"}


def compute_attack_defense_stats(
    fixtures: List[Dict[str, Any]],
    recent_form: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, float]]:
    """
    计算每支球队的攻防指标。

    Returns:
        {team: {attack_score, defense_score, goal_difference_score,
                knockout_performance_score, momentum_score}}
    """
    # ── 1. 收集已结束比赛 ──
    valid = []
    for fx in fixtures:
        status = (fx.get("status") or "").upper()
        if status not in _FINISHED_STATUSES:
            continue
        hs = fx.get("home_score")
        aws = fx.get("away_score")
        if hs is None or aws is None:
            continue
        valid.append(fx)

    # ── 2. 统计场均进球/失球 ──
    team_gf: Dict[str, List[float]] = {}
    team_ga: Dict[str, List[float]] = {}
    team_ko_wins: Dict[str, int] = {}
    team_ko_matches: Dict[str, int] = {}

    def _add(team: str, gf: float, ga: float):
        team_gf.setdefault(team, []).append(gf)
        team_ga.setdefault(team, []).append(ga)

    for fx in valid:
        home = fx.get("home_team", "")
        away = fx.get("away_team", "")
        hs = int(fx.get("home_score", 0))
        aws = int(fx.get("away_score", 0))
        stage = (fx.get("stage") or "").lower().strip()
        winner = fx.get("winner", "")

        if home and away:
            _add(home, hs, aws)
            _add(away, aws, hs)

        # 淘汰赛胜场
        is_ko = any(k in stage for k in _KNOCKOUT_STAGES)
        if is_ko and home and away:
            team_ko_matches[home] = team_ko_matches.get(home, 0) + 1
            team_ko_matches[away] = team_ko_matches.get(away, 0) + 1
            if winner and winner not in ("Draw", ""):
                if winner == home:
                    team_ko_wins[home] = team_ko_wins.get(home, 0) + 1
                elif winner == away:
                    team_ko_wins[away] = team_ko_wins.get(away, 0) + 1

    # ── 3. 归一化 ──
    all_gf_avg = []
    all_ga_avg = []
    team_avg: Dict[str, Dict[str, float]] = {}

    for team, gf_list in team_gf.items():
        if not gf_list:
            continue
        gf_avg = sum(gf_list) / len(gf_list)
        ga_avg = sum(team_ga.get(team, [0])) / max(len(team_ga.get(team, [1])), 1)
        team_avg[team] = {"gf_avg": gf_avg, "ga_avg": ga_avg}
        all_gf_avg.append(gf_avg)
        all_ga_avg.append(ga_avg)

    max_gf = max(all_gf_avg) if all_gf_avg else 3.0
    min_gf = min(all_gf_avg) if all_gf_avg else 0.0
    max_ga = max(all_ga_avg) if all_ga_avg else 3.0
    min_ga = min(all_ga_avg) if all_ga_avg else 0.0
    gf_range = max_gf - min_gf if max_gf != min_gf else 1.0
    ga_range = max_ga - min_ga if max_ga != min_ga else 1.0

    # ── 4. 计算最终分数 ──
    result: Dict[str, Dict[str, float]] = {}
    for team, avg in team_avg.items():
        attack_score = (avg["gf_avg"] - min_gf) / gf_range
        defense_score = 1.0 - (avg["ga_avg"] - min_ga) / ga_range
        gd_score = (attack_score + defense_score) / 2

        ko_total = team_ko_matches.get(team, 0)
        ko_wins = team_ko_wins.get(team, 0)
        ko_perf = ko_wins / ko_total if ko_total > 0 else 0.5

        # momentum: 来自 recent_form 的 win_rate
        rf = recent_form.get(team, {})
        momentum = rf.get("win_rate", 0.5)

        result[team] = {
            "team": team,
            "attack_score": round(max(0, min(1, attack_score)), 4),
            "defense_score": round(max(0, min(1, defense_score)), 4),
            "goal_difference_score": round(max(0, min(1, gd_score)), 4),
            "knockout_performance_score": round(max(0, min(1, ko_perf)), 4),
            "momentum_score": round(max(0, min(1, momentum)), 4),
        }

    logger.info("attack_defense_stats computed for %d teams", len(result))
    return result
