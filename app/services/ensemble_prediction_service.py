"""
集成预测服务 V2
融合 ELO、神经网络(V2)、XGBoost、泊松和路径概率模型

新权重:
- ELO: 25%
- Neural Network (V2): 30%
- XGBoost: 20%
- Poisson: 15%
- Path: 10%
"""
from typing import Optional, Dict
import os
import logging
import numpy as np

from sqlalchemy.orm import Session
from app.models.schemas import Team
from app.services.prediction_service import PredictionService

logger = logging.getLogger(__name__)


# 特征列定义（与训练脚本一致）
TEAM_FEATURES = [
    'elo_rating', 'elo_change_1year', 'elo_change_3year',
    'world_cup_experience', 'major_tournament_points',
    'wins_5', 'draws_5', 'losses_5',
    'goals_for_5', 'goals_against_5', 'win_rate_5',
    'wins_10', 'draws_10', 'losses_10',
    'goals_for_10', 'goals_against_10', 'win_rate_10',
    'attack_score', 'avg_goals_scored', 'shots_estimate',
    'big_win_rate', 'scoring_consistency',
    'defense_score', 'avg_goals_conceded', 'clean_sheet_rate',
]

DIFF_FEATURES = [
    'elo_rating', 'elo_change_1year', 'elo_change_3year',
    'world_cup_experience', 'major_tournament_points',
    'wins_5', 'draws_5', 'losses_5',
    'goals_for_5', 'goals_against_5', 'win_rate_5',
    'wins_10', 'draws_10', 'losses_10',
    'goals_for_10', 'goals_against_10', 'win_rate_10',
]


class EnsemblePredictionService(PredictionService):
    """
    集成预测服务 V2

    融合五个模型:
    - ELO: 25%
    - Neural Network (V2): 30%
    - XGBoost: 20%
    - Poisson: 15%
    - Path: 10%
    """

    def __init__(
        self,
        db: Session,
        nn_model_path: Optional[str] = None,
        tree_model_path: Optional[str] = None,
        feature_stats_path: Optional[str] = None,
    ):
        super().__init__(db)
        self.nn_model_path = nn_model_path or "models/feature_network_v2_latest.pth"
        self.tree_model_path = tree_model_path or "models/tree_predictor.pkl"
        self.feature_stats_path = feature_stats_path or "models/feature_stats_v2.json"
        self._nn_model = None
        self._tree_model = None
        self._feature_stats = None
        self._feature_builder = None

    def _get_feature_builder(self):
        """懒加载特征构建器"""
        if self._feature_builder is None:
            try:
                from app.services.advanced_feature_builder import AdvancedFeatureBuilder
                self._feature_builder = AdvancedFeatureBuilder(db=self.db)
            except Exception as e:
                logger.warning(f"Failed to load AdvancedFeatureBuilder: {e}")
        return self._feature_builder

    def _load_feature_stats(self) -> dict:
        """加载特征标准化参数"""
        if self._feature_stats is not None:
            return self._feature_stats
        import json
        if os.path.exists(self.feature_stats_path):
            with open(self.feature_stats_path, 'r') as f:
                self._feature_stats = json.load(f)
        else:
            self._feature_stats = {}
        return self._feature_stats

    def _build_team_features_dict(self, team: Team, is_home: bool = True) -> dict:
        """为单支球队构建 25 维特征"""
        builder = self._get_feature_builder()
        if builder is not None:
            try:
                feats = builder.build_team_features(team.id)
                # 只取 TEAM_FEATURES 中定义的特征
                return {k: feats.get(k, 0.0) for k in TEAM_FEATURES}
            except Exception as e:
                logger.warning(f"Feature builder failed for {team.name}: {e}")

        # Fallback: 使用数据库中的基本信息
        elo = team.current_elo or 1500.0
        base = {
            'elo_rating': elo,
            'elo_change_1year': 0.0,
            'elo_change_3year': 0.0,
            'world_cup_experience': 0,
            'major_tournament_points': 0.0,
            'wins_5': 2, 'draws_5': 1, 'losses_5': 2,
            'goals_for_5': 5.0, 'goals_against_5': 4.0, 'win_rate_5': 0.4,
            'wins_10': 4, 'draws_10': 3, 'losses_10': 3,
            'goals_for_10': 12.0, 'goals_against_10': 9.0, 'win_rate_10': 0.4,
            'attack_score': 1.0, 'avg_goals_scored': 1.2, 'shots_estimate': 3.0,
            'big_win_rate': 0.2, 'scoring_consistency': 0.7,
            'defense_score': 0.5, 'avg_goals_conceded': 1.0, 'clean_sheet_rate': 0.3,
        }
        return base

    def _build_combined_features(self, home_team: Team, away_team: Team) -> np.ndarray:
        """构建 67 维组合特征向量"""
        home_feats = self._build_team_features_dict(home_team, is_home=True)
        away_feats = self._build_team_features_dict(away_team, is_home=False)

        home_vec = np.array([home_feats.get(f, 0.0) for f in TEAM_FEATURES], dtype=np.float32)
        away_vec = np.array([away_feats.get(f, 0.0) for f in TEAM_FEATURES], dtype=np.float32)
        diff_vec = np.array([home_feats.get(f, 0.0) - away_feats.get(f, 0.0) for f in DIFF_FEATURES], dtype=np.float32)

        combined = np.concatenate([home_vec, away_vec, diff_vec])

        # 标准化
        stats = self._load_feature_stats()
        if stats and 'mean' in stats:
            mean = np.array(stats['mean'], dtype=np.float32)
            std = np.array(stats['std'], dtype=np.float32)
            if len(mean) == len(combined):
                combined = (combined - mean) / std

        return combined

    def predict_with_ensemble(self, home_team: Team, away_team: Team) -> Dict:
        """使用集成模型预测比赛"""
        # 1. ELO 预测
        elo_pred = self._predict_with_elo(home_team, away_team)

        # 2. Poisson 预测
        poisson_pred = self._predict_with_poisson(home_team, away_team)

        # 3. NN V2 预测
        nn_pred = None
        try:
            nn_pred = self._predict_with_nn_v2(home_team, away_team)
        except Exception as e:
            logger.warning(f"NN V2 prediction failed: {e}")

        # 4. XGBoost 预测
        xgb_pred = None
        try:
            xgb_pred = self._predict_with_xgboost(home_team, away_team)
        except Exception as e:
            logger.warning(f"XGBoost prediction failed: {e}")

        # 5. 路径概率（简化：使用 ELO）
        path_pred = elo_pred

        # 确定可用模型和权重
        available_models = {}
        available_models['elo'] = elo_pred
        available_models['poisson'] = poisson_pred
        available_models['path'] = path_pred

        if nn_pred:
            available_models['nn'] = nn_pred
        if xgb_pred:
            available_models['xgb'] = xgb_pred

        # 目标权重
        target_weights = {'elo': 0.25, 'nn': 0.30, 'xgb': 0.20, 'poisson': 0.15, 'path': 0.10}

        # 重新分配权重（只考虑可用模型）
        weights = {}
        total_target = sum(target_weights.get(k, 0) for k in available_models)
        for k in available_models:
            weights[k] = target_weights.get(k, 0) / total_target if total_target > 0 else 1.0 / len(available_models)

        # 融合概率（优先使用概率输出）
        home_win_prob = sum(
            self._get_prob(available_models[k], 'home_win') * weights[k]
            for k in available_models
        )
        draw_prob = sum(
            self._get_prob(available_models[k], 'draw') * weights[k]
            for k in available_models
        )
        away_win_prob = sum(
            self._get_prob(available_models[k], 'away_win') * weights[k]
            for k in available_models
        )

        # 归一化概率
        total_prob = home_win_prob + draw_prob + away_win_prob
        if total_prob > 0:
            home_win_prob /= total_prob
            draw_prob /= total_prob
            away_win_prob /= total_prob

        # 转换为比分
        home_elo = home_team.current_elo or 1500
        away_elo = away_team.current_elo or 1500
        home_expected = 1.5 + (home_elo - away_elo) / 400
        away_expected = 1.5 - (home_elo - away_elo) / 400
        home_score = int(round(max(0, home_expected)))
        away_score = int(round(max(0, away_expected)))

        confidence = max(home_win_prob, draw_prob, away_win_prob)

        reasoning = (
            f"集成预测V2 ({', '.join(f'{k}:{v:.0%}' for k, v in weights.items())})\n"
            f"ELO: {home_team.name}({home_elo:.0f}) vs {away_team.name}({away_elo:.0f})\n"
            f"概率: 主胜{home_win_prob:.1%} 平{draw_prob:.1%} 客胜{away_win_prob:.1%}"
        )

        return {
            "home_score": home_score,
            "away_score": away_score,
            "confidence": round(confidence, 3),
            "reasoning": reasoning,
            "ensemble_weights": weights,
            "probabilities": {
                "home_win": home_win_prob,
                "draw": draw_prob,
                "away_win": away_win_prob,
            },
            "model_predictions": {
                "elo": elo_pred,
                "poisson": poisson_pred,
                "neural_network_v2": nn_pred,
                "xgboost": xgb_pred,
            }
        }

    def _get_prob(self, pred: dict, key: str) -> float:
        """从预测结果中提取概率"""
        if 'probabilities' in pred:
            probs = pred['probabilities']
            if key in probs:
                return probs[key]
            # 兼容旧格式
            if key == 'home_win' and 'win_a' in probs:
                return probs['win_a']
            if key == 'away_win' and 'win_b' in probs:
                return probs['win_b']

        # 从比分推断
        hs = pred.get('home_score', 1)
        aws = pred.get('away_score', 1)
        total = hs + aws
        if total == 0:
            return 0.33
        if key == 'home_win':
            return hs / (total + 1)
        elif key == 'away_win':
            return aws / (total + 1)
        else:  # draw
            return 0.25

    def _predict_with_nn_v2(self, home_team: Team, away_team: Team) -> Dict:
        """使用 V2 神经网络预测"""
        import torch
        from app.services.feature_network import FeatureAttentionMixerV2

        if self._nn_model is None:
            if not os.path.exists(self.nn_model_path):
                raise FileNotFoundError(f"NN model not found: {self.nn_model_path}")
            self._nn_model = FeatureAttentionMixerV2(team_dim=25, input_dim=50)
            self._nn_model.load_state_dict(torch.load(self.nn_model_path, map_location='cpu'))
            self._nn_model.eval()

        combined = self._build_combined_features(home_team, away_team)
        combined_tensor = torch.tensor(combined.reshape(1, -1), dtype=torch.float32)

        with torch.no_grad():
            logits = self._nn_model(combined_tensor)
            probs = torch.softmax(logits, dim=1).numpy()[0]

        home_elo = home_team.current_elo or 1500
        away_elo = away_team.current_elo or 1500
        home_expected = 1.5 + (home_elo - away_elo) / 400
        away_expected = 1.5 - (home_elo - away_elo) / 400

        return {
            "home_score": int(round(max(0, home_expected))),
            "away_score": int(round(max(0, away_expected))),
            "confidence": float(max(probs)),
            "probabilities": {
                "home_win": float(probs[0]),
                "draw": float(probs[1]),
                "away_win": float(probs[2]),
            }
        }

    def _predict_with_xgboost(self, home_team: Team, away_team: Team) -> Dict:
        """使用 XGBoost 预测"""
        from app.models.tree_predictor import TreePredictor

        if self._tree_model is None:
            self._tree_model = TreePredictor(model_path=self.tree_model_path)
            self._tree_model.load()

        combined = self._build_combined_features(home_team, away_team)
        probs = self._tree_model.predict_proba(combined)[0]

        home_elo = home_team.current_elo or 1500
        away_elo = away_team.current_elo or 1500
        home_expected = 1.5 + (home_elo - away_elo) / 400
        away_expected = 1.5 - (home_elo - away_elo) / 400

        return {
            "home_score": int(round(max(0, home_expected))),
            "away_score": int(round(max(0, away_expected))),
            "confidence": float(max(probs)),
            "probabilities": {
                "home_win": float(probs[0]),
                "draw": float(probs[1]),
                "away_win": float(probs[2]),
            }
        }
