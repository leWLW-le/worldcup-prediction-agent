"""
XGBoost 树模型预测器
输入: 67维组合特征 (home_25 + away_25 + diff_17)
输出: 三分类概率 [home_win, draw, away_win]
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pickle
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# 特征列定义（与 train_feature_network.py 一致）
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


class TreePredictor:
    """XGBoost 三分类预测器"""

    def __init__(self, model_path: str = "models/tree_predictor.pkl"):
        self.model_path = model_path
        self.model = None
        self.scaler = None  # 标准化参数

    def _build_features(self, csv_row: pd.Series) -> np.ndarray:
        """从 CSV 行构建 67 维特征向量"""
        home = [csv_row.get(f'home_{f}', 0.0) for f in TEAM_FEATURES]
        away = [csv_row.get(f'away_{f}', 0.0) for f in TEAM_FEATURES]
        diff = [csv_row.get(f'diff_{f}', 0.0) for f in DIFF_FEATURES]
        return np.array(home + away + diff, dtype=np.float32)

    def _build_features_from_dict(self, features: Dict[str, float]) -> np.ndarray:
        """从特征字典构建 67 维特征向量"""
        home = [features.get(f'home_{f}', 0.0) for f in TEAM_FEATURES]
        away = [features.get(f'away_{f}', 0.0) for f in TEAM_FEATURES]
        diff = [features.get(f'diff_{f}', 0.0) for f in DIFF_FEATURES]
        return np.array(home + away + diff, dtype=np.float32)

    def train(self, csv_file: str = "data/training_dataset_v2.csv"):
        """训练 XGBoost 模型"""
        import xgboost as xgb
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import (
            accuracy_score, f1_score, balanced_accuracy_score,
            brier_score_loss, log_loss, classification_report
        )

        logger.info(f"Loading training data from {csv_file}")
        df = pd.read_csv(csv_file)

        # 构建特征矩阵
        home_cols = [f'home_{f}' for f in TEAM_FEATURES]
        away_cols = [f'away_{f}' for f in TEAM_FEATURES]
        diff_cols = [f'diff_{f}' for f in DIFF_FEATURES]
        feature_cols = home_cols + away_cols + diff_cols

        # 确保列存在
        for col in feature_cols:
            if col not in df.columns:
                df[col] = 0.0

        X = df[feature_cols].fillna(0.0).values
        y = df['label'].values

        # 时间排序后划分
        if 'date' in df.columns:
            df = df.sort_values('date')
            X = df[feature_cols].fillna(0.0).values
            y = df['label'].values

        split_idx = int(len(X) * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        # 标准化
        self.scaler = {
            'mean': X_train.mean(axis=0),
            'std': np.where(X_train.std(axis=0) == 0, 1, X_train.std(axis=0))
        }
        X_train_norm = (X_train - self.scaler['mean']) / self.scaler['std']
        X_test_norm = (X_test - self.scaler['mean']) / self.scaler['std']

        # 计算类别权重
        class_counts = np.bincount(y_train, minlength=3)
        total = len(y_train)
        scale_pos_weight = {i: total / (3 * class_counts[i]) for i in range(3)}

        logger.info(f"Train: {len(X_train)}, Test: {len(X_test)}")
        logger.info(f"Class counts: {class_counts}")

        # 训练 XGBoost
        self.model = xgb.XGBClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            objective='multi:softprob',
            num_class=3,
            eval_metric='mlogloss',
            use_label_encoder=False,
            random_state=42,
            n_jobs=-1
        )

        self.model.fit(
            X_train_norm, y_train,
            eval_set=[(X_test_norm, y_test)],
            verbose=50
        )

        # 评估
        y_pred = self.model.predict(X_test_norm)
        y_prob = self.model.predict_proba(X_test_norm)

        acc = accuracy_score(y_test, y_pred)
        f1_macro = f1_score(y_test, y_pred, average='macro')
        balanced_acc = balanced_accuracy_score(y_test, y_pred)
        brier = np.mean(np.sum((y_prob - np.eye(3)[y_test]) ** 2, axis=1))
        ll = log_loss(y_test, y_prob, labels=[0, 1, 2])

        logger.info(f"\n=== XGBoost Evaluation ===")
        logger.info(f"Accuracy:          {acc:.4f}")
        logger.info(f"Macro F1:          {f1_macro:.4f}")
        logger.info(f"Balanced Accuracy: {balanced_acc:.4f}")
        logger.info(f"Brier Score:       {brier:.4f}")
        logger.info(f"Log Loss:          {ll:.4f}")
        logger.info(f"\n{classification_report(y_test, y_pred, target_names=['home_win', 'draw', 'away_win'])}")

        # 保存模型
        self.save()

        return {
            'accuracy': acc,
            'macro_f1': f1_macro,
            'balanced_accuracy': balanced_acc,
            'brier_score': brier,
            'log_loss': ll,
            'train_samples': len(X_train),
            'test_samples': len(X_test),
            'feature_count': len(feature_cols)
        }

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        """
        预测三分类概率

        Args:
            features: (67,) 或 (n, 67) 特征向量

        Returns:
            (3,) 或 (n, 3) 概率 [home_win, draw, away_win]
        """
        if self.model is None:
            self.load()

        if features.ndim == 1:
            features = features.reshape(1, -1)

        # 标准化
        if self.scaler is not None:
            features = (features - self.scaler['mean']) / self.scaler['std']

        probs = self.model.predict_proba(features)
        return probs

    def save(self):
        """保存模型"""
        os.makedirs(os.path.dirname(self.model_path) if os.path.dirname(self.model_path) else '.', exist_ok=True)
        data = {
            'model': self.model,
            'scaler': self.scaler
        }
        with open(self.model_path, 'wb') as f:
            pickle.dump(data, f)
        logger.info(f"Model saved to {self.model_path}")

    def load(self):
        """加载模型"""
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model not found: {self.model_path}")
        with open(self.model_path, 'rb') as f:
            data = pickle.load(f)
        self.model = data['model']
        self.scaler = data['scaler']
        logger.info(f"Model loaded from {self.model_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

    predictor = TreePredictor()
    results = predictor.train()

    print("\n=== XGBoost Training Completed ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
