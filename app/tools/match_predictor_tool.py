"""
比赛预测工具 V2

优先使用 EnsemblePredictionService（NN V2 + XGBoost + ELO + Poisson + Path 集成）。
当集成模型不可用时，自动降级到旧版 ProbabilityEngine（纯 ELO）。
对外接口不变：predict_match(home_dict, away_dict, stage) → dict。
"""

import logging
import random
from typing import Any, Dict, Optional

from app.services.probability_engine import ProbabilityEngine

logger = logging.getLogger(__name__)


class MatchPredictorTool:
    """单场比赛预测工具（V2 — 集成模型优先）"""

    def __init__(self, seed: int | None = None):
        self.engine = ProbabilityEngine()
        if seed is not None:
            random.seed(seed)

        # ── 尝试加载集成预测服务 ──
        self._ensemble = None
        self._team_cache: Dict[str, Any] = {}
        self._db = None
        self._ensemble_available = False
        self._init_ensemble()

    def _init_ensemble(self):
        """尝试初始化 EnsemblePredictionService，失败则静默降级"""
        try:
            from app.db.database import SessionLocal
            from app.services.ensemble_prediction_service import EnsemblePredictionService
            from app.models.schemas import Team

            self._db = SessionLocal()
            self._ensemble = EnsemblePredictionService(self._db)

            # 预缓存所有球队 ORM 对象（按名称）
            teams = self._db.query(Team).all()
            for t in teams:
                self._team_cache[t.name] = t
            # 同时缓存常见别名（大小写不敏感）
            for t in teams:
                self._team_cache.setdefault(t.name.lower(), t)
                self._team_cache.setdefault(t.name.upper(), t)

            self._ensemble_available = True
            logger.info(
                "MatchPredictorTool V2: Ensemble loaded (%d teams cached)",
                len(self._team_cache),
            )
        except Exception as e:
            logger.warning(
                "MatchPredictorTool V2: Ensemble init failed, falling back to ELO-only. (%s)",
                e,
            )
            self._ensemble_available = False

    def _lookup_team(self, name: str):
        """从缓存中查找球队 ORM 对象"""
        team = self._team_cache.get(name)
        if team:
            return team
        # 尝试大小写不敏感匹配
        team = self._team_cache.get(name.lower())
        if team:
            return team
        # 尝试模糊匹配（去除空格/下划线）
        normalized = name.lower().replace(" ", "").replace("_", "")
        for key, t in self._team_cache.items():
            if key.lower().replace(" ", "").replace("_", "") == normalized:
                return t
        return None

    def predict_match(
        self,
        home_team: Dict[str, Any],
        away_team: Dict[str, Any],
        stage: str = "group",
    ) -> Dict[str, Any]:
        """
        预测单场比赛。优先使用集成模型，失败时降级到 ELO。

        Args:
            home_team: {team_name, elo_rating, power_score, attack_score, ...}
            away_team: 同上
            stage: "group" | "knockout"

        Returns:
            预测结果字典
        """
        home_name = home_team.get("team_name", "Home")
        away_name = away_team.get("team_name", "Away")

        # ── 尝试集成模型 ──
        if self._ensemble_available:
            home_orm = self._lookup_team(home_name)
            away_orm = self._lookup_team(away_name)
            if home_orm and away_orm:
                try:
                    return self._predict_with_ensemble(
                        home_orm, away_orm, home_name, away_name,
                        home_team, away_team, stage,
                    )
                except Exception as e:
                    logger.warning(
                        "Ensemble prediction failed for %s vs %s: %s, falling back to ELO",
                        home_name, away_name, e,
                    )

        # ── 降级：旧版 ELO ──
        return self._predict_with_elo_fallback(
            home_team, away_team, home_name, away_name, stage,
        )

    def _predict_with_ensemble(
        self, home_orm, away_orm,
        home_name: str, away_name: str,
        home_dict: Dict, away_dict: Dict,
        stage: str,
    ) -> Dict[str, Any]:
        """使用集成模型预测"""
        pred = self._ensemble.predict_with_ensemble(home_orm, away_orm)
        probs = pred.get("probabilities", {})
        home_win_prob = round(probs.get("home_win", 0.5), 4)
        draw_prob = round(probs.get("draw", 0.25), 4)
        away_win_prob = round(probs.get("away_win", 0.25), 4)

        # 使用集成模型的概率来生成比分
        home_elo = home_orm.current_elo or 1500
        away_elo = away_orm.current_elo or 1500
        home_expected = 1.5 + (home_elo - away_elo) / 400
        away_expected = 1.5 - (home_elo - away_elo) / 400
        pred_home_score = int(round(max(0, home_expected)))
        pred_away_score = int(round(max(0, away_expected)))

        # 淘汰赛不能平局
        is_penalty = False
        if stage == "knockout" and pred_home_score == pred_away_score:
            if home_win_prob >= away_win_prob:
                pred_home_score += 1
            else:
                pred_away_score += 1
            is_penalty = True

        # 确定胜者
        if pred_home_score > pred_away_score:
            predicted_winner = home_name
            confidence = home_win_prob
        elif pred_away_score > pred_home_score:
            predicted_winner = away_name
            confidence = away_win_prob
        else:
            if home_win_prob >= away_win_prob:
                predicted_winner = home_name
                confidence = home_win_prob
            else:
                predicted_winner = away_name
                confidence = away_win_prob

        reason_codes = self._generate_reason_codes(home_dict, away_dict)

        return {
            "home_team": home_name,
            "away_team": away_name,
            "predicted_home_score": pred_home_score,
            "predicted_away_score": pred_away_score,
            "home_win_prob": home_win_prob,
            "draw_prob": draw_prob,
            "away_win_prob": away_win_prob,
            "predicted_winner": predicted_winner,
            "confidence": round(confidence, 4),
            "is_penalty_shootout": is_penalty,
            "source": "ensemble_v2",
            "reason_codes": reason_codes,
        }

    def _predict_with_elo_fallback(
        self,
        home_team: Dict, away_team: Dict,
        home_name: str, away_name: str,
        stage: str,
    ) -> Dict[str, Any]:
        """旧版 ELO 预测（降级路径）"""
        home_elo = home_team.get("elo_rating", 1500)
        away_elo = away_team.get("elo_rating", 1500)

        outcome = self.engine.calculate_match_outcome_probabilities(home_elo, away_elo)
        home_win_prob = round(outcome["win_a"], 4)
        draw_prob = round(outcome["draw"], 4)
        away_win_prob = round(outcome["win_b"], 4)

        top_scores = self.engine.predict_score_distribution(home_elo, away_elo)
        best_score = top_scores[0]
        pred_home_score = best_score[0]
        pred_away_score = best_score[1]

        is_penalty = False
        if stage == "knockout" and pred_home_score == pred_away_score:
            if home_win_prob >= away_win_prob:
                pred_home_score += 1
            else:
                pred_away_score += 1
            is_penalty = True

        if pred_home_score > pred_away_score:
            predicted_winner = home_name
            confidence = home_win_prob
        elif pred_away_score > pred_home_score:
            predicted_winner = away_name
            confidence = away_win_prob
        else:
            if home_win_prob >= away_win_prob:
                predicted_winner = home_name
                confidence = home_win_prob
            else:
                predicted_winner = away_name
                confidence = away_win_prob

        reason_codes = self._generate_reason_codes(home_team, away_team)

        return {
            "home_team": home_name,
            "away_team": away_name,
            "predicted_home_score": pred_home_score,
            "predicted_away_score": pred_away_score,
            "home_win_prob": home_win_prob,
            "draw_prob": draw_prob,
            "away_win_prob": away_win_prob,
            "predicted_winner": predicted_winner,
            "confidence": round(confidence, 4),
            "is_penalty_shootout": is_penalty,
            "source": "agent_prediction",
            "reason_codes": reason_codes,
        }

    def _generate_reason_codes(
        self, home_team: Dict, away_team: Dict
    ) -> list[str]:
        """生成可解释的 reason_codes"""
        codes = []

        home_elo = home_team.get("elo_rating", 1500)
        away_elo = away_team.get("elo_rating", 1500)
        if abs(home_elo - away_elo) > 50:
            codes.append("ELO_ADVANTAGE")

        home_form = home_team.get("recent_win_rate", 0.5)
        away_form = away_team.get("recent_win_rate", 0.5)
        if abs(home_form - away_form) > 0.1:
            codes.append("BETTER_RECENT_FORM")

        home_atk = home_team.get("attack_score", 0.5)
        away_atk = away_team.get("attack_score", 0.5)
        if home_atk > away_atk + 0.05:
            codes.append("STRONGER_ATTACK")
        elif away_atk > home_atk + 0.05:
            codes.append("WEAKER_ATTACK")

        home_def = home_team.get("defense_score", 0.5)
        away_def = away_team.get("defense_score", 0.5)
        if home_def > away_def + 0.05:
            codes.append("BETTER_DEFENSE")

        home_power = home_team.get("power_score", 0.5)
        away_power = away_team.get("power_score", 0.5)
        if abs(home_power - away_power) > 0.05:
            codes.append("POWER_SCORE_DIFF")

        if not codes:
            codes.append("EVEN_MATCH")

        return codes

    def __del__(self):
        """清理 DB session"""
        if self._db:
            try:
                self._db.close()
            except Exception:
                pass
