"""
数据库模型定义
包含球队、比赛、模拟记录等核心实体
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.database import Base


class Team(Base):
    """球队模型"""
    __tablename__ = "teams"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    confederation = Column(String(50), nullable=True, index=True)  # 洲际足联（如 UEFA, CONMEBOL）
    current_elo = Column(Float, nullable=False, default=1500.0)  # 当前 ELO 评分
    group_name = Column(String(50), nullable=True)  # 世界杯小组（如 Group A）
    total_value_eur = Column(Float, nullable=True)  # 球队总身价（欧元）
    recent_form = Column(String(20), nullable=True)  # 近期战绩（如 WWDWW）
    
    # 关系
    matches_as_team_a = relationship("Match", foreign_keys="Match.team_a_id", back_populates="team_a")
    matches_as_team_b = relationship("Match", foreign_keys="Match.team_b_id", back_populates="team_b")
    simulation_records = relationship("SimulationRecord", back_populates="champion_team")
    
    def __repr__(self) -> str:
        return f"<Team(name='{self.name}', elo={self.current_elo})>"


class Match(Base):
    """比赛模型"""
    __tablename__ = "matches"
    
    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, nullable=False, index=True)  # 比赛日期
    
    team_a_id = Column(Integer, ForeignKey("teams.id"), nullable=False)  # A队ID
    team_b_id = Column(Integer, ForeignKey("teams.id"), nullable=False)  # B队ID
    
    score_a = Column(Integer, nullable=True)  # A队得分
    score_b = Column(Integer, nullable=True)  # B队得分
    
    is_knockout = Column(Boolean, default=False, index=True)  # 是否为淘汰赛
    tournament_type = Column(String(50), nullable=True, index=True)  # 赛事类型（如 World Cup 2026）
    
    # 关系
    team_a = relationship("Team", foreign_keys=[team_a_id], back_populates="matches_as_team_a")
    team_b = relationship("Team", foreign_keys=[team_b_id], back_populates="matches_as_team_b")
    
    def __repr__(self) -> str:
        return f"<Match(date={self.date}, {self.team_a_id} vs {self.team_b_id})>"


class Prediction(Base):
    """预测结果模型"""
    __tablename__ = "predictions"
    
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False, index=True)  # 比赛ID
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)  # 预测获胜队伍ID
    
    predicted_home_score = Column(Integer, nullable=False)  # 预测主队得分
    predicted_away_score = Column(Integer, nullable=False)  # 预测客队得分
    confidence = Column(Float, nullable=True)  # 置信度 (0-1)
    reasoning = Column(Text, nullable=True)  # 推理依据
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    def __repr__(self) -> str:
        return f"<Prediction(match_id={self.match_id}, confidence={self.confidence})>"


class SimulationRecord(Base):
    """Monte Carlo 模拟记录模型"""
    __tablename__ = "simulation_records"
    
    id = Column(Integer, primary_key=True, index=True)
    version = Column(String(50), nullable=False, index=True)  # 模拟版本标识
    champion_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)  # 冠军队伍ID
    simulation_log = Column(Text, nullable=True)  # JSON 格式的模拟日志
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # 关系
    champion_team = relationship("Team", back_populates="simulation_records")
    
    def __repr__(self) -> str:
        return f"<SimulationRecord(version='{self.version}', champion={self.champion_team_id})>"


class HistoricalMatch(Base):
    """历史比赛模型"""
    __tablename__ = "historical_matches"
    
    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, nullable=False, index=True)  # 比赛日期
    
    home_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)  # 主队ID
    away_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)  # 客队ID
    
    home_score = Column(Integer, nullable=False)  # 主队得分
    away_score = Column(Integer, nullable=False)  # 客队得分
    
    result = Column(String(20), nullable=True, index=True)  # 结果: home_win/draw/away_win
    competition = Column(String(100), nullable=True, index=True)  # 赛事名称
    competition_weight = Column(Float, nullable=True, default=0.5)  # 赛事权重
    neutral = Column(Boolean, nullable=True, default=True)  # 是否中立场
    
    source = Column(String(50), nullable=True)  # 数据来源
    created_at = Column(DateTime, default=datetime.utcnow, index=True)  # 创建时间
    
    def __repr__(self) -> str:
        return f"<HistoricalMatch(date={self.date}, {self.home_team_id} vs {self.away_team_id}, {self.home_score}-{self.away_score})>"



