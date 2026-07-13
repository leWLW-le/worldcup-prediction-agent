"""
训练数据集构建器
从历史比赛数据生成用于PyTorch模型训练的数据集
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

from app.db.database import SessionLocal
from app.services.probability_engine import ProbabilityEngine

logger = logging.getLogger(__name__)


class TrainingDatasetBuilder:
    """
    训练数据集构建器
    
    从historical_matches生成training_dataset.csv
    
    每场比赛生成特征：
    - 球队A: elo, fifa_rank, recent_form, attack_strength, defense_strength
    - 球队B: elo, fifa_rank, recent_form, attack_strength, defense_strength
    - 比赛: home_advantage, competition_weight, neutral
    
    标签：
    - result: 0=主胜, 1=平局, 2=客胜
    """
    
    def __init__(self, db: Optional[Session] = None):
        """
        初始化构建器
        
        Args:
            db: 数据库会话
        """
        self.db = db or SessionLocal()
        self.prob_engine = ProbabilityEngine()
    
    def close(self):
        """关闭数据库会话"""
        if self.db:
            self.db.close()
    
    def calculate_team_elo(self, team_id: int, match_date: datetime) -> float:
        """
        计算球队在特定日期的ELO评分
        
        Args:
            team_id: 球队ID
            match_date: 比赛日期
            
        Returns:
            ELO评分
        """
        # 查询该日期之前的所有比赛
        matches = self.db.execute(
            text("""
                SELECT
                    hm.date,
                    hm.home_team_id,
                    hm.away_team_id,
                    hm.home_score,
                    hm.away_score,
                    hm.result
                FROM historical_matches hm
                WHERE hm.date < :match_date
                AND (hm.home_team_id = :team_id OR hm.away_team_id = :team_id)
                ORDER BY hm.date ASC
            """),
            {'match_date': match_date, 'team_id': team_id}
        ).fetchall()
        
        # 初始ELO
        elo = 1500.0
        K = 30
        
        for match in matches:
            match_date_m = match[0]
            home_id = match[1]
            away_id = match[2]
            home_score = match[3]
            away_score = match[4]
            result = match[5]
            
            is_home = (home_id == team_id)
            
            if is_home:
                opponent_elo = 1500.0  # 简化：对手初始ELO
                expected = 1 / (1 + 10 ** ((opponent_elo - elo) / 400))
                actual = 1 if result == 'home_win' else (0.5 if result == 'draw' else 0)
            else:
                opponent_elo = 1500.0
                expected = 1 / (1 + 10 ** ((elo - opponent_elo) / 400))
                actual = 1 if result == 'away_win' else (0.5 if result == 'draw' else 0)
            
            elo += K * (actual - expected)
        
        return elo
    
    def calculate_recent_form(
        self,
        team_id: int,
        match_date: datetime,
        window: int = 5
    ) -> float:
        """
        计算球队近期战绩（胜率）
        
        Args:
            team_id: 球队ID
            match_date: 比赛日期
            window: 窗口大小（默认5场）
            
        Returns:
            胜率 (0-1)
        """
        matches = self.db.execute(
            text("""
                SELECT result, home_team_id
                FROM historical_matches
                WHERE date < :match_date
                AND (home_team_id = :team_id OR away_team_id = :team_id)
                ORDER BY date DESC
                LIMIT :window
            """),
            {'match_date': match_date, 'team_id': team_id, 'window': window}
        ).fetchall()
        
        if not matches:
            return 0.5
        
        wins = 0
        for match in matches:
            result = match[0]
            is_home = (match[1] == team_id)
            
            if (is_home and result == 'home_win') or (not is_home and result == 'away_win'):
                wins += 1
            elif result == 'draw':
                wins += 0.5
        
        return wins / len(matches)
    
    def calculate_attack_strength(
        self,
        team_id: int,
        match_date: datetime,
        window: int = 10
    ) -> float:
        """
        计算球队攻击强度（场均进球）
        
        Args:
            team_id: 球队ID
            match_date: 比赛日期
            window: 窗口大小
            
        Returns:
            场均进球数
        """
        matches = self.db.execute(
            text("""
                SELECT home_score, away_score, home_team_id
                FROM historical_matches
                WHERE date < :match_date
                AND (home_team_id = :team_id OR away_team_id = :team_id)
                ORDER BY date DESC
                LIMIT :window
            """),
            {'match_date': match_date, 'team_id': team_id, 'window': window}
        ).fetchall()
        
        if not matches:
            return 1.0
        
        total_goals = 0
        for match in matches:
            home_score = match[0]
            away_score = match[1]
            is_home = (match[2] == team_id)
            
            total_goals += home_score if is_home else away_score
        
        return total_goals / len(matches)
    
    def calculate_defense_strength(
        self,
        team_id: int,
        match_date: datetime,
        window: int = 10
    ) -> float:
        """
        计算球队防守强度（场均失球，越低越好）
        
        Args:
            team_id: 球队ID
            match_date: 比赛日期
            window: 窗口大小
            
        Returns:
            场均失球数
        """
        matches = self.db.execute(
            text("""
                SELECT home_score, away_score, home_team_id
                FROM historical_matches
                WHERE date < :match_date
                AND (home_team_id = :team_id OR away_team_id = :team_id)
                ORDER BY date DESC
                LIMIT :window
            """),
            {'match_date': match_date, 'team_id': team_id, 'window': window}
        ).fetchall()
        
        if not matches:
            return 1.0
        
        total_conceded = 0
        for match in matches:
            home_score = match[0]
            away_score = match[1]
            is_home = (match[2] == team_id)
            
            total_conceded += away_score if is_home else home_score
        
        return total_conceded / len(matches)
    
    def get_head_to_head_score(
        self,
        home_team_id: int,
        away_team_id: int,
        match_date: datetime,
        window: int = 5
    ) -> float:
        """
        计算交锋历史得分
        
        Args:
            home_team_id: 主队ID
            away_team_id: 客队ID
            match_date: 比赛日期
            window: 窗口大小
            
        Returns:
            交锋得分 (-1 到 1)
        """
        matches = self.db.execute(
            text("""
                SELECT result, home_team_id
                FROM historical_matches
                WHERE date < :match_date
                AND (
                    (home_team_id = :home_id AND away_team_id = :away_id)
                    OR
                    (home_team_id = :away_id AND away_team_id = :home_id)
                )
                ORDER BY date DESC
                LIMIT :window
            """),
            {
                'match_date': match_date,
                'home_id': home_team_id,
                'away_id': away_team_id,
                'window': window
            }
        ).fetchall()
        
        if not matches:
            return 0.0
        
        score = 0
        for match in matches:
            result = match[0]
            was_home = (match[1] == home_team_id)
            
            if (was_home and result == 'home_win') or (not was_home and result == 'away_win'):
                score += 1
            elif (was_home and result == 'away_win') or (not was_home and result == 'home_win'):
                score -= 1
        
        return score / len(matches)
    
    def build_dataset(
        self,
        output_file: str = "data/training_dataset.csv",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict:
        """
        构建训练数据集
        
        Args:
            output_file: 输出CSV文件路径
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            
        Returns:
            构建统计信息
        """
        logger.info("Building training dataset...")
        
        # 查询历史比赛
        query = """
            SELECT
                hm.id,
                hm.date,
                hm.home_team_id,
                hm.away_team_id,
                hm.home_score,
                hm.away_score,
                hm.result,
                hm.competition_weight,
                hm.neutral
            FROM historical_matches hm
            WHERE 1=1
        """
        
        params = {}
        
        if start_date:
            query += " AND hm.date >= :start_date"
            params['start_date'] = start_date
        
        if end_date:
            query += " AND hm.date <= :end_date"
            params['end_date'] = end_date
        
        query += " ORDER BY hm.date ASC"
        
        matches = self.db.execute(text(query), params).fetchall()
        
        logger.info(f"Found {len(matches)} matches to process")
        
        # 构建数据集
        dataset = []
        processed = 0
        skipped = 0
        
        for match in matches:
            try:
                match_id = match[0]
                match_date = match[1]
                home_team_id = match[2]
                away_team_id = match[3]
                home_score = match[4]
                away_score = match[5]
                result = match[6]
                competition_weight = match[7]
                neutral = match[8]
                
                # 计算主队特征
                home_elo = self.calculate_team_elo(home_team_id, match_date)
                home_form = self.calculate_recent_form(home_team_id, match_date)
                home_attack = self.calculate_attack_strength(home_team_id, match_date)
                home_defense = self.calculate_defense_strength(home_team_id, match_date)
                
                # 计算客队特征
                away_elo = self.calculate_team_elo(away_team_id, match_date)
                away_form = self.calculate_recent_form(away_team_id, match_date)
                away_attack = self.calculate_attack_strength(away_team_id, match_date)
                away_defense = self.calculate_defense_strength(away_team_id, match_date)
                
                # 计算交锋历史
                h2h_score = self.get_head_to_head_score(
                    home_team_id, away_team_id, match_date
                )
                
                # 转换结果为标签
                if result == 'home_win':
                    label = 0
                elif result == 'draw':
                    label = 1
                else:
                    label = 2
                
                # 添加到数据集
                dataset.append({
                    'match_id': match_id,
                    'date': match_date,
                    'home_team_id': home_team_id,
                    'away_team_id': away_team_id,
                    'home_elo': home_elo,
                    'home_fifa_rank': 50,  # 占位符
                    'home_recent_form': home_form,
                    'home_attack_strength': home_attack,
                    'home_defense_strength': home_defense,
                    'away_elo': away_elo,
                    'away_fifa_rank': 50,  # 占位符
                    'away_recent_form': away_form,
                    'away_attack_strength': away_attack,
                    'away_defense_strength': away_defense,
                    'home_advantage': 100 if not neutral else 0,
                    'competition_weight': competition_weight,
                    'neutral': neutral,
                    'elo_difference': home_elo - away_elo,
                    'ranking_difference': 0,  # 占位符
                    'attack_difference': home_attack - away_attack,
                    'defense_difference': home_defense - away_defense,
                    'recent_form_difference': home_form - away_form,
                    'competition_strength': competition_weight,
                    'historical_win_rate': 0.5,  # 占位符
                    'head_to_head_score': h2h_score,
                    'home_score': home_score,
                    'away_score': away_score,
                    'result': label
                })
                
                processed += 1
                
                if processed % 100 == 0:
                    logger.info(f"Processed {processed}/{len(matches)} matches")
                
            except Exception as e:
                logger.error(f"Failed to process match {match[0]}: {e}")
                skipped += 1
                continue
        
        # 保存为CSV
        if dataset:
            df = pd.DataFrame(dataset)
            df.to_csv(output_file, index=False)
            logger.info(f"Training dataset saved to {output_file}")
        
        stats = {
            'total_matches': len(matches),
            'processed': processed,
            'skipped': skipped,
            'output_file': output_file
        }
        
        logger.info(f"Dataset building completed: {stats}")
        return stats
