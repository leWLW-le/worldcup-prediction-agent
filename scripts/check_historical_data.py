"""
历史数据验收脚本
检查历史比赛数据的质量和完整性
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.db.database import SessionLocal
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_historical_data():
    """
    检查历史比赛数据
    
    检查项：
    1. 历史比赛数量 > 5000
    2. 时间跨度 >= 10年
    3. 球队数量 >= 100
    4. 缺失率 < 5%
    5. 重复比赛
    6. 异常比分
    """
    db = SessionLocal()
    
    try:
        logger.info("=" * 60)
        logger.info("历史数据验收检查")
        logger.info("=" * 60)
        
        # 1. 总比赛数量
        total_matches = db.execute(
            text("SELECT COUNT(*) FROM historical_matches")
        ).scalar() or 0
        
        logger.info(f"\n1. 历史比赛数量: {total_matches}")
        if total_matches >= 5000:
            logger.info("   ✓ 通过 (目标: >= 5000)")
        else:
            logger.warning(f"   ✗ 未通过 (目标: >= 5000, 实际: {total_matches})")
        
        # 2. 时间跨度
        date_range = db.execute(
            text("""
                SELECT
                    MIN(date) as min_date,
                    MAX(date) as max_date,
                    CAST(julianday(MAX(date)) - julianday(MIN(date)) AS INTEGER) as days
                FROM historical_matches
            """)
        ).fetchone()
        
        min_date = date_range[0]
        max_date = date_range[1]
        days = date_range[2] or 0
        years = days / 365.25
        
        logger.info(f"\n2. 时间跨度: {years:.1f} 年")
        logger.info(f"   从 {min_date} 到 {max_date}")
        if years >= 10:
            logger.info("   ✓ 通过 (目标: >= 10年)")
        else:
            logger.warning(f"   ✗ 未通过 (目标: >= 10年, 实际: {years:.1f}年)")
        
        # 3. 球队数量
        team_count = db.execute(
            text("""
                SELECT COUNT(DISTINCT id) FROM teams
                WHERE id IN (
                    SELECT DISTINCT home_team_id FROM historical_matches
                    UNION
                    SELECT DISTINCT away_team_id FROM historical_matches
                )
            """)
        ).scalar() or 0
        
        logger.info(f"\n3. 球队数量: {team_count}")
        if team_count >= 100:
            logger.info("   ✓ 通过 (目标: >= 100)")
        else:
            logger.warning(f"   ✗ 未通过 (目标: >= 100, 实际: {team_count})")
        
        # 4. 缺失率检查
        null_checks = {
            'home_score': 'SELECT COUNT(*) FROM historical_matches WHERE home_score IS NULL',
            'away_score': 'SELECT COUNT(*) FROM historical_matches WHERE away_score IS NULL',
            'result': 'SELECT COUNT(*) FROM historical_matches WHERE result IS NULL',
            'competition': 'SELECT COUNT(*) FROM historical_matches WHERE competition IS NULL'
        }
        
        logger.info(f"\n4. 缺失率检查:")
        total_nulls = 0
        for field, query in null_checks.items():
            null_count = db.execute(text(query)).scalar() or 0
            null_rate = (null_count / total_matches * 100) if total_matches > 0 else 0
            total_nulls += null_count
            
            if null_rate < 5:
                logger.info(f"   {field}: {null_count} ({null_rate:.2f}%) ✓")
            else:
                logger.warning(f"   {field}: {null_count} ({null_rate:.2f}%) ✗ (目标: < 5%)")
        
        overall_null_rate = (total_nulls / (total_matches * len(null_checks)) * 100) if total_matches > 0 else 0
        logger.info(f"   总体缺失率: {overall_null_rate:.2f}%")
        if overall_null_rate < 5:
            logger.info("   ✓ 通过 (目标: < 5%)")
        else:
            logger.warning(f"   ✗ 未通过 (目标: < 5%, 实际: {overall_null_rate:.2f}%)")
        
        # 5. 重复比赛检查
        duplicates = db.execute(
            text("""
                SELECT date, home_team_id, away_team_id, COUNT(*) as count
                FROM historical_matches
                GROUP BY date, home_team_id, away_team_id
                HAVING count > 1
                ORDER BY count DESC
                LIMIT 10
            """)
        ).fetchall()
        
        logger.info(f"\n5. 重复比赛检查:")
        if not duplicates:
            logger.info("   ✓ 通过 (无重复)")
        else:
            logger.warning(f"   ✗ 发现 {len(duplicates)} 组重复比赛:")
            for dup in duplicates[:5]:
                logger.warning(f"      {dup[0]}: 球队 {dup[1]} vs {dup[2]} (出现 {dup[3]} 次)")
        
        # 6. 异常比分检查
        abnormal_scores = db.execute(
            text("""
                SELECT id, date, home_team_id, away_team_id, home_score, away_score
                FROM historical_matches
                WHERE home_score < 0 OR home_score > 20
                   OR away_score < 0 OR away_score > 20
                ORDER BY date DESC
                LIMIT 10
            """)
        ).fetchall()
        
        logger.info(f"\n6. 异常比分检查:")
        if not abnormal_scores:
            logger.info("   ✓ 通过 (无异常比分)")
        else:
            logger.warning(f"   ✗ 发现 {len(abnormal_scores)} 场异常比分:")
            for match in abnormal_scores[:5]:
                logger.warning(f"      {match[1]}: 球队 {match[2]} vs {match[3]}, 比分 {match[4]}-{match[5]}")
        
        # 7. 结果分布
        result_dist = db.execute(
            text("""
                SELECT result, COUNT(*) as count
                FROM historical_matches
                GROUP BY result
                ORDER BY count DESC
            """)
        ).fetchall()
        
        logger.info(f"\n7. 结果分布:")
        for row in result_dist:
            percentage = (row[1] / total_matches * 100) if total_matches > 0 else 0
            logger.info(f"   {row[0]}: {row[1]} ({percentage:.1f}%)")
        
        # 8. 赛事分布
        competition_dist = db.execute(
            text("""
                SELECT competition, COUNT(*) as count
                FROM historical_matches
                WHERE competition IS NOT NULL
                GROUP BY competition
                ORDER BY count DESC
                LIMIT 10
            """)
        ).fetchall()
        
        logger.info(f"\n8. 赛事分布 (Top 10):")
        for row in competition_dist:
            logger.info(f"   {row[0]}: {row[1]}")
        
        # 总结
        logger.info("\n" + "=" * 60)
        logger.info("验收总结")
        logger.info("=" * 60)
        
        passed = 0
        total = 6
        
        if total_matches >= 5000:
            passed += 1
        if years >= 10:
            passed += 1
        if team_count >= 100:
            passed += 1
        if overall_null_rate < 5:
            passed += 1
        if not duplicates:
            passed += 1
        if not abnormal_scores:
            passed += 1
        
        logger.info(f"\n通过: {passed}/{total}")
        
        if passed == total:
            logger.info("✓ 所有检查通过！数据质量良好。")
        else:
            logger.warning(f"✗ {total - passed} 项检查未通过，需要改进。")
        
        return {
            'total_matches': total_matches,
            'years_span': years,
            'team_count': team_count,
            'null_rate': overall_null_rate,
            'duplicates': len(duplicates),
            'abnormal_scores': len(abnormal_scores),
            'passed': passed,
            'total': total
        }
        
    except Exception as e:
        logger.error(f"检查失败: {e}")
        return None
    finally:
        db.close()


if __name__ == "__main__":
    results = check_historical_data()
    
    if results:
        print("\n=== 数据验收结果 ===")
        print(f"历史比赛数量: {results['total_matches']}")
        print(f"时间跨度: {results['years_span']:.1f} 年")
        print(f"球队数量: {results['team_count']}")
        print(f"缺失率: {results['null_rate']:.2f}%")
        print(f"重复比赛: {results['duplicates']}")
        print(f"异常比分: {results['abnormal_scores']}")
        print(f"通过检查: {results['passed']}/{results['total']}")
