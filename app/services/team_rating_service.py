"""
team_rating_service - 球队评分数据加载服务

从 data/team_ratings.csv 加载 FIFA/Elo 评分、阵容实力等特征。
这是预测特征，不是比赛事实源。
"""

import csv
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_DATA_PATH = Path(__file__).parent.parent.parent / "data" / "team_ratings.csv"


def load_team_ratings(csv_path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    加载球队评分数据。

    Returns:
        {team_name: {fifa_rank, elo_rating, squad_strength,
                     world_cup_experience, major_tournament_score, source}}
    """
    path = Path(csv_path) if csv_path else _DATA_PATH
    if not path.exists():
        logger.warning("team_ratings.csv not found at %s", path)
        return {}

    ratings: Dict[str, Dict[str, Any]] = {}
    try:
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                team = row.get("team", "").strip()
                if not team:
                    continue
                ratings[team] = {
                    "team": team,
                    "fifa_rank": _int(row.get("fifa_rank")),
                    "elo_rating": _float(row.get("elo_rating")),
                    "squad_strength": _float(row.get("squad_strength")),
                    "world_cup_experience": _float(row.get("world_cup_experience")),
                    "major_tournament_score": _float(row.get("major_tournament_score")),
                    "source": row.get("source", "unknown"),
                    "updated_at": row.get("updated_at", ""),
                }
        logger.info("Loaded %d team ratings from %s", len(ratings), path)
    except Exception as e:
        logger.error("Failed to load team_ratings.csv: %s", e)
    return ratings


def get_team_rating(team: str, ratings: Dict[str, Dict]) -> Dict[str, Any]:
    """获取单支球队评分，缺失时返回中性值。"""
    neutral = {
        "team": team,
        "fifa_rank": 50,
        "elo_rating": 1500.0,
        "squad_strength": 0.5,
        "world_cup_experience": 0.3,
        "major_tournament_score": 0.3,
        "source": "default",
    }
    return ratings.get(team, neutral)


def _int(v) -> int:
    try:
        return int(v) if v else 0
    except (ValueError, TypeError):
        return 0


def _float(v) -> float:
    try:
        return float(v) if v else 0.0
    except (ValueError, TypeError):
        return 0.0
