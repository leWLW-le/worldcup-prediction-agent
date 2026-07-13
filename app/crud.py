"""
CRUD 操作函数
提供 Team, Match, SimulationRecord 的完整增删改查功能
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
import json

from app.models.schemas import Team, Match, SimulationRecord
from app.models.pydantic_models import (
    TeamCreate, TeamUpdate,
    MatchCreate, MatchUpdate,
    SimulationRecordCreate
)


# ============ Team CRUD ============

def create_team(db: Session, team: TeamCreate) -> Team:
    """
    创建新球队
    
    Args:
        db: 数据库会话
        team: 球队数据
        
    Returns:
        创建的球队对象
    """
    db_team = Team(
        name=team.name,
        confederation=team.confederation,
        current_elo=team.current_elo
    )
    db.add(db_team)
    db.commit()
    db.refresh(db_team)
    return db_team


def get_team(db: Session, team_id: int) -> Optional[Team]:
    """
    根据 ID 获取球队
    
    Args:
        db: 数据库会话
        team_id: 球队 ID
        
    Returns:
        球队对象，不存在则返回 None
    """
    return db.query(Team).filter(Team.id == team_id).first()


def get_team_by_name(db: Session, name: str) -> Optional[Team]:
    """
    根据名称获取球队
    
    Args:
        db: 数据库会话
        name: 球队名称
        
    Returns:
        球队对象，不存在则返回 None
    """
    return db.query(Team).filter(Team.name == name).first()


def get_teams(
    db: Session, 
    skip: int = 0, 
    limit: int = 100,
    confederation: Optional[str] = None
) -> list[Team]:
    """
    获取球队列表
    
    Args:
        db: 数据库会话
        skip: 跳过记录数
        limit: 限制返回数
        confederation: 按洲际足联筛选
        
    Returns:
        球队列表
    """
    query = db.query(Team)
    
    if confederation:
        query = query.filter(Team.confederation == confederation)
    
    return query.offset(skip).limit(limit).all()


def update_team(db: Session, team_id: int, team_update: TeamUpdate) -> Optional[Team]:
    """
    更新球队信息
    
    Args:
        db: 数据库会话
        team_id: 球队 ID
        team_update: 更新数据
        
    Returns:
        更新后的球队对象，不存在则返回 None
    """
    db_team = get_team(db, team_id)
    if not db_team:
        return None
    
    update_data = team_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_team, field, value)
    
    db.commit()
    db.refresh(db_team)
    return db_team


def delete_team(db: Session, team_id: int) -> bool:
    """
    删除球队
    
    Args:
        db: 数据库会话
        team_id: 球队 ID
        
    Returns:
        是否删除成功
    """
    db_team = get_team(db, team_id)
    if not db_team:
        return False
    
    db.delete(db_team)
    db.commit()
    return True


def get_teams_by_elo_range(
    db: Session, 
    min_elo: float, 
    max_elo: float
) -> list[Team]:
    """
    根据 ELO 评分范围获取球队
    
    Args:
        db: 数据库会话
        min_elo: 最小 ELO
        max_elo: 最大 ELO
        
    Returns:
        球队列表
    """
    return db.query(Team).filter(
        Team.current_elo >= min_elo,
        Team.current_elo <= max_elo
    ).all()


# ============ Match CRUD ============

def create_match(db: Session, match: MatchCreate) -> Match:
    """
    创建新比赛
    
    Args:
        db: 数据库会话
        match: 比赛数据
        
    Returns:
        创建的比赛对象
    """
    # 验证参赛队伍存在
    team_a = get_team(db, match.team_a_id)
    team_b = get_team(db, match.team_b_id)
    
    if not team_a or not team_b:
        raise ValueError("One or both teams do not exist")
    
    if team_a.id == team_b.id:
        raise ValueError("Team A and Team B cannot be the same")
    
    db_match = Match(
        date=match.date,
        team_a_id=match.team_a_id,
        team_b_id=match.team_b_id,
        score_a=match.score_a,
        score_b=match.score_b,
        is_knockout=match.is_knockout,
        tournament_type=match.tournament_type
    )
    db.add(db_match)
    db.commit()
    db.refresh(db_match)
    return db_match


def get_match(db: Session, match_id: int) -> Optional[Match]:
    """
    根据 ID 获取比赛
    
    Args:
        db: 数据库会话
        match_id: 比赛 ID
        
    Returns:
        比赛对象，不存在则返回 None
    """
    return db.query(Match).filter(Match.id == match_id).first()


def get_matches(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    team_id: Optional[int] = None,
    is_knockout: Optional[bool] = None,
    tournament_type: Optional[str] = None
) -> list[Match]:
    """
    获取比赛列表
    
    Args:
        db: 数据库会话
        skip: 跳过记录数
        limit: 限制返回数
        team_id: 按队伍筛选
        is_knockout: 按淘汰赛筛选
        tournament_type: 按赛事类型筛选
        
    Returns:
        比赛列表
    """
    query = db.query(Match)
    
    if team_id:
        query = query.filter(
            (Match.team_a_id == team_id) | (Match.team_b_id == team_id)
        )
    
    if is_knockout is not None:
        query = query.filter(Match.is_knockout == is_knockout)
    
    if tournament_type:
        query = query.filter(Match.tournament_type == tournament_type)
    
    return query.order_by(Match.date.desc()).offset(skip).limit(limit).all()


def update_match(db: Session, match_id: int, match_update: MatchUpdate) -> Optional[Match]:
    """
    更新比赛结果
    
    Args:
        db: 数据库会话
        match_id: 比赛 ID
        match_update: 更新数据
        
    Returns:
        更新后的比赛对象，不存在则返回 None
    """
    db_match = get_match(db, match_id)
    if not db_match:
        return None
    
    update_data = match_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_match, field, value)
    
    db.commit()
    db.refresh(db_match)
    return db_match


def delete_match(db: Session, match_id: int) -> bool:
    """
    删除比赛
    
    Args:
        db: 数据库会话
        match_id: 比赛 ID
        
    Returns:
        是否删除成功
    """
    db_match = get_match(db, match_id)
    if not db_match:
        return False
    
    db.delete(db_match)
    db.commit()
    return True


def get_matches_by_tournament(
    db: Session,
    tournament_type: str
) -> list[Match]:
    """
    获取指定赛事的所有比赛
    
    Args:
        db: 数据库会话
        tournament_type: 赛事类型
        
    Returns:
        比赛列表
    """
    return db.query(Match).filter(
        Match.tournament_type == tournament_type
    ).order_by(Match.date).all()


# ============ Simulation Record CRUD ============

def create_simulation_record(
    db: Session, 
    record: SimulationRecordCreate
) -> SimulationRecord:
    """
    创建模拟记录
    
    Args:
        db: 数据库会话
        record: 模拟记录数据
        
    Returns:
        创建的模拟记录对象
    """
    # 验证冠军队伍存在
    champion = get_team(db, record.champion_team_id)
    if not champion:
        raise ValueError("Champion team does not exist")
    
    # 如果 simulation_log 是字典，转换为 JSON 字符串
    simulation_log = record.simulation_log
    if isinstance(simulation_log, dict):
        simulation_log = json.dumps(simulation_log, ensure_ascii=False)
    
    db_record = SimulationRecord(
        version=record.version,
        champion_team_id=record.champion_team_id,
        simulation_log=simulation_log
    )
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    return db_record


def get_simulation_record(db: Session, record_id: int) -> Optional[SimulationRecord]:
    """
    根据 ID 获取模拟记录
    
    Args:
        db: 数据库会话
        record_id: 记录 ID
        
    Returns:
        模拟记录对象，不存在则返回 None
    """
    return db.query(SimulationRecord).filter(
        SimulationRecord.id == record_id
    ).first()


def get_simulation_records(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    version: Optional[str] = None,
    champion_team_id: Optional[int] = None
) -> list[SimulationRecord]:
    """
    获取模拟记录列表
    
    Args:
        db: 数据库会话
        skip: 跳过记录数
        limit: 限制返回数
        version: 按版本筛选
        champion_team_id: 按冠军队伍筛选
        
    Returns:
        模拟记录列表
    """
    query = db.query(SimulationRecord)
    
    if version:
        query = query.filter(SimulationRecord.version == version)
    
    if champion_team_id:
        query = query.filter(SimulationRecord.champion_team_id == champion_team_id)
    
    return query.order_by(SimulationRecord.created_at.desc()).offset(skip).limit(limit).all()


def get_simulation_record_by_version(
    db: Session,
    version: str
) -> Optional[SimulationRecord]:
    """
    根据版本获取最新的模拟记录
    
    Args:
        db: 数据库会话
        version: 版本号
        
    Returns:
        最新的模拟记录，不存在则返回 None
    """
    return db.query(SimulationRecord).filter(
        SimulationRecord.version == version
    ).order_by(SimulationRecord.created_at.desc()).first()


def delete_simulation_record(db: Session, record_id: int) -> bool:
    """
    删除模拟记录
    
    Args:
        db: 数据库会话
        record_id: 记录 ID
        
    Returns:
        是否删除成功
    """
    db_record = get_simulation_record(db, record_id)
    if not db_record:
        return False
    
    db.delete(db_record)
    db.commit()
    return True


def get_simulation_stats(
    db: Session,
    version: Optional[str] = None
) -> dict:
    """
    获取模拟统计数据
    
    Args:
        db: 数据库会话
        version: 按版本筛选
        
    Returns:
        统计字典，包含总记录数和冠军分布
    """
    query = db.query(SimulationRecord)
    
    if version:
        query = query.filter(SimulationRecord.version == version)
    
    total = query.count()
    
    # 获取冠军分布
    champion_stats = db.query(
        SimulationRecord.champion_team_id,
        func.count(SimulationRecord.id).label('count')
    )
    
    if version:
        champion_stats = champion_stats.filter(SimulationRecord.version == version)
    
    champion_stats = champion_stats.group_by(
        SimulationRecord.champion_team_id
    ).all()
    
    return {
        "total_simulations": total,
        "champion_distribution": {
            str(row.champion_team_id): row.count 
            for row in champion_stats
        }
    }


def parse_simulation_log(record: SimulationRecord) -> Optional[dict]:
    """
    解析模拟记录的 JSON 日志
    
    Args:
        record: 模拟记录对象
        
    Returns:
        解析后的字典，失败则返回 None
    """
    if not record.simulation_log:
        return None
    
    try:
        return json.loads(record.simulation_log)
    except (json.JSONDecodeError, TypeError):
        return None
