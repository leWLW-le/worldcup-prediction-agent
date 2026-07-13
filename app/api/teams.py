"""
球队相关 API 路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.database import get_db
from app.models.schemas import Team
from app.models.pydantic_models import TeamCreate, TeamResponse, ApiResponse
from app.services.prediction_service import PredictionService

router = APIRouter(
    prefix="/teams",
    tags=["teams"],
    responses={404: {"description": "Not found"}}
)


@router.get("/", response_model=List[TeamResponse])
def read_teams(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """获取所有球队列表"""
    teams = db.query(Team).offset(skip).limit(limit).all()
    return teams


@router.get("/{team_id}", response_model=TeamResponse)
def read_team(team_id: int, db: Session = Depends(get_db)):
    """根据 ID 获取球队信息"""
    team = db.query(Team).filter(Team.id == team_id).first()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


@router.post("/", response_model=TeamResponse, status_code=201)
def create_team(team: TeamCreate, db: Session = Depends(get_db)):
    """创建新球队"""
    # 检查是否已存在
    existing = db.query(Team).filter(
        (Team.name == team.name) | (Team.country_code == team.country_code)
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Team already exists")
    
    db_team = Team(**team.model_dump())
    db.add(db_team)
    db.commit()
    db.refresh(db_team)
    return db_team


@router.delete("/{team_id}", response_model=ApiResponse)
def delete_team(team_id: int, db: Session = Depends(get_db)):
    """删除球队"""
    team = db.query(Team).filter(Team.id == team_id).first()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    
    db.delete(team)
    db.commit()
    
    return ApiResponse(success=True, message="Team deleted successfully")
