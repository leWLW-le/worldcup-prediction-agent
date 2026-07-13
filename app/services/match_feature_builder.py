"""
比赛特征构建器
为每场比赛生成 A队特征 + B队特征 + 差值特征

最终输入维度：
- A队特征: 17个
- B队特征: 17个
- 差值特征: 17个
- 总计: 51个特征
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging

from app.services.advanced_feature_builder import AdvancedFeatureBuilder

logger = logging.getLogger(__name__)


class MatchFeatureBuilder:
    """比赛特征构建器"""
    
    # 每队特征名（不含比赛环境，环境为比赛级别）
    TEAM_FEATURE_COLS = [
        # 基础实力 (5)
        'elo_rating', 'elo_change_1year', 'elo_change_3year',
        'world_cup_experience', 'major_tournament_points',
        # 近期状态5场 (6)
        'wins_5', 'draws_5', 'losses_5',
        'goals_for_5', 'goals_against_5', 'win_rate_5',
        # 近期状态10场 (6)
        'wins_10', 'draws_10', 'losses_10',
        'goals_for_10', 'goals_against_10', 'win_rate_10',
        # 进攻能力 (5)
        'attack_score', 'avg_goals_scored', 'shots_estimate',
        'big_win_rate', 'scoring_consistency',
        # 防守能力 (5)
        'defense_score', 'avg_goals_conceded', 'clean_sheet_rate',
        'concede_consistency', 'comeback_defense_score',
        # 强队表现 (3)
        'strong_opponent_win_rate', 'top20_team_performance',
        'tournament_performance_score',
    ]
    
    # 比赛环境特征
    MATCH_ENV_COLS = [
        'neutral_venue', 'competition_weight',
        'world_cup_match', 'knockout_stage'
    ]
    
    def __init__(self, feature_builder: Optional[AdvancedFeatureBuilder] = None):
        self.feature_builder = feature_builder or AdvancedFeatureBuilder()
    
    def build_match_features(self, match_row: dict, team_features: Dict) -> Dict[str, float]:
        """
        为单场比赛生成完整特征
        
        Args:
            match_row: 比赛数据行（含 home_team_id, away_team_id, date 等）
            team_features: 预计算的球队特征 {team_id: {feature_name: value}}
            
        Returns:
            比赛特征字典
        """
        home_id = match_row['home_team_id']
        away_id = match_row['away_team_id']
        
        home_feats = team_features.get(home_id, {})
        away_feats = team_features.get(away_id, {})
        
        result = {}
        
        # A队特征 (home)
        for col in self.TEAM_FEATURE_COLS:
            result[f'home_{col}'] = home_feats.get(col, 0.0)
        
        # B队特征 (away)
        for col in self.TEAM_FEATURE_COLS:
            result[f'away_{col}'] = away_feats.get(col, 0.0)
        
        # 差值特征
        for col in self.TEAM_FEATURE_COLS:
            h_val = home_feats.get(col, 0.0)
            a_val = away_feats.get(col, 0.0)
            result[f'diff_{col}'] = h_val - a_val
        
        # 比赛环境特征
        env_feats = AdvancedFeatureBuilder.calc_match_environment(match_row)
        for col in self.MATCH_ENV_COLS:
            result[col] = env_feats.get(col, 0.0)
        
        return result
    
    def build_dataset(self, output_csv: str = "data/training_dataset_v2.csv") -> pd.DataFrame:
        """
        构建完整训练数据集
        
        Returns:
            DataFrame with all match features + label
        """
        df = self.feature_builder.matches_df
        logger.info(f"Building match features for {len(df)} matches...")
        
        # 预计算所有球队特征（使用每场比赛前的数据避免数据泄漏）
        # 为效率起见，按时间分段计算
        all_rows = []
        
        # 按日期排序
        df = df.sort_values('date').reset_index(drop=True)
        
        # 分批计算特征（每100场更新一次球队特征）
        batch_size = 100
        team_features = None
        
        for i, row in df.iterrows():
            # 每batch_size场更新一次特征
            if i % batch_size == 0 or team_features is None:
                team_features = self.feature_builder.build_all_team_features(
                    before_date=row['date']
                )
            
            # 构建比赛特征
            match_dict = row.to_dict()
            feats = self.build_match_features(match_dict, team_features)
            
            # 添加标签
            if row['result'] == 'home_win':
                feats['label'] = 0
            elif row['result'] == 'draw':
                feats['label'] = 1
            elif row['result'] == 'away_win':
                feats['label'] = 2
            else:
                continue
            
            # 添加元数据
            feats['match_id'] = row['id']
            feats['date'] = row['date']
            
            all_rows.append(feats)
            
            if (i + 1) % 500 == 0:
                logger.info(f"Processed {i + 1}/{len(df)} matches")
        
        result_df = pd.DataFrame(all_rows)
        
        # 保存
        os.makedirs(os.path.dirname(output_csv) if os.path.dirname(output_csv) else '.', exist_ok=True)
        result_df.to_csv(output_csv, index=False)
        logger.info(f"Training dataset v2 saved to {output_csv}")
        logger.info(f"Shape: {result_df.shape}")
        logger.info(f"Columns: {list(result_df.columns)}")
        
        # 统计
        label_counts = result_df['label'].value_counts()
        logger.info(f"Label distribution: home_win={label_counts.get(0, 0)}, "
                    f"draw={label_counts.get(1, 0)}, away_win={label_counts.get(2, 0)}")
        
        return result_df
    
    def get_all_feature_names(self) -> List[str]:
        """返回所有特征名（不含元数据和标签）"""
        names = []
        
        # Home features
        for col in self.TEAM_FEATURE_COLS:
            names.append(f'home_{col}')
        
        # Away features
        for col in self.TEAM_FEATURE_COLS:
            names.append(f'away_{col}')
        
        # Diff features
        for col in self.TEAM_FEATURE_COLS:
            names.append(f'diff_{col}')
        
        # Match environment
        names.extend(self.MATCH_ENV_COLS)
        
        return names
    
    def get_team_feature_count(self) -> int:
        """每队特征数"""
        return len(self.TEAM_FEATURE_COLS)
    
    def get_total_feature_count(self) -> int:
        """总特征数"""
        return len(self.get_all_feature_names())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    builder = MatchFeatureBuilder()
    
    print(f"每队特征数: {builder.get_team_feature_count()}")
    print(f"总特征数: {builder.get_total_feature_count()}")
    print(f"特征名: {builder.get_all_feature_names()[:10]}...")
    
    # 构建数据集
    df = builder.build_dataset()
    print(f"\n数据集形状: {df.shape}")
    print(f"列数: {len(df.columns)}")
