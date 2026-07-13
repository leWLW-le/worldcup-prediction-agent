"""
重新生成冠军预测
使用集成模型模拟2026世界杯
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
import numpy as np
from collections import defaultdict
from sqlalchemy import text

from app.db.database import SessionLocal
from app.models.schemas import Team, Match
from app.services.ensemble_prediction_service import EnsemblePredictionService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_group_stage_matches(db) -> list:
    """获取2026世界杯小组赛对阵"""
    # 2026世界杯48队12组
    groups = {
        'A': ['Canada', 'Mexico', 'South Africa', 'Ecuador'],
        'B': ['Argentina', 'Algeria', 'Austria', 'Jordan'],
        'C': ['Brazil', 'Morocco', 'Scotland', 'Haiti'],
        'D': ['United States', 'Paraguay', 'Australia', 'TBD_D4'],
        'E': ['Germany', 'Curacao', 'Ecuador', 'TBD_E4'],
        'F': ['France', 'Colombia', 'Senegal', 'TBD_F4'],
        'G': ['Spain', 'Croatia', 'Saudi Arabia', 'TBD_G4'],
        'H': ['Portugal', 'Uruguay', 'South Korea', 'TBD_H4'],
        'I': ['Japan', 'Iran', 'TBD_I3', 'TBD_I4'],
        'J': ['England', 'Ghana', 'TBD_J3', 'TBD_J4'],
        'K': ['Netherlands', 'TBD_K2', 'TBD_K3', 'TBD_K4'],
        'L': ['Belgium', 'Egypt', 'TBD_L3', 'TBD_L4'],
    }
    return groups


def simulate_match(ensemble_service, home_team_obj, away_team_obj) -> dict:
    """模拟单场比赛"""
    try:
        result = ensemble_service.predict_with_ensemble(home_team_obj, away_team_obj)
        return result
    except Exception as e:
        logger.warning(f"Ensemble prediction failed for {home_team_obj.name} vs {away_team_obj.name}: {e}")
        # Fallback to ELO only
        from app.services.prediction_service import PredictionService
        fallback = PredictionService(ensemble_service.db)
        return fallback._predict_with_elo(home_team_obj, away_team_obj)


def simulate_tournament(n_simulations: int = 1000):
    """
    模拟整个锦标赛
    
    Args:
        n_simulations: 模拟次数
        
    Returns:
        冠军概率分布
    """
    db = SessionLocal()
    ensemble_service = EnsemblePredictionService(db)
    
    try:
        # 获取所有球队
        teams = db.query(Team).all()
        team_by_name = {t.name: t for t in teams}
        
        logger.info(f"Loaded {len(teams)} teams from database")
        
        # 冠军计数
        champion_counts = defaultdict(int)
        runner_up_counts = defaultdict(int)
        
        groups = get_group_stage_matches(db)
        
        for sim in range(n_simulations):
            if (sim + 1) % 100 == 0:
                logger.info(f"Simulation {sim + 1}/{n_simulations}")
            
            # 简化模拟：使用球队ELO直接模拟淘汰赛
            # 获取有ELO评分的球队
            rated_teams = [t for t in teams if t.current_elo and t.current_elo > 0]
            
            if len(rated_teams) < 2:
                logger.warning("Not enough rated teams for simulation")
                break
            
            # 随机打乱进行淘汰赛模拟
            np.random.shuffle(rated_teams)
            
            # 简化的淘汰赛模拟
            current_round = rated_teams[:32]  # 取前32队
            
            while len(current_round) > 1:
                next_round = []
                for i in range(0, len(current_round), 2):
                    if i + 1 < len(current_round):
                        home = current_round[i]
                        away = current_round[i + 1]
                        
                        pred = simulate_match(ensemble_service, home, away)
                        
                        if pred['home_score'] > pred['away_score']:
                            next_round.append(home)
                        elif pred['away_score'] > pred['home_score']:
                            next_round.append(away)
                        else:
                            # 平局：点球大战（ELO高的赢）
                            if home.current_elo >= away.current_elo:
                                next_round.append(home)
                            else:
                                next_round.append(away)
                    else:
                        next_round.append(current_round[i])
                
                current_round = next_round
            
            champion = current_round[0]
            champion_counts[champion.name] += 1
        
        # 计算概率
        total = sum(champion_counts.values())
        champion_probs = {
            team: count / total 
            for team, count in sorted(champion_counts.items(), key=lambda x: -x[1])
        }
        
        # 结果
        results = {
            'n_simulations': n_simulations,
            'champion_probabilities': dict(list(champion_probs.items())[:20]),
            'top_champion': list(champion_probs.keys())[0] if champion_probs else None,
            'top_probability': list(champion_probs.values())[0] if champion_probs else 0,
        }
        
        # 特别关注法国
        france_prob = champion_probs.get('France', 0)
        results['france_champion_probability'] = france_prob
        
        logger.info("\n" + "=" * 60)
        logger.info("冠军预测结果")
        logger.info("=" * 60)
        logger.info(f"模拟次数: {n_simulations}")
        logger.info(f"\nTop 10 冠军概率:")
        for i, (team, prob) in enumerate(list(champion_probs.items())[:10]):
            logger.info(f"  {i+1}. {team}: {prob:.2%}")
        
        logger.info(f"\n法国冠军概率: {france_prob:.2%}")
        
        # 保存结果
        output_file = "data/champion_prediction_ensemble.json"
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"\n结果已保存到 {output_file}")
        
        return results
        
    finally:
        db.close()


if __name__ == "__main__":
    results = simulate_tournament(n_simulations=1000)
    
    print("\n=== 冠军预测完成 ===")
    print(f"最可能冠军: {results['top_champion']} ({results['top_probability']:.2%})")
    print(f"法国冠军概率: {results['france_champion_probability']:.2%}")
