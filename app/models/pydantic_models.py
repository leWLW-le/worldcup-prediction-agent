"""
Pydantic 数据模型（用于 API 请求/响应验证）
"""
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


# ============ Team Schemas ============

class TeamBase(BaseModel):
    """球队基础模型"""
    name: str = Field(..., min_length=1, max_length=100, description="球队名称")
    confederation: Optional[str] = Field(None, max_length=50, description="洲际足联（如 UEFA, CONMEBOL）")
    current_elo: float = Field(1500.0, ge=0, description="当前 ELO 评分")


class TeamCreate(TeamBase):
    """创建球队请求模型"""
    pass


class TeamUpdate(BaseModel):
    """更新球队请求模型"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    confederation: Optional[str] = Field(None, max_length=50)
    current_elo: Optional[float] = Field(None, ge=0)


class TeamResponse(TeamBase):
    """球队响应模型"""
    id: int
    
    class Config:
        from_attributes = True


# ============ Match Schemas ============

class MatchBase(BaseModel):
    """比赛基础模型"""
    date: datetime = Field(..., description="比赛日期")
    team_a_id: int = Field(..., description="A队ID")
    team_b_id: int = Field(..., description="B队ID")
    score_a: Optional[int] = Field(None, ge=0, description="A队得分")
    score_b: Optional[int] = Field(None, ge=0, description="B队得分")
    is_knockout: bool = Field(False, description="是否为淘汰赛")
    tournament_type: Optional[str] = Field(None, max_length=50, description="赛事类型")


class MatchCreate(MatchBase):
    """创建比赛请求模型"""
    pass


class MatchUpdate(BaseModel):
    """更新比赛结果请求模型"""
    score_a: Optional[int] = Field(None, ge=0)
    score_b: Optional[int] = Field(None, ge=0)
    is_knockout: Optional[bool] = None
    tournament_type: Optional[str] = Field(None, max_length=50)


class MatchResponse(MatchBase):
    """比赛响应模型"""
    id: int
    
    class Config:
        from_attributes = True


# ============ Simulation Record Schemas ============

class SimulationRecordBase(BaseModel):
    """模拟记录基础模型"""
    version: str = Field(..., min_length=1, max_length=50, description="模拟版本标识")
    champion_team_id: int = Field(..., description="冠军队伍ID")
    simulation_log: Optional[str] = Field(None, description="JSON 格式的模拟日志")


class SimulationRecordCreate(SimulationRecordBase):
    """创建模拟记录请求模型"""
    pass


class SimulationRecordResponse(SimulationRecordBase):
    """模拟记录响应模型"""
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class SimulationResultSummary(BaseModel):
    """模拟结果汇总模型"""
    version: str
    total_simulations: int = Field(..., ge=1, description="总模拟次数")
    champion_distribution: dict[str, int] = Field(..., description="冠军分布统计")
    top_teams: list[dict[str, Any]] = Field(..., description="前几名队伍统计")


# ============ Prediction Schemas ============

class PredictTournamentRequest(BaseModel):
    """预测锦标赛请求模型"""
    year: int = Field(2026, description="世界杯年份")
    use_historical_data: bool = Field(True, description="是否使用历史数据")
    model_type: str = Field("elo", description="预测模型类型 (elo/poisson)")


class TournamentPredictionResponse(BaseModel):
    """锦标赛预测响应模型"""
    champion: Optional[str] = Field(None, description="冠军队伍")
    runner_up: Optional[str] = Field(None, description="亚军队伍")
    predictions: list[dict] = Field(default_factory=list, description="预测列表")
    reasoning: str = Field(..., description="推理依据")


class PredictionCreate(BaseModel):
    """创建预测请求模型"""
    match_id: int = Field(..., description="比赛ID")
    team_id: Optional[int] = Field(None, description="预测获胜队伍ID")
    predicted_home_score: int = Field(..., ge=0, description="预测主队得分")
    predicted_away_score: int = Field(..., ge=0, description="预测客队得分")
    confidence: Optional[float] = Field(None, ge=0, le=1, description="置信度")
    reasoning: Optional[str] = Field(None, description="推理依据")


class PredictionResponse(BaseModel):
    """预测响应模型"""
    id: int
    match_id: int
    team_id: Optional[int] = None
    predicted_home_score: int
    predicted_away_score: int
    confidence: Optional[float] = None
    reasoning: Optional[str] = None
    
    class Config:
        from_attributes = True


# ============ Generic Response Schema ============

class ApiResponse(BaseModel):
    """通用 API 响应模型"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    data: Optional[dict] = Field(None, description="响应数据")
