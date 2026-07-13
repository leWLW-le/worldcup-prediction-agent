"""
运行回测脚本
使用历史数据验证模型准确性
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from sqlalchemy import text
from app.db.database import SessionLocal
from app.services.probability_engine import ProbabilityEngine
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_backtest():
    """
    运行回测
    
    使用历史数据验证预测模型的准确性
    """
    logger.info("=" * 60)
    logger.info("运行回测")
    logger.info("=" * 60)
    
    db = SessionLocal()
    prob_engine = ProbabilityEngine()
    
    try:
        # 查询历史比赛
        matches = db.execute(
            text("""
                SELECT
                    hm.id,
                    hm.date,
                    hm.home_team_id,
                    hm.away_team_id,
                    hm.home_score,
                    hm.away_score,
                    hm.result,
                    t1.name as home_team,
                    t2.name as away_team,
                    t1.current_elo as home_elo,
                    t2.current_elo as away_elo
                FROM historical_matches hm
                JOIN teams t1 ON hm.home_team_id = t1.id
                JOIN teams t2 ON hm.away_team_id = t2.id
                WHERE hm.home_score IS NOT NULL
                AND hm.away_score IS NOT NULL
                ORDER BY hm.date DESC
                LIMIT 1000
            """)
        ).fetchall()
        
        logger.info(f"Loaded {len(matches)} matches for backtesting")
        
        # 回测指标
        total = 0
        correct_direction = 0
        correct_winner = 0
        exact_score = 0
        top3_score_coverage = 0
        
        brier_scores = []
        log_losses = []
        
        tournament_stats = {}
        confidence_bins = {
            '0.0-0.2': {'total': 0, 'correct': 0},
            '0.2-0.4': {'total': 0, 'correct': 0},
            '0.4-0.6': {'total': 0, 'correct': 0},
            '0.6-0.8': {'total': 0, 'correct': 0},
            '0.8-1.0': {'total': 0, 'correct': 0}
        }
        
        for match in matches:
            match_id = match[0]
            match_date = match[1]
            home_team_id = match[2]
            away_team_id = match[3]
            actual_home_score = match[4]
            actual_away_score = match[5]
            actual_result = match[6]
            home_team = match[7]
            away_team = match[8]
            home_elo = match[9] or 1500
            away_elo = match[10] or 1500
            
            try:
                # 预测比赛结果
                dist = prob_engine.predict_score_distribution(home_elo, away_elo)
                outcome_probs = prob_engine.calculate_match_outcome_probabilities(home_elo, away_elo)
                
                # 预测比分（最高概率）
                predicted_home = int(dist[0][0])
                predicted_away = int(dist[0][1])
                
                # 预测结果
                if outcome_probs['win_a'] > outcome_probs['draw'] and outcome_probs['win_a'] > outcome_probs['win_b']:
                    predicted_result = 'home_win'
                    confidence = outcome_probs['win_a']
                elif outcome_probs['win_b'] > outcome_probs['draw'] and outcome_probs['win_b'] > outcome_probs['win_a']:
                    predicted_result = 'away_win'
                    confidence = outcome_probs['win_b']
                else:
                    predicted_result = 'draw'
                    confidence = outcome_probs['draw']
                
                # 评估
                total += 1
                
                # 方向准确性
                if (predicted_home > predicted_away and actual_home_score > actual_away_score) or \
                   (predicted_home < predicted_away and actual_home_score < actual_away_score) or \
                   (predicted_home == predicted_away and actual_home_score == actual_away_score):
                    correct_direction += 1
                
                # 胜者准确性
                if predicted_result == actual_result:
                    correct_winner += 1
                
                # 精确比分
                if predicted_home == actual_home_score and predicted_away == actual_away_score:
                    exact_score += 1
                
                # Top-3比分覆盖
                top3_scores = [(int(d[0]), int(d[1])) for d in dist[:3]]
                actual_score_tuple = (int(actual_home_score), int(actual_away_score))
                if actual_score_tuple in top3_scores:
                    top3_score_coverage += 1
                
                # Brier score
                pred_probs = [
                    outcome_probs['win_a'],
                    outcome_probs['draw'],
                    outcome_probs['win_b']
                ]
                actual_probs = [0, 0, 0]
                if actual_result == 'home_win':
                    actual_probs[0] = 1
                elif actual_result == 'draw':
                    actual_probs[1] = 1
                else:
                    actual_probs[2] = 1
                
                brier = sum((p - a) ** 2 for p, a in zip(pred_probs, actual_probs))
                brier_scores.append(brier)
                
                # Log loss
                log_loss = -np.log(max(pred_probs[actual_probs.index(1)], 1e-10))
                log_losses.append(log_loss)
                
                # 置信度分箱
                for bin_range, stats in confidence_bins.items():
                    low, high = map(float, bin_range.split('-'))
                    if low <= confidence < high:
                        stats['total'] += 1
                        if predicted_result == actual_result:
                            stats['correct'] += 1
                        break
                
                # 赛事统计
                competition = "Unknown"
                if competition not in tournament_stats:
                    tournament_stats[competition] = {'total': 0, 'correct': 0}
                tournament_stats[competition]['total'] += 1
                if predicted_result == actual_result:
                    tournament_stats[competition]['correct'] += 1
                
            except Exception as e:
                logger.error(f"Failed to backtest match {match_id}: {e}")
                continue
        
        # 计算总体指标
        direction_accuracy = correct_direction / total if total > 0 else 0
        winner_accuracy = correct_winner / total if total > 0 else 0
        exact_score_accuracy = exact_score / total if total > 0 else 0
        top3_coverage = top3_score_coverage / total if total > 0 else 0
        avg_brier = np.mean(brier_scores) if brier_scores else 0
        avg_log_loss = np.mean(log_losses) if log_losses else 0
        
        # 置信度校准
        calibration = {}
        for bin_range, stats in confidence_bins.items():
            if stats['total'] > 0:
                calibration[bin_range] = {
                    'total': stats['total'],
                    'correct': stats['correct'],
                    'accuracy': stats['correct'] / stats['total']
                }
        
        # 结果
        results = {
            'total_matches': total,
            'direction_accuracy': direction_accuracy,
            'winner_accuracy': winner_accuracy,
            'exact_score_accuracy': exact_score_accuracy,
            'top3_score_coverage': top3_coverage,
            'brier_score': avg_brier,
            'log_loss': avg_log_loss,
            'calibration': calibration,
            'tournament_breakdown': tournament_stats
        }
        
        logger.info("\n" + "=" * 60)
        logger.info("回测结果")
        logger.info("=" * 60)
        logger.info(f"总比赛数: {total}")
        logger.info(f"方向准确率: {direction_accuracy:.2%}")
        logger.info(f"胜者准确率: {winner_accuracy:.2%}")
        logger.info(f"精确比分准确率: {exact_score_accuracy:.2%}")
        logger.info(f"Top-3比分覆盖率: {top3_coverage:.2%}")
        logger.info(f"Brier Score: {avg_brier:.4f}")
        logger.info(f"Log Loss: {avg_log_loss:.4f}")
        
        # 保存结果
        output_file = "backtest_result_historical.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"\n结果已保存到 {output_file}")
        
        return results
        
    finally:
        db.close()


if __name__ == "__main__":
    results = run_backtest()
    
    print("\n=== 回测完成 ===")
    print(f"方向准确率: {results['direction_accuracy']:.2%}")
    print(f"胜者准确率: {results['winner_accuracy']:.2%}")
    print(f"Brier Score: {results['brier_score']:.4f}")
