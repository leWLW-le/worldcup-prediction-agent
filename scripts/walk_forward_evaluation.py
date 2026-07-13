"""
Walk Forward 时间序列回测

训练: 2010-2018 → 验证: 2019-2020
训练: 2010-2020 → 验证: 2021-2022
训练: 2010-2022 → 验证: 2023-2024

输出每阶段: accuracy, macro_f1, balanced_accuracy, brier_score, log_loss

运行:
    python scripts/walk_forward_evaluation.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
import torch.nn.functional as F
import numpy as np
import pandas as pd
import logging
from sklearn.metrics import (
    accuracy_score, f1_score, balanced_accuracy_score,
    brier_score_loss, log_loss, classification_report
)

from app.services.feature_network import FeatureAttentionMixerV2, FocalLoss

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
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


def prepare_features(df: pd.DataFrame) -> tuple:
    """准备特征矩阵"""
    home_cols = [f'home_{f}' for f in TEAM_FEATURES]
    away_cols = [f'away_{f}' for f in TEAM_FEATURES]
    diff_cols = [f'diff_{f}' for f in DIFF_FEATURES]
    feature_cols = home_cols + away_cols + diff_cols

    for col in feature_cols:
        if col not in df.columns:
            df[col] = 0.0

    X = df[feature_cols].fillna(0.0).values.astype(np.float32)
    y = df['label'].values.astype(np.int64)

    return X, y, feature_cols


def standardize(X_train: np.ndarray, X_test: np.ndarray) -> tuple:
    """Z-score 标准化"""
    mean = X_train.mean(axis=0)
    std = np.where(X_train.std(axis=0) == 0, 1, X_train.std(axis=0))
    return (X_train - mean) / std, (X_test - mean) / std, mean, std


def train_and_evaluate(
    X_train: np.ndarray, y_train: np.ndarray,
    X_test: np.ndarray, y_test: np.ndarray,
    phase_name: str
) -> dict:
    """训练并评估一个阶段"""
    logger.info(f"\n{'='*60}")
    logger.info(f"Phase: {phase_name}")
    logger.info(f"Train: {len(X_train)}, Test: {len(X_test)}")

    # 标准化
    X_train_norm, X_test_norm, mean, std = standardize(X_train, X_test)

    # 类别权重
    class_counts = np.bincount(y_train, minlength=3)
    total = len(y_train)
    weights = total / (3 * class_counts.astype(np.float64))
    weights = weights / weights.sum() * 3
    class_weights = torch.tensor(weights, dtype=torch.float32)

    # 创建模型
    model = FeatureAttentionMixerV2(team_dim=25, input_dim=50)
    device = torch.device('cpu')
    model = model.to(device)

    criterion = FocalLoss(alpha=class_weights, gamma=2.0)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-4)

    # 训练 80 epochs
    batch_size = 64
    best_val_loss = float('inf')
    best_state = None

    for epoch in range(80):
        model.train()
        indices = np.random.permutation(len(X_train_norm))

        for start in range(0, len(X_train_norm), batch_size):
            batch_idx = indices[start:start+batch_size]
            X_batch = torch.tensor(X_train_norm[batch_idx], dtype=torch.float32)
            y_batch = torch.tensor(y_train[batch_idx], dtype=torch.long)

            optimizer.zero_grad()
            logits = model(X_batch)
            loss = criterion(logits, y_batch)
            loss.backward()
            optimizer.step()

        # 验证
        model.eval()
        with torch.no_grad():
            val_logits = model(torch.tensor(X_test_norm, dtype=torch.float32))
            val_loss = criterion(val_logits, torch.tensor(y_test, dtype=torch.long)).item()

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}

    # 加载最佳模型
    if best_state is not None:
        model.load_state_dict(best_state)

    # 最终评估
    model.eval()
    with torch.no_grad():
        test_logits = model(torch.tensor(X_test_norm, dtype=torch.float32))
        test_probs = torch.softmax(test_logits, dim=1).numpy()
        test_preds = np.argmax(test_probs, axis=1)

    acc = accuracy_score(y_test, test_preds)
    f1_macro = f1_score(y_test, test_preds, average='macro')
    bal_acc = balanced_accuracy_score(y_test, test_preds)
    brier = np.mean(np.sum((test_probs - np.eye(3)[y_test]) ** 2, axis=1))
    ll = log_loss(y_test, test_probs, labels=[0, 1, 2])

    logger.info(f"  Accuracy:          {acc:.4f}")
    logger.info(f"  Macro F1:          {f1_macro:.4f}")
    logger.info(f"  Balanced Accuracy: {bal_acc:.4f}")
    logger.info(f"  Brier Score:       {brier:.4f}")
    logger.info(f"  Log Loss:          {ll:.4f}")
    logger.info(f"\n{classification_report(y_test, test_preds, target_names=['home_win', 'draw', 'away_win'])}")

    return {
        'phase': phase_name,
        'train_samples': len(X_train),
        'test_samples': len(X_test),
        'accuracy': acc,
        'macro_f1': f1_macro,
        'balanced_accuracy': bal_acc,
        'brier_score': brier,
        'log_loss': ll,
    }


def main():
    csv_file = "data/training_dataset_v2.csv"
    logger.info(f"Loading data from {csv_file}")

    df = pd.read_csv(csv_file)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)

    X, y, feature_cols = prepare_features(df)

    # Walk Forward 分割
    phases = [
        ("Train 2010-2018 / Val 2019-2020",
         df['date'] < '2019-01-01',
         (df['date'] >= '2019-01-01') & (df['date'] < '2021-01-01')),
        ("Train 2010-2020 / Val 2021-2022",
         df['date'] < '2021-01-01',
         (df['date'] >= '2021-01-01') & (df['date'] < '2023-01-01')),
        ("Train 2010-2022 / Val 2023-2024",
         df['date'] < '2023-01-01',
         df['date'] >= '2023-01-01'),
    ]

    results = []
    for name, train_mask, val_mask in phases:
        X_train, y_train = X[train_mask.values], y[train_mask.values]
        X_val, y_val = X[val_mask.values], y[val_mask.values]

        if len(X_train) == 0 or len(X_val) == 0:
            logger.warning(f"Skipping phase {name}: empty train or val set")
            continue

        result = train_and_evaluate(X_train, y_train, X_val, y_val, name)
        results.append(result)

    # 汇总
    print("\n" + "=" * 70)
    print("Walk Forward 回测汇总")
    print("=" * 70)
    for r in results:
        print(f"\n{r['phase']}:")
        print(f"  Train={r['train_samples']}, Test={r['test_samples']}")
        print(f"  Accuracy={r['accuracy']:.4f}, Macro F1={r['macro_f1']:.4f}, "
              f"Balanced Acc={r['balanced_accuracy']:.4f}")
        print(f"  Brier={r['brier_score']:.4f}, Log Loss={r['log_loss']:.4f}")

    # 保存结果
    import json
    output_file = "data/walk_forward_results.json"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    logger.info(f"\nResults saved to {output_file}")

    return results


if __name__ == "__main__":
    main()
