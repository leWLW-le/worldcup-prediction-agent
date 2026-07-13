"""
预测相关 API 路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.schemas import Team, Match, Prediction
from app.models.pydantic_models import (
    PredictTournamentRequest,
    TournamentPredictionResponse,
    PredictionCreate,
    PredictionResponse,
    ApiResponse
)
from app.services.prediction_service import PredictionService

router = APIRouter(
    prefix="/predictions",
    tags=["predictions"],
    responses={404: {"description": "Not found"}}
)


@router.post("/tournament", response_model=TournamentPredictionResponse)
def predict_tournament(
    request: PredictTournamentRequest,
    db: Session = Depends(get_db)
):
    """
    预测整个世界杯锦标赛结果
    
    包含从小组赛到决赛的完整预测流程
    """
    prediction_service = PredictionService(db)
    
    try:
        result = prediction_service.predict_tournament(
            year=request.year,
            use_historical_data=request.use_historical_data,
            model_type=request.model_type
        )
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")


@router.post("/match/{match_id}", response_model=PredictionResponse)
def predict_single_match(
    match_id: int,
    model_type: str = "elo",
    db: Session = Depends(get_db)
):
    """
    预测单场比赛结果
    
    Args:
        match_id: 比赛 ID
        model_type: 预测模型类型 (elo/poisson)
    """
    # 获取比赛信息
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    # 获取参赛队伍
    home_team = db.query(Team).filter(Team.id == match.home_team_id).first()
    away_team = db.query(Team).filter(Team.id == match.away_team_id).first()
    
    if not home_team or not away_team:
        raise HTTPException(status_code=404, detail="Teams not found")
    
    # 执行预测
    prediction_service = PredictionService(db)
    prediction_result = prediction_service.predict_match_outcome(
        home_team=home_team,
        away_team=away_team,
        model_type=model_type
    )
    
    # 确定获胜队伍
    winner_id = None
    if prediction_result["home_score"] > prediction_result["away_score"]:
        winner_id = home_team.id
    elif prediction_result["away_score"] > prediction_result["home_score"]:
        winner_id = away_team.id
    
    # 保存预测结果
    saved_prediction = prediction_service.save_prediction(
        match_id=match_id,
        predicted_home_score=prediction_result["home_score"],
        predicted_away_score=prediction_result["away_score"],
        confidence=prediction_result["confidence"],
        reasoning=prediction_result["reasoning"],
        team_id=winner_id
    )
    
    return saved_prediction


@router.get("/match/{match_id}", response_model=list[PredictionResponse])
def get_match_predictions(match_id: int, db: Session = Depends(get_db)):
    """获取某场比赛的所有预测结果"""
    predictions = db.query(Prediction).filter(
        Prediction.match_id == match_id
    ).all()
    
    return predictions


@router.delete("/{prediction_id}", response_model=ApiResponse)
def delete_prediction(prediction_id: int, db: Session = Depends(get_db)):
    """删除预测结果"""
    prediction = db.query(Prediction).filter(
        Prediction.id == prediction_id
    ).first()
    
    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found")
    
    db.delete(prediction)
    db.commit()
    
    return ApiResponse(success=True, message="Prediction deleted successfully")
