"""
feature_builder_service - 统一特征构建

整合 team_ratings / recent_form / attack_defense / path_difficulty
为每支仍有夺冠可能的球队生成统一 team_features。
"""

import logging
from typing import Any, Dict, List, Optional

from app.services.team_rating_service import load_team_ratings
from app.services.recent_form_service import compute_recent_form
from app.services.team_stats_service import compute_attack_defense_stats
from app.services.path_difficulty_service import compute_path_difficulty

logger = logging.getLogger(__name__)

# overall_strength_score 权重
_WEIGHTS = {
    "elo_rating": 0.25,
    "fifa_rank": 0.15,
    "recent_form_score": 0.20,
    "attack_score": 0.10,
    "defense_score": 0.10,
    "path_advantage_score": 0.10,
    "knockout_performance_score": 0.10,
}


def build_team_features(
    fixtures: List[Dict[str, Any]],
    knockout_predictions: List[Dict[str, Any]],
    csv_path: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    构建统一球队特征。

    Returns:
        {team: {team, elo_rating, fifa_rank, squad_strength,
                recent_form_score, attack_score, defense_score,
                momentum_score, knockout_performance_score,
                path_difficulty_score, path_advantage_score,
                overall_strength_score, feature_quality}}
    """
    # ── 阶段 1：必须完成 ──
    ratings = load_team_ratings(csv_path)
    recent_form = compute_recent_form(fixtures)
    atk_def = compute_attack_defense_stats(fixtures, recent_form)
    path_diff = compute_path_difficulty(knockout_predictions, ratings)

    # 合并所有涉及的球队
    all_teams = set()
    all_teams.update(ratings.keys())
    all_teams.update(recent_form.keys())
    all_teams.update(atk_def.keys())
    all_teams.update(path_diff.keys())

    result: Dict[str, Dict[str, Any]] = {}
    missing_map: Dict[str, List[str]] = {}

    for team in all_teams:
        r = ratings.get(team, {})
        rf = recent_form.get(team, {})
        ad = atk_def.get(team, {})
        pd = path_diff.get(team, {})

        missing = []

        # Elo 归一化到 0-1
        elo_raw = r.get("elo_rating", 1500.0)
        elo_norm = max(0.0, min(1.0, (elo_raw - 1200) / 1000))

        # FIFA rank 归一化 (rank 越小越好)
        fifa_raw = r.get("fifa_rank", 50)
        fifa_norm = max(0.0, min(1.0, 1.0 - (fifa_raw - 1) / 60))

        recent_form_score = rf.get("form_score")
        if recent_form_score is None:
            recent_form_score = 0.5
            missing.append("recent_form")

        attack_score = ad.get("attack_score")
        if attack_score is None:
            attack_score = 0.5
            missing.append("attack_score")

        defense_score = ad.get("defense_score")
        if defense_score is None:
            defense_score = 0.5
            missing.append("defense_score")

        momentum_score = ad.get("momentum_score", 0.5)
        ko_perf = ad.get("knockout_performance_score", 0.5)
        path_diff_score = pd.get("path_difficulty_score", 0.5)
        path_adv = pd.get("path_advantage_score", 0.5)

        # 综合评分
        overall = (
            elo_norm * _WEIGHTS["elo_rating"]
            + fifa_norm * _WEIGHTS["fifa_rank"]
            + recent_form_score * _WEIGHTS["recent_form_score"]
            + attack_score * _WEIGHTS["attack_score"]
            + defense_score * _WEIGHTS["defense_score"]
            + path_adv * _WEIGHTS["path_advantage_score"]
            + ko_perf * _WEIGHTS["knockout_performance_score"]
        )

        result[team] = {
            "team": team,
            "elo_rating": elo_raw,
            "elo_norm": round(elo_norm, 4),
            "fifa_rank": fifa_raw,
            "fifa_norm": round(fifa_norm, 4),
            "squad_strength": r.get("squad_strength", 0.5),
            "recent_form_score": round(recent_form_score, 4),
            "attack_score": round(attack_score, 4),
            "defense_score": round(defense_score, 4),
            "momentum_score": round(momentum_score, 4),
            "knockout_performance_score": round(ko_perf, 4),
            "path_difficulty_score": round(path_diff_score, 4),
            "path_advantage_score": round(path_adv, 4),
            # team_strength_index: 球队综合实力指数（非概率，不用于夺冠概率计算）
            "team_strength_index": round(overall, 4),
            "feature_quality": {"missing": missing} if missing else {"missing": []},
        }
        if missing:
            missing_map[team] = missing

    logger.info("team_features built for %d teams (%d with missing data)",
                len(result), len(missing_map))
    return result
