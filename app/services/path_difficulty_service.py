"""
path_difficulty_service - 晋级路径难度评估

核心思路：
  每支球队找到当前轮次的下一场比赛对手，用自身评分与对手评分对比：
  - 自身评分 > 对手评分 → 路径更容易
  - 自身评分 < 对手评分 → 路径更难
  只看当前轮次，不考虑后续轮次。
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Elo 差值归一化基准：300 分视为最大差距
_ELO_SPREAD = 300.0


def compute_path_difficulty(
    knockout_predictions: List[Dict[str, Any]],
    team_ratings: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    计算每支仍有晋级机会球队的路径难度。

    对每支球队：
      1. 找到当前轮次的下一场比赛和对手
      2. 用 team_elo - opponent_elo 得到差值
         差值 > 0 → 实力高于对手 → 更容易
         差值 < 0 → 实力低于对手 → 更难
      3. 映射到 path_difficulty_score (0~1) 和 path_advantage_score (0~1)

    Args:
        knockout_predictions: 淘汰赛预测列表
        team_ratings: team_rating_service 的评分数据

    Returns:
        {team: {current_round, next_opponent, next_opponent_rating,
                path_difficulty_score, path_advantage_score}}
    """
    # 按轮次分组
    rounds: Dict[str, List[Dict]] = {}
    for m in knockout_predictions:
        rnd = m.get("round", "")
        rounds.setdefault(rnd, []).append(m)

    # 确定每支球队当前所在轮次（取最靠后的轮次）
    team_round: Dict[str, str] = {}
    round_order = ["round_of_32", "round_of_16", "quarter_finals",
                   "semi_finals", "final"]
    for rnd in round_order:
        for m in rounds.get(rnd, []):
            home = m.get("home_team", "")
            away = m.get("away_team", "")
            if home:
                team_round[home] = rnd
            if away:
                team_round[away] = rnd

    # 获取球队 Elo 评分，缺失时用中性值 1500
    def _get_elo(name: str) -> float:
        r = team_ratings.get(name, {})
        return r.get("elo_rating", 1500.0) if r else 1500.0

    # 将 Elo 差值映射到 0-1 难度分
    # diff = team_elo - opp_elo
    # diff 越大（自己越强/对手越弱）→ 难度越低
    # diff 越小（自己越弱/对手越强）→ 难度越高
    def _diff_to_difficulty(diff: float) -> float:
        return max(0.0, min(1.0, 0.5 - diff / (2.0 * _ELO_SPREAD)))

    result: Dict[str, Dict[str, Any]] = {}

    for team in team_round:
        current_rnd = team_round[team]
        team_elo = _get_elo(team)

        next_opp_rating = 0.0
        next_opponent = ""

        # 找当前轮次的直接对手
        for m in rounds.get(current_rnd, []):
            if m.get("home_team") == team or m.get("away_team") == team:
                opp = m.get("away_team") if m.get("home_team") == team else m.get("home_team")
                next_opponent = opp
                next_opp_rating = _get_elo(opp)
                break

        # 只看当前轮次这一场比赛的难度
        if next_opp_rating > 0:
            path_diff = _diff_to_difficulty(team_elo - next_opp_rating)
        else:
            path_diff = 0.5  # 没有对手信息，中性

        path_diff = max(0.0, min(1.0, path_diff))
        path_adv = 1.0 - path_diff

        result[team] = {
            "team": team,
            "current_round": current_rnd,
            "next_opponent": next_opponent,
            "next_opponent_rating": round(next_opp_rating, 1),
            "path_difficulty_score": round(path_diff, 4),
            "path_advantage_score": round(path_adv, 4),
        }

    logger.info("path_difficulty computed for %d teams", len(result))
    return result
