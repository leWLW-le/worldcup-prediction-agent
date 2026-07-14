"""
Agent 相关数据库模型

新增表：agent_runs, agent_reasoning_steps, predicted_matches, team_features, fixtures
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text, JSON, UniqueConstraint
from datetime import datetime

from app.db.database import Base


def compute_canonical_pair(home_team: str, away_team: str) -> str:
    """生成规范化的球队配对键（字母序排列），用于逻辑去重。

    规范化规则：
    1. 首尾去空格
    2. 连续空格压缩为单个空格
    3. 首字母大写标准化（Title Case）
    4. 常见别名统一（如 'USA' -> 'United States'）
    5. 字母序排列，确保 France vs Spain == Spain vs France

    注意：当前项目只有 season 字段（默认 2026），没有 tournament edition 列。
    canonical_pair 与 stage 组合构成逻辑唯一键，等效于 season + stage + pair。
    """
    # 已知别名映射
    _ALIASES = {
        "usa": "United States",
        "us": "United States",
        "united states of america": "United States",
        "uk": "England",
        "great britain": "England",
        "england": "England",
        "czech republic": "Czechia",
        "czechia": "Czechia",
        "holland": "Netherlands",
        "holland": "Netherlands",
    }

    def _normalize(name: str) -> str:
        if not name:
            return ""
        # 去首尾空格 + 压缩连续空格
        normalized = " ".join(name.strip().split())
        # 检查别名（不区分大小写）
        lower = normalized.lower()
        if lower in _ALIASES:
            normalized = _ALIASES[lower]
        else:
            # Title Case 标准化
            normalized = normalized.title() if normalized.isupper() or normalized.islower() else normalized
        return normalized

    h = _normalize(home_team)
    a = _normalize(away_team)
    return " vs ".join(sorted([h, a]))


class AgentRun(Base):
    """Agent 运行记录"""
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, index=True)
    objective = Column(Text, nullable=True)
    season = Column(Integer, default=2026)
    predicted_champion = Column(String(100), nullable=True)
    predicted_runner_up = Column(String(100), nullable=True)
    data_quality_score = Column(Float, nullable=True)
    final_explanation = Column(Text, nullable=True)
    status = Column(String(20), default="pending")
    errors_json = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class AgentReasoningStep(Base):
    """Agent 推理步骤"""
    __tablename__ = "agent_reasoning_steps"

    id = Column(Integer, primary_key=True, index=True)
    agent_run_id = Column(Integer, ForeignKey("agent_runs.id"), nullable=False, index=True)
    step_order = Column(Integer, nullable=False)
    step_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class PredictedMatch(Base):
    """预测的比赛"""
    __tablename__ = "predicted_matches"

    id = Column(Integer, primary_key=True, index=True)
    agent_run_id = Column(Integer, ForeignKey("agent_runs.id"), nullable=False, index=True)
    stage = Column(String(50), nullable=True)  # group / round_of_32 / ...
    home_team = Column(String(100), nullable=False)
    away_team = Column(String(100), nullable=False)
    predicted_home_score = Column(Integer, nullable=True)
    predicted_away_score = Column(Integer, nullable=True)
    predicted_winner = Column(String(100), nullable=True)
    confidence = Column(Float, nullable=True)
    source = Column(String(30), default="agent_prediction")  # real_result / agent_prediction
    reasoning_json = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime, default=datetime.utcnow)


class TeamFeature(Base):
    """球队特征快照"""
    __tablename__ = "team_features"

    id = Column(Integer, primary_key=True, index=True)
    agent_run_id = Column(Integer, ForeignKey("agent_runs.id"), nullable=False, index=True)
    team_name = Column(String(100), nullable=False)
    elo_rating = Column(Float, nullable=True)
    fifa_rank = Column(Integer, nullable=True)
    recent_win_rate = Column(Float, nullable=True)
    recent_goals_for_avg = Column(Float, nullable=True)
    recent_goals_against_avg = Column(Float, nullable=True)
    attack_score = Column(Float, nullable=True)
    defense_score = Column(Float, nullable=True)
    power_score = Column(Float, nullable=True)
    data_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Fixture(Base):
    """真实比赛赛程 / 比分表
    只保存真实比赛数据，不保存预测结果。
    数据来源：football-data.org / API-Football
    """
    __tablename__ = "fixtures"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    fixture_id = Column(String(100), unique=True, index=True, nullable=False)  # 唯一标识
    api_fixture_id = Column(String(100), index=True)  # API 原始 fixture ID

    # 球队信息
    home_team = Column(String(100), nullable=False, index=True)
    away_team = Column(String(100), nullable=False, index=True)
    home_team_id = Column(String(50))
    away_team_id = Column(String(50))

    # 比赛信息
    match_date = Column(DateTime, index=True)
    stage = Column(String(50))  # group_stage, round_of_32, round_of_16, quarter_finals, semi_finals, final
    status = Column(String(50), index=True)  # NS, LIVE, FT, AET, PEN

    # 逻辑去重键：规范化球队配对（字母序），与 stage 组合构成唯一约束
    canonical_pair = Column(String(200), index=True)

    __table_args__ = (
        UniqueConstraint('stage', 'canonical_pair', name='uq_fixture_stage_pair'),
    )

    # 比分
    home_score = Column(Integer)
    away_score = Column(Integer)
    winner = Column(String(100))

    # 数据来源
    source = Column(String(50), index=True)  # football_data, api_football, db_cache, manual_candidate, unavailable
    source_level = Column(String(50), index=True)  # external_real, verified_cache, manual_verified, unverified_candidate, unavailable
    is_verified = Column(Boolean, default=False)
    needs_review = Column(Boolean, default=False)
    confidence_level = Column(String(50), index=True)  # high, medium, low, unavailable
    evidence_count = Column(Integer, default=0)  # 有几个可信来源支持该比赛数据
    evidence_sources = Column(Text)  # JSON 数组，例如 ["football_data", "api_football"]

    # 时间戳
    fetched_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 原始数据
    raw_payload = Column(Text)  # JSON 格式的原始 API 响应

    def __repr__(self):
        return f"<Fixture(fixture_id={self.fixture_id}, {self.home_team} vs {self.away_team})>"
