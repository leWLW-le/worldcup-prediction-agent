"""
预测服务模块
实现世界杯比赛预测的核心逻辑
"""
from typing import Optional
import pandas as pd
import numpy as np
from scipy.stats import poisson
import os
import logging

from sqlalchemy.orm import Session

from app.models.schemas import Team, Match, Prediction
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class PredictionService:
    """预测服务类"""
    
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
    
    def predict_match_outcome(
        self, 
        home_team: Team, 
        away_team: Team,
        model_type: str = "elo"
    ) -> dict[str, int | float | str]:
        """
        预测单场比赛结果
        
        Args:
            home_team: 主队
            away_team: 客队
            model_type: 预测模型类型
            
        Returns:
            包含预测比分、置信度和推理依据的字典
        """
        if model_type == "elo":
            return self._predict_with_elo(home_team, away_team)
        elif model_type == "poisson":
            return self._predict_with_poisson(home_team, away_team)
        else:
            raise ValueError(f"Unsupported model type: {model_type}")
    
    def _predict_with_elo(self, home_team: Team, away_team: Team) -> dict:
        """
        基于 ELO 评分的预测模型
        
        ELO 差异越大，强队获胜概率越高
        """
        home_elo = home_team.current_elo or 1500
        away_elo = away_team.current_elo or 1500
        
        # 计算 ELO 差异（加上主场优势约 100 分）
        elo_diff = (home_elo - away_elo) + 100
        
        # 将 ELO 差异转换为期望进球数
        # 使用逻辑函数映射
        expected_home_goals = max(0, 1.5 + (elo_diff / 400))
        expected_away_goals = max(0, 1.5 - (elo_diff / 400))
        
        # 使用泊松分布生成整数比分
        home_score = int(np.round(np.random.poisson(expected_home_goals)))
        away_score = int(np.random.poisson(expected_away_goals))
        
        # 计算置信度（基于 ELO 差异的绝对值）
        confidence = min(0.95, 0.5 + abs(elo_diff) / 2000)
        
        # 生成推理依据
        reasoning = (
            f"基于ELO评分: {home_team.name}({home_elo:.0f}) vs {away_team.name}({away_elo:.0f}), "
            f"差异={elo_diff:.0f}, 主场优势+100"
        )
        
        return {
            "home_score": home_score,
            "away_score": away_score,
            "confidence": round(confidence, 3),
            "reasoning": reasoning
        }
    
    def _predict_with_poisson(self, home_team: Team, away_team: Team) -> dict:
        """
        基于泊松分布的预测模型
        考虑球队的攻击和防守能力
        """
        # TODO: 实现更复杂的泊松模型
        # 这里使用简化的版本
        return self._predict_with_elo(home_team, away_team)
    
    def predict_tournament(
        self,
        year: int = 2026,
        use_historical_data: bool = True,
        model_type: str = "elo"
    ) -> dict:
        """
        预测整个锦标赛结果
        
        Args:
            year: 世界杯年份
            use_historical_data: 是否使用历史数据
            model_type: 预测模型类型
            
        Returns:
            包含完整预测结果的字典
        """
        # TODO: 实现完整的锦标赛预测逻辑
        # 1. 获取所有小组赛对阵
        # 2. 预测每场小组赛结果
        # 3. 确定小组出线队伍
        # 4. 预测淘汰赛每一轮
        # 5. 返回冠军预测和完整推理过程
        
        return {
            "champion": None,
            "runner_up": None,
            "predictions": [],
            "reasoning": "预测功能开发中..."
        }
    
    def save_prediction(
        self,
        match_id: int,
        predicted_home_score: int,
        predicted_away_score: int,
        confidence: Optional[float] = None,
        reasoning: Optional[str] = None,
        team_id: Optional[int] = None
    ) -> Prediction:
        """
        保存预测结果到数据库
        
        Args:
            match_id: 比赛ID
            predicted_home_score: 预测主队得分
            predicted_away_score: 预测客队得分
            confidence: 置信度
            reasoning: 推理依据
            team_id: 预测获胜队伍ID
            
        Returns:
            创建的预测记录
        """
        prediction = Prediction(
            match_id=match_id,
            team_id=team_id,
            predicted_home_score=predicted_home_score,
            predicted_away_score=predicted_away_score,
            confidence=confidence,
            reasoning=reasoning
        )
        
        self.db.add(prediction)
        self.db.commit()
        self.db.refresh(prediction)
        
        return prediction
