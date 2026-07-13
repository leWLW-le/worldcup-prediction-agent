"""
高级特征构建器
基于 historical_matches 生成扩展球队特征（30-50维）

特征分类：
1. 基础实力特征 (5)
2. 近期状态特征 (12)
3. 进攻能力特征 (5)
4. 防守能力特征 (5)
5. 强队表现特征 (3)
6. 比赛环境特征 (4)

总计: 34 个特征（每队 17 个 × 2 队 + 差值 17 = 51 最终输入）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from sqlalchemy import text
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

from app.db.database import SessionLocal

logger = logging.getLogger(__name__)


class AdvancedFeatureBuilder:
    """高级特征构建器"""
    
    # 赛事权重映射
    COMPETITION_WEIGHTS = {
        'FIFA World Cup': 1.0,
        'FIFA World Cup Qualification': 0.8,
        'UEFA European Championship': 0.9,
        'UEFA Euro Qualification': 0.7,
        'UEFA Nations League': 0.6,
        'Copa America': 0.85,
        'Africa Cup of Nations': 0.7,
        'AFC Asian Cup': 0.7,
        'CONCACAF Gold Cup': 0.65,
        'OFC Nations Cup': 0.4,
        'International Friendly': 0.3,
    }
    
    def __init__(self, db=None):
        self.db = db or SessionLocal()
        self._matches_df = None
        self._team_elo_history = {}
    
    @property
    def matches_df(self) -> pd.DataFrame:
        """懒加载历史比赛数据"""
        if self._matches_df is None:
            self._matches_df = self._load_matches()
        return self._matches_df
    
    def _load_matches(self) -> pd.DataFrame:
        """从数据库加载所有历史比赛"""
        query = text("""
            SELECT
                hm.id, hm.date, hm.home_team_id, hm.away_team_id,
                hm.home_score, hm.away_score, hm.result,
                hm.competition, hm.competition_weight, hm.neutral,
                t1.name as home_team, t2.name as away_team,
                t1.current_elo as home_elo, t2.current_elo as away_elo
            FROM historical_matches hm
            JOIN teams t1 ON hm.home_team_id = t1.id
            JOIN teams t2 ON hm.away_team_id = t2.id
            ORDER BY hm.date ASC
        """)
        result = self.db.execute(query).fetchall()
        
        columns = [
            'id', 'date', 'home_team_id', 'away_team_id',
            'home_score', 'away_score', 'result',
            'competition', 'competition_weight', 'neutral',
            'home_team', 'away_team', 'home_elo', 'away_elo'
        ]
        df = pd.DataFrame(result, columns=columns)
        df['date'] = pd.to_datetime(df['date'])
        logger.info(f"Loaded {len(df)} historical matches")
        return df
    
    def _get_team_matches(self, team_id: int, before_date=None) -> pd.DataFrame:
        """获取某队的所有比赛（统一为主队视角和客队视角）"""
        df = self.matches_df
        
        if before_date is not None:
            df = df[df['date'] <= before_date]
        
        home_matches = df[df['home_team_id'] == team_id].copy()
        home_matches['is_home'] = True
        home_matches['team_goals'] = home_matches['home_score']
        home_matches['opponent_goals'] = home_matches['away_score']
        home_matches['opponent_id'] = home_matches['away_team_id']
        home_matches['opponent_elo'] = home_matches['away_elo']
        
        away_matches = df[df['away_team_id'] == team_id].copy()
        away_matches['is_home'] = False
        away_matches['team_goals'] = away_matches['away_score']
        away_matches['opponent_goals'] = away_matches['home_score']
        away_matches['opponent_id'] = away_matches['home_team_id']
        away_matches['opponent_elo'] = away_matches['home_elo']
        
        all_matches = pd.concat([home_matches, away_matches], ignore_index=True)
        all_matches = all_matches.sort_values('date', ascending=False)
        
        # 计算比赛结果
        all_matches['win'] = (all_matches['team_goals'] > all_matches['opponent_goals']).astype(int)
        all_matches['draw'] = (all_matches['team_goals'] == all_matches['opponent_goals']).astype(int)
        all_matches['loss'] = (all_matches['team_goals'] < all_matches['opponent_goals']).astype(int)
        
        return all_matches
    
    def _get_top20_elo_threshold(self, before_date=None) -> float:
        """获取ELO排名前20的阈值"""
        df = self.matches_df
        if before_date is not None:
            df = df[df['date'] <= before_date]
        
        all_elos = pd.concat([df['home_elo'], df['away_elo']]).dropna()
        if len(all_elos) == 0:
            return 1800.0
        return all_elos.quantile(0.80)
    
    # ============================================================
    # 1. 基础实力特征 (5)
    # ============================================================
    
    def calc_elo_rating(self, team_id: int, before_date=None) -> float:
        """当前ELO评分"""
        df = self.matches_df
        if before_date is not None:
            df = df[df['date'] <= before_date]
        
        elos = df[df['home_team_id'] == team_id]['home_elo']
        if len(elos) > 0:
            return elos.iloc[-1]
        elos = df[df['away_team_id'] == team_id]['away_elo']
        if len(elos) > 0:
            return elos.iloc[-1]
        return 1500.0
    
    def calc_elo_change(self, team_id: int, years: int = 1, before_date=None) -> float:
        """ELO变化量"""
        df = self.matches_df
        if before_date is not None:
            df = df[df['date'] <= before_date]
        
        team_matches = self._get_team_matches(team_id, before_date)
        if len(team_matches) < 2:
            return 0.0
        
        latest_elo = team_matches.iloc[0]['opponent_elo']  # 近似
        cutoff_date = team_matches.iloc[0]['date'] - timedelta(days=365 * years)
        old_matches = team_matches[team_matches['date'] <= cutoff_date]
        
        if len(old_matches) == 0:
            return 0.0
        
        # 使用首尾ELO差异近似
        first_elo = old_matches.iloc[-1].get('home_elo', 1500)
        last_elo = team_matches.iloc[0].get('home_elo', 1500)
        
        return last_elo - first_elo if last_elo and first_elo else 0.0
    
    def calc_world_cup_experience(self, team_id: int, before_date=None) -> int:
        """世界杯参赛次数"""
        df = self.matches_df
        if before_date is not None:
            df = df[df['date'] <= before_date]
        
        team_matches = df[
            ((df['home_team_id'] == team_id) | (df['away_team_id'] == team_id)) &
            (df['competition'] == 'FIFA World Cup')
        ]
        # 按年份计算不同届数
        if len(team_matches) == 0:
            return 0
        years = team_matches['date'].dt.year.nunique()
        return years
    
    def calc_major_tournament_points(self, team_id: int, before_date=None) -> float:
        """大赛积分（世界杯+洲际杯）"""
        df = self.matches_df
        if before_date is not None:
            df = df[df['date'] <= before_date]
        
        major_comps = ['FIFA World Cup', 'UEFA European Championship', 'Copa America',
                       'Africa Cup of Nations', 'AFC Asian Cup', 'CONCACAF Gold Cup']
        
        team_matches = df[
            ((df['home_team_id'] == team_id) | (df['away_team_id'] == team_id)) &
            (df['competition'].isin(major_comps))
        ]
        
        if len(team_matches) == 0:
            return 0.0
        
        points = 0.0
        for _, m in team_matches.iterrows():
            weight = self.COMPETITION_WEIGHTS.get(m['competition'], 0.5)
            if m['home_team_id'] == team_id:
                if m['home_score'] > m['away_score']:
                    points += 3 * weight
                elif m['home_score'] == m['away_score']:
                    points += 1 * weight
            else:
                if m['away_score'] > m['home_score']:
                    points += 3 * weight
                elif m['away_score'] == m['home_score']:
                    points += 1 * weight
        
        return points
    
    def calc_recent_rank_trend(self, team_id: int, before_date=None) -> float:
        """近期排名趋势（近6个月ELO变化）"""
        return self.calc_elo_change(team_id, years=0.5, before_date=before_date)
    
    # ============================================================
    # 2. 近期状态特征 (12)
    # ============================================================
    
    def calc_recent_form(self, team_id: int, n_matches: int = 5, before_date=None) -> Dict:
        """近期N场状态"""
        team_matches = self._get_team_matches(team_id, before_date)
        recent = team_matches.head(n_matches)
        
        if len(recent) == 0:
            return {
                f'wins_{n_matches}': 0, f'draws_{n_matches}': 0, f'losses_{n_matches}': 0,
                f'goals_for_{n_matches}': 0, f'goals_against_{n_matches}': 0,
                f'win_rate_{n_matches}': 0.0
            }
        
        wins = recent['win'].sum()
        draws = recent['draw'].sum()
        losses = recent['loss'].sum()
        goals_for = recent['team_goals'].sum()
        goals_against = recent['opponent_goals'].sum()
        win_rate = wins / len(recent)
        
        return {
            f'wins_{n_matches}': int(wins),
            f'draws_{n_matches}': int(draws),
            f'losses_{n_matches}': int(losses),
            f'goals_for_{n_matches}': float(goals_for),
            f'goals_against_{n_matches}': float(goals_against),
            f'win_rate_{n_matches}': float(win_rate)
        }
    
    # ============================================================
    # 3. 进攻能力特征 (5)
    # ============================================================
    
    def calc_attack_features(self, team_id: int, before_date=None) -> Dict:
        """进攻能力特征"""
        team_matches = self._get_team_matches(team_id, before_date)
        
        if len(team_matches) == 0:
            return {
                'attack_score': 0.0, 'avg_goals_scored': 0.0,
                'shots_estimate': 0.0, 'big_win_rate': 0.0,
                'scoring_consistency': 0.0
            }
        
        goals = team_matches['team_goals']
        avg_goals = goals.mean()
        
        # 大比分胜率（进球>=3的比赛胜率）
        big_games = team_matches[team_matches['team_goals'] >= 3]
        big_win_rate = big_games['win'].mean() if len(big_games) > 0 else 0.0
        
        # 进球连续性（连续进球的场次比例）
        scoring_streak = 0
        total_streaks = 0
        for g in goals.values:
            if g > 0:
                scoring_streak += 1
            else:
                if scoring_streak > 0:
                    total_streaks += 1
                scoring_streak = 0
        if scoring_streak > 0:
            total_streaks += 1
        scoring_consistency = (goals > 0).mean()
        
        # 综合进攻评分
        attack_score = avg_goals * 0.4 + (goals > 0).mean() * 2 * 0.3 + big_win_rate * 0.3
        
        # 射门估计（基于进球的估算，约2.5倍进球数）
        shots_estimate = avg_goals * 2.5
        
        return {
            'attack_score': float(attack_score),
            'avg_goals_scored': float(avg_goals),
            'shots_estimate': float(shots_estimate),
            'big_win_rate': float(big_win_rate),
            'scoring_consistency': float(scoring_consistency)
        }
    
    # ============================================================
    # 4. 防守能力特征 (5)
    # ============================================================
    
    def calc_defense_features(self, team_id: int, before_date=None) -> Dict:
        """防守能力特征"""
        team_matches = self._get_team_matches(team_id, before_date)
        
        if len(team_matches) == 0:
            return {
                'defense_score': 0.0, 'avg_goals_conceded': 0.0,
                'clean_sheet_rate': 0.0, 'concede_consistency': 0.0,
                'comeback_defense_score': 0.0
            }
        
        conceded = team_matches['opponent_goals']
        avg_conceded = conceded.mean()
        
        # 零封率
        clean_sheets = (team_matches['opponent_goals'] == 0).sum()
        clean_sheet_rate = clean_sheets / len(team_matches)
        
        # 失球稳定性（失球标准差越小越好）
        concede_std = conceded.std() if len(conceded) > 1 else 0.0
        concede_consistency = 1.0 - min(concede_std / 3.0, 1.0)
        
        # 逆转防守能力（先失球后不输的比赛比例）
        comeback_games = team_matches[team_matches['opponent_goals'] > team_matches['team_goals']]
        comeback_defense = 1.0 - (len(comeback_games) / max(len(team_matches), 1))
        
        # 综合防守评分
        defense_score = (1.0 - min(avg_conceded / 3.0, 1.0)) * 0.4 + \
                       clean_sheet_rate * 0.3 + \
                       concede_consistency * 0.3
        
        return {
            'defense_score': float(defense_score),
            'avg_goals_conceded': float(avg_conceded),
            'clean_sheet_rate': float(clean_sheet_rate),
            'concede_consistency': float(concede_consistency),
            'comeback_defense_score': float(comeback_defense)
        }
    
    # ============================================================
    # 5. 强队表现特征 (3)
    # ============================================================
    
    def calc_strong_opponent_features(self, team_id: int, before_date=None) -> Dict:
        """对阵强队的表现"""
        df = self.matches_df
        if before_date is not None:
            df = df[df['date'] <= before_date]
        
        top20_threshold = self._get_top20_elo_threshold(before_date)
        
        team_matches = self._get_team_matches(team_id, before_date)
        
        # 对阵强队（ELO >= top20_threshold）
        strong_matches = team_matches[team_matches['opponent_elo'] >= top20_threshold]
        
        if len(strong_matches) == 0:
            return {
                'strong_opponent_win_rate': 0.0,
                'top20_team_performance': 0.0,
                'tournament_performance_score': 0.0
            }
        
        strong_win_rate = strong_matches['win'].mean()
        
        # 对Top20球队的表现（进球-失球）
        top20_perf = (strong_matches['team_goals'] - strong_matches['opponent_goals']).mean()
        
        # 大赛表现分数
        major_comps = ['FIFA World Cup', 'UEFA European Championship', 'Copa America']
        major_matches = team_matches[team_matches['competition'].isin(major_comps)]
        if len(major_matches) > 0:
            tournament_score = major_matches['win'].mean() * 0.6 + \
                             (major_matches['team_goals'] - major_matches['opponent_goals']).mean() * 0.1 + 0.5
        else:
            tournament_score = 0.5
        
        return {
            'strong_opponent_win_rate': float(strong_win_rate),
            'top20_team_performance': float(top20_perf),
            'tournament_performance_score': float(min(max(tournament_score, 0), 1))
        }
    
    # ============================================================
    # 6. 比赛环境特征 (4)
    # ============================================================
    
    @staticmethod
    def calc_match_environment(match_row: dict) -> Dict:
        """比赛环境特征"""
        neutral = 1.0 if match_row.get('neutral', True) else 0.0
        
        comp = match_row.get('competition', 'International Friendly')
        comp_weight = AdvancedFeatureBuilder.COMPETITION_WEIGHTS.get(comp, 0.3)
        
        is_world_cup = 1.0 if 'World Cup' in str(comp) else 0.0
        is_knockout = 0.0  # 历史比赛默认0，可在具体场景覆盖
        
        return {
            'neutral_venue': neutral,
            'competition_weight': comp_weight,
            'world_cup_match': is_world_cup,
            'knockout_stage': is_knockout
        }
    
    # ============================================================
    # 综合：生成单队全部特征
    # ============================================================
    
    def build_team_features(self, team_id: int, before_date=None) -> Dict[str, float]:
        """生成单支球队的全部特征"""
        features = {}
        
        # 1. 基础实力 (5)
        elo = self.calc_elo_rating(team_id, before_date)
        features['elo_rating'] = elo
        features['elo_change_1year'] = self.calc_elo_change(team_id, 1, before_date)
        features['elo_change_3year'] = self.calc_elo_change(team_id, 3, before_date)
        features['world_cup_experience'] = self.calc_world_cup_experience(team_id, before_date)
        features['major_tournament_points'] = self.calc_major_tournament_points(team_id, before_date)
        
        # 2. 近期状态 (12)
        features.update(self.calc_recent_form(team_id, 5, before_date))
        features.update(self.calc_recent_form(team_id, 10, before_date))
        
        # 3. 进攻能力 (5)
        features.update(self.calc_attack_features(team_id, before_date))
        
        # 4. 防守能力 (5)
        features.update(self.calc_defense_features(team_id, before_date))
        
        # 5. 强队表现 (3)
        features.update(self.calc_strong_opponent_features(team_id, before_date))
        
        return features
    
    def build_all_team_features(self, before_date=None) -> Dict[int, Dict[str, float]]:
        """生成所有球队的特征"""
        team_ids = set()
        df = self.matches_df
        if before_date is not None:
            df = df[df['date'] <= before_date]
        
        team_ids = set(df['home_team_id'].unique()) | set(df['away_team_id'].unique())
        
        all_features = {}
        for tid in team_ids:
            all_features[tid] = self.build_team_features(tid, before_date)
        
        logger.info(f"Built features for {len(all_features)} teams")
        return all_features
    
    def get_feature_names(self) -> List[str]:
        """返回所有特征名列表"""
        names = []
        
        # 基础实力 (5)
        names.extend(['elo_rating', 'elo_change_1year', 'elo_change_3year',
                       'world_cup_experience', 'major_tournament_points'])
        
        # 近期状态5场 (6)
        names.extend(['wins_5', 'draws_5', 'losses_5',
                       'goals_for_5', 'goals_against_5', 'win_rate_5'])
        
        # 近期状态10场 (6)
        names.extend(['wins_10', 'draws_10', 'losses_10',
                       'goals_for_10', 'goals_against_10', 'win_rate_10'])
        
        # 进攻能力 (5)
        names.extend(['attack_score', 'avg_goals_scored', 'shots_estimate',
                       'big_win_rate', 'scoring_consistency'])
        
        # 防守能力 (5)
        names.extend(['defense_score', 'avg_goals_conceded', 'clean_sheet_rate',
                       'concede_consistency', 'comeback_defense_score'])
        
        # 强队表现 (3)
        names.extend(['strong_opponent_win_rate', 'top20_team_performance',
                       'tournament_performance_score'])
        
        # 比赛环境 (4)
        names.extend(['neutral_venue', 'competition_weight',
                       'world_cup_match', 'knockout_stage'])
        
        return names


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    builder = AdvancedFeatureBuilder()
    
    # 测试：生成一支球队的特征
    sample_team_id = builder.matches_df['home_team_id'].iloc[0]
    features = builder.build_team_features(sample_team_id)
    
    print(f"\n球队 {sample_team_id} 的扩展特征:")
    for k, v in features.items():
        print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")
    
    print(f"\n总特征数: {len(features)}")
    print(f"特征名列表: {builder.get_feature_names()}")
    print(f"特征名数量: {len(builder.get_feature_names())}")
