"""
PyTorch V2 特征网络训练脚本
使用 FeatureAttentionMixerV2 + Focal Loss + 多指标评估

训练数据: data/training_dataset_v2.csv (67维特征)
模型输出: models/feature_network_v2_latest.pth

运行:
    python scripts/train_feature_network.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score, f1_score, brier_score_loss,
    log_loss, balanced_accuracy_score, classification_report
)
import json
import logging

from app.services.feature_network import FeatureAttentionMixerV2, FocalLoss

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


# ============================================================
# 特征列定义
# ============================================================

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


class MatchDatasetV2(Dataset):
    """V2 比赛数据集 — 67维组合特征"""

    def __init__(self, csv_file: str):
        self.df = pd.read_csv(csv_file)

        # 构建列名
        self.home_cols = [f'home_{f}' for f in TEAM_FEATURES]
        self.away_cols = [f'away_{f}' for f in TEAM_FEATURES]
        self.diff_cols = [f'diff_{f}' for f in DIFF_FEATURES]

        # 确保列存在
        all_cols = self.home_cols + self.away_cols + self.diff_cols
        for col in all_cols:
            if col not in self.df.columns:
                self.df[col] = 0.0

        # 填充 NaN
        self.df[all_cols] = self.df[all_cols].fillna(0.0)

        # 标准化 (Z-score)
        self.means = self.df[all_cols].mean()
        self.stds = self.df[all_cols].std().replace(0, 1)
        self.df[all_cols] = (self.df[all_cols] - self.means) / self.stds

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        home = self.df.iloc[idx][self.home_cols].values.astype(np.float32)
        away = self.df.iloc[idx][self.away_cols].values.astype(np.float32)
        diff = self.df.iloc[idx][self.diff_cols].values.astype(np.float32)
        combined = np.concatenate([home, away, diff])  # (67,)
        label = int(self.df.iloc[idx]['label'])
        return torch.tensor(combined), torch.tensor(label, dtype=torch.long)


def calculate_class_weights(labels: np.ndarray) -> torch.Tensor:
    """计算类别权重"""
    class_counts = np.bincount(labels, minlength=3)
    total = len(labels)
    weights = total / (3 * class_counts.astype(np.float64))
    weights = weights / weights.sum() * 3
    logger.info(f"Class counts: home_win={class_counts[0]}, draw={class_counts[1]}, away_win={class_counts[2]}")
    logger.info(f"Class weights: {weights}")
    return torch.tensor(weights, dtype=torch.float32)


def train_model(
    train_csv: str = "data/training_dataset_v2.csv",
    output_model: str = "models/feature_network_v2_latest.pth",
    epochs: int = 150,
    batch_size: int = 64,
    learning_rate: float = 0.001,
    test_size: float = 0.2
):
    logger.info(f"Loading dataset from {train_csv}")
    dataset = MatchDatasetV2(train_csv)

    # 保存特征标准化参数（供推理时使用）
    all_cols = dataset.home_cols + dataset.away_cols + dataset.diff_cols
    feature_stats = {
        'mean': dataset.means[all_cols].values.tolist(),
        'std': dataset.stds[all_cols].values.tolist(),
        'columns': all_cols,
        'feature_count': len(all_cols),
    }
    stats_path = "models/feature_stats_v2.json"
    os.makedirs(os.path.dirname(stats_path) if os.path.dirname(stats_path) else '.', exist_ok=True)
    with open(stats_path, 'w') as f:
        json.dump(feature_stats, f, indent=2)
    logger.info(f"Feature stats saved to {stats_path} ({len(all_cols)} features)")

    # 时间排序后划分（避免数据泄漏）
    dataset.df = dataset.df.sort_values('date').reset_index(drop=True)

    # 按时间: 80% train, 20% test
    split_idx = int(len(dataset) * (1 - test_size))
    train_indices = list(range(split_idx))
    test_indices = list(range(split_idx, len(dataset)))

    train_dataset = torch.utils.data.Subset(dataset, train_indices)
    test_dataset = torch.utils.data.Subset(dataset, test_indices)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)

    # 类别权重
    train_labels = dataset.df.iloc[train_indices]['label'].values
    class_weights = calculate_class_weights(train_labels)

    # 创建 V2 模型
    model = FeatureAttentionMixerV2(team_dim=25, input_dim=50)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = model.to(device)
    class_weights = class_weights.to(device)

    logger.info(f"Using device: {device}")
    logger.info(f"Model: FeatureAttentionMixerV2")
    logger.info(f"Parameters: {sum(p.numel() for p in model.parameters()):,}")

    # Focal Loss + class weights
    criterion = FocalLoss(alpha=class_weights, gamma=2.0)

    optimizer = optim.Adam(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=1e-6)

    # 训练循环
    best_val_loss = float('inf')
    train_losses = []
    val_losses = []

    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        all_preds = []
        all_labels = []

        for combined_feats, labels in train_loader:
            combined_feats = combined_feats.to(device)
            labels = labels.to(device)

            optimizer.zero_grad()
            logits = model(combined_feats)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()

            running_loss += loss.item()
            _, predicted = torch.max(logits.data, 1)
            all_preds.extend(predicted.cpu().numpy())
            all_labels.extend(labels.cpu().numpy())

        train_loss = running_loss / len(train_loader)
        train_losses.append(train_loss)

        # 验证
        model.eval()
        val_loss = 0.0
        val_preds = []
        val_labels = []
        val_probs = []

        with torch.no_grad():
            for combined_feats, labels in test_loader:
                combined_feats = combined_feats.to(device)
                labels = labels.to(device)

                logits = model(combined_feats)
                loss = criterion(logits, labels)
                val_loss += loss.item()

                probs = torch.softmax(logits, dim=1)
                _, predicted = torch.max(logits.data, 1)
                val_preds.extend(predicted.cpu().numpy())
                val_labels.extend(labels.cpu().numpy())
                val_probs.extend(probs.cpu().numpy())

        val_loss = val_loss / len(test_loader)
        val_losses.append(val_loss)

        scheduler.step()

        # 保存最佳模型
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), output_model)
            logger.info(f"Best model saved (val_loss={best_val_loss:.4f})")

        if (epoch + 1) % 10 == 0:
            train_acc = accuracy_score(all_labels, all_preds)
            val_acc = accuracy_score(val_labels, val_preds)
            val_f1 = f1_score(val_labels, val_preds, average='macro')
            logger.info(
                f"Epoch [{epoch+1}/{epochs}] "
                f"Train: {train_loss:.4f}/{train_acc:.4f} | "
                f"Val: {val_loss:.4f}/{val_acc:.4f}/{val_f1:.4f}"
            )

    # ========== 最终评估 ==========
    logger.info("\n=== Final Evaluation ===")

    val_preds_arr = np.array(val_preds)
    val_labels_arr = np.array(val_labels)
    val_probs_arr = np.array(val_probs)

    final_acc = accuracy_score(val_labels_arr, val_preds_arr)
    final_f1_macro = f1_score(val_labels_arr, val_preds_arr, average='macro')
    final_balanced_acc = balanced_accuracy_score(val_labels_arr, val_preds_arr)
    final_brier = np.mean(np.sum((val_probs_arr - np.eye(3)[val_labels_arr]) ** 2, axis=1))
    final_logloss = log_loss(val_labels_arr, val_probs_arr, labels=[0, 1, 2])

    logger.info(f"Accuracy:          {final_acc:.4f}")
    logger.info(f"Macro F1:          {final_f1_macro:.4f}")
    logger.info(f"Balanced Accuracy: {final_balanced_acc:.4f}")
    logger.info(f"Brier Score:       {final_brier:.4f}")
    logger.info(f"Log Loss:          {final_logloss:.4f}")
    logger.info(f"\nClassification Report:")
    logger.info(classification_report(
        val_labels_arr, val_preds_arr,
        target_names=['home_win', 'draw', 'away_win']
    ))

    # 保存结果
    results = {
        'model_version': 'v2',
        'epochs': epochs,
        'best_val_loss': best_val_loss,
        'final_val_accuracy': final_acc,
        'final_macro_f1': final_f1_macro,
        'final_balanced_accuracy': final_balanced_acc,
        'final_brier_score': final_brier,
        'final_log_loss': final_logloss,
        'class_weights': class_weights.cpu().numpy().tolist(),
        'feature_count': 67,
        'input_dim': 50,
        'train_samples': len(train_indices),
        'test_samples': len(test_indices),
        'train_losses': train_losses,
        'val_losses': val_losses
    }

    results_file = output_model.replace('.pth', '_results.json')
    os.makedirs(os.path.dirname(results_file) if os.path.dirname(results_file) else '.', exist_ok=True)
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)

    logger.info(f"Results saved to {results_file}")

    return results


if __name__ == "__main__":
    results = train_model(
        train_csv="data/training_dataset_v2.csv",
        output_model="models/feature_network_v2_latest.pth",
        epochs=150,
        batch_size=64,
        learning_rate=0.001
    )

    print("\n=== Training Completed ===")
    print(f"Features:     {results['feature_count']}")
    print(f"Accuracy:     {results['final_val_accuracy']:.4f}")
    print(f"Macro F1:     {results['final_macro_f1']:.4f}")
    print(f"Balanced Acc: {results['final_balanced_accuracy']:.4f}")
    print(f"Brier Score:  {results['final_brier_score']:.4f}")
    print(f"Log Loss:     {results['final_log_loss']:.4f}")
