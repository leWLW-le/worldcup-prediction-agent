"""
构建扩展特征训练数据集 training_dataset_v2.csv

使用 AdvancedFeatureBuilder + MatchFeatureBuilder 生成 67 维特征 + 标签

运行:
    python scripts/build_extended_features.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import pandas as pd
from app.services.match_feature_builder import MatchFeatureBuilder

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def main():
    logger.info("=== 构建扩展特征训练数据集 ===")

    builder = MatchFeatureBuilder()

    print(f"每队特征数: {builder.get_team_feature_count()}")
    print(f"总特征数 (home+away+diff+env): {builder.get_total_feature_count()}")

    # 构建数据集
    df = builder.build_dataset(output_csv="data/training_dataset_v2.csv")

    print(f"\n=== 数据集构建完成 ===")
    print(f"形状: {df.shape}")
    print(f"行数: {len(df)}")
    print(f"列数: {len(df.columns)}")

    # 标签分布
    label_counts = df['label'].value_counts().sort_index()
    total = len(df)
    print(f"\n标签分布:")
    print(f"  home_win (0): {label_counts.get(0, 0)} ({label_counts.get(0, 0)/total*100:.1f}%)")
    print(f"  draw     (1): {label_counts.get(1, 0)} ({label_counts.get(1, 0)/total*100:.1f}%)")
    print(f"  away_win (2): {label_counts.get(2, 0)} ({label_counts.get(2, 0)/total*100:.1f}%)")

    # 缺失率
    missing = df.isnull().sum().sum() / (len(df) * len(df.columns)) * 100
    print(f"\n缺失率: {missing:.2f}%")

    # 特征列（不含元数据和标签）
    feature_cols = [c for c in df.columns if c not in ['match_id', 'date', 'label']]
    print(f"特征列数: {len(feature_cols)}")

    # 检查 home/diff 列
    home_cols = [c for c in df.columns if c.startswith('home_')]
    away_cols = [c for c in df.columns if c.startswith('away_')]
    diff_cols = [c for c in df.columns if c.startswith('diff_')]
    env_cols = ['neutral_venue', 'competition_weight', 'world_cup_match', 'knockout_stage']
    print(f"  home_*: {len(home_cols)}")
    print(f"  away_*: {len(away_cols)}")
    print(f"  diff_*: {len(diff_cols)}")
    print(f"  env: {len(env_cols)}")

    return df


if __name__ == "__main__":
    main()
