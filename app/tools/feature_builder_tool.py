"""
特征构建工具

把原始数据变成模型可用特征。
计算 power_score = 0.35*elo + 0.20*fifa + 0.20*form + 0.15*attack + 0.10*defense
缺失字段时降低权重并重新归一化。
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class FeatureBuilderTool:
    """球队特征构建工具"""

    def build_features(
        self,
        teams: List[Dict[str, Any]],
        api_form_data: Optional[Dict] = None,
        historical_stats: Optional[Dict] = None,
        scraper_values: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        为所有球队构建特征。

        Args:
            teams: 球队列表，每个包含 name, elo_rating, fifa_rank(可选) 等
            api_form_data: API 近期战绩 {team_name: {form, recent_matches}}
            historical_stats: 历史统计 {team_name: {goals_for_avg, goals_against_avg}}
            scraper_values: 爬虫身价 {team_name: market_value}

        Returns:
            {success, source, data: {team_name: {features}}, error}
        """
        api_form_data = api_form_data or {}
        historical_stats = historical_stats or {}
        scraper_values = scraper_values or {}

        result = {}
        for team in teams:
            name = team.get("name", "Unknown")
            features = self._build_single_team_features(
                name, team, api_form_data, historical_stats, scraper_values
            )
            result[name] = features

        return {"success": True, "source": "feature_builder", "data": result, "error": None}

    def _build_single_team_features(
        self,
        name: str,
        team: Dict,
        api_form_data: Dict,
        historical_stats: Dict,
        scraper_values: Dict,
    ) -> Dict[str, Any]:
        """为单支球队构建特征"""
        # 基础字段
        elo = team.get("elo_rating") or team.get("current_elo") or 1500.0
        fifa_rank = team.get("fifa_rank") or team.get("fifa_ranking")
        recent_form = team.get("recent_form", "")

        # 从 API 战绩计算胜率
        form_info = api_form_data.get(name, {})
        form_str = form_info.get("form", recent_form)
        win_rate = self._calc_win_rate(form_str)

        # 从历史统计获取攻防数据
        hist = historical_stats.get(name, {})
        goals_for_avg = hist.get("goals_for_avg", 1.2)
        goals_against_avg = hist.get("goals_against_avg", 1.0)

        # 归一化各维度 (0~1)
        elo_score = max(0.0, min(1.0, (elo - 1200) / 1000))
        fifa_score = self._calc_fifa_score(fifa_rank)
        form_score = win_rate
        attack_score = max(0.0, min(1.0, goals_for_avg / 3.0))
        defense_score = max(0.0, min(1.0, 1.0 - goals_against_avg / 3.0))

        # 带权重的 power_score，缺失字段降权
        weights = {
            "elo": 0.35,
            "fifa": 0.20,
            "form": 0.20,
            "attack": 0.15,
            "defense": 0.10,
        }
        scores = {
            "elo": elo_score,
            "fifa": fifa_score,
            "form": form_score,
            "attack": attack_score,
            "defense": defense_score,
        }

        # 数据源计数（用于 data_confidence）
        sources_available = 1  # elo 始终有
        if fifa_rank is not None:
            sources_available += 1
        if form_str and form_str != "-----":
            sources_available += 1
        if hist:
            sources_available += 1
        if name in scraper_values:
            sources_available += 1

        # 降权：fifa_score 为 None 时移除该项权重
        active_weights = {}
        active_scores = {}
        for key in weights:
            val = scores[key]
            if val is not None:
                active_weights[key] = weights[key]
                active_scores[key] = val

        # 重新归一化
        total_weight = sum(active_weights.values())
        if total_weight > 0:
            power_score = sum(
                (w / total_weight) * active_scores[k]
                for k, w in active_weights.items()
            )
        else:
            power_score = 0.5  # 完全无数据时的兜底

        data_confidence = sources_available / 5.0

        return {
            "team_name": name,
            "api_team_id": team.get("id") or team.get("api_team_id"),
            "elo_rating": elo,
            "fifa_rank": fifa_rank,
            "recent_form": form_str,
            "recent_win_rate": round(win_rate, 3),
            "recent_goals_for_avg": round(goals_for_avg, 3),
            "recent_goals_against_avg": round(goals_against_avg, 3),
            "attack_score": round(attack_score, 3),
            "defense_score": round(defense_score, 3),
            "form_score": round(form_score, 3),
            "power_score": round(power_score, 4),
            "data_confidence": round(data_confidence, 2),
        }

    @staticmethod
    def _calc_win_rate(form_str: str) -> float:
        """从 WDWLL 形式的字符串计算胜率"""
        if not form_str or form_str == "-----":
            return 0.4  # 默认中等偏下
        wins = form_str.count("W")
        draws = form_str.count("D")
        total = len(form_str)
        if total == 0:
            return 0.4
        return (wins + draws * 0.5) / total

    @staticmethod
    def _calc_fifa_score(fifa_rank: Optional[int]) -> Optional[float]:
        """FIFA 排名归一化 (排名越小越强)"""
        if fifa_rank is None:
            return None
        return max(0.0, min(1.0, 1.0 - (fifa_rank - 1) / 50))
