"""
历史数据导入脚本
下载并导入大量历史国际比赛数据
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import requests
import logging
from datetime import datetime

from app.db.database import init_db, SessionLocal
from app.models.schemas import HistoricalMatch
from app.services.historical_data_pipeline import HistoricalDataPipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def download_kaggle_dataset():
    """
    下载Kaggle国际比赛数据集
    来源: https://www.kaggle.com/datasets/martj42/international_results
    """
    logger.info("Downloading international matches dataset...")
    
    # 使用公开的足球数据集
    url = "https://raw.githubusercontent.com/openfootball/football-data/master/international/2020s/2020.csv"
    
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            logger.info("Downloaded successfully")
            return response.text
    except Exception as e:
        logger.warning(f"Failed to download: {e}")
    
    return None


def generate_synthetic_data():
    """
    生成合成历史数据（用于演示）
    基于真实比赛模式生成大量数据
    """
    logger.info("Generating synthetic historical data...")
    
    import random
    from datetime import timedelta
    
    # 主要国家队
    teams = [
        "Brazil", "Argentina", "France", "Germany", "Spain", "Italy", "England",
        "Portugal", "Netherlands", "Belgium", "Uruguay", "Colombia", "Chile",
        "Mexico", "USA", "Canada", "Japan", "South Korea", "Australia", "Iran",
        "Saudi Arabia", "Qatar", "Morocco", "Senegal", "Nigeria", "Ghana",
        "Cameroon", "Ivory Coast", "Algeria", "Tunisia", "Egypt", "Poland",
        "Croatia", "Serbia", "Switzerland", "Denmark", "Sweden", "Austria",
        "Russia", "Turkey", "Greece", "Czech Republic", "Romania", "Hungary",
        "Norway", "Finland", "Ireland", "Scotland", "Wales", "Northern Ireland",
        "Peru", "Paraguay", "Ecuador", "Bolivia", "Venezuela", "Costa Rica",
        "Panama", "Honduras", "Jamaica", "Haiti", "Trinidad and Tobago",
        "China", "Uzbekistan", "Iraq", "Syria", "Lebanon", "Oman", "Vietnam",
        "Thailand", "Indonesia", "Malaysia", "Jordan", "Palestine", "Bahrain",
        "United Arab Emirates", "Korea DPR", "Kyrgyzstan", "Tajikistan",
        "New Zealand", "Fiji", "New Caledonia", "Tahiti", "Solomon Islands",
        "South Africa", "Angola", "Zambia", "Zimbabwe", "Mozambique",
        "Mali", "Burkina Faso", "Guinea", "Togo", "Benin", "Niger",
        "Mauritania", "Gambia", "Guinea-Bissau", "Sierra Leone", "Liberia",
        "Cape Verde", "Congo", "DR Congo", "Gabon", "Equatorial Guinea",
        "Central African Republic", "Chad", "Sudan", "South Sudan",
        "Ethiopia", "Kenya", "Tanzania", "Uganda", "Rwanda", "Burundi",
        "Madagascar", "Mauritius", "Comoros", "Seychelles",
        "Albania", "North Macedonia", "Montenegro", "Bosnia-Herzegovina",
        "Slovenia", "Slovakia", "Ukraine", "Belarus", "Georgia", "Armenia",
        "Azerbaijan", "Kazakhstan", "Moldova", "Luxembourg", "Malta",
        "Cyprus", "Iceland", "Faroe Islands", "Estonia", "Latvia", "Lithuania",
        "Andorra", "San Marino", "Liechtenstein", "Gibraltar", "Kosovo",
        "El Salvador", "Guatemala", "Cuba", "Nicaragua", "Belize",
        "Guyana", "Suriname", "Barbados", "Bahamas", "Bermuda",
        "Curaçao", "Martinique", "Guadeloupe", "French Guiana"
    ]
    
    # 赛事类型及权重
    tournaments = [
        ("FIFA World Cup", 1.0, 0.1),
        ("FIFA World Cup Qualification", 0.9, 0.3),
        ("UEFA European Championship", 0.8, 0.05),
        ("UEFA Euro Qualification", 0.7, 0.15),
        ("Copa America", 0.75, 0.05),
        ("Africa Cup of Nations", 0.6, 0.05),
        ("AFC Asian Cup", 0.6, 0.03),
        ("CONCACAF Gold Cup", 0.55, 0.03),
        ("UEFA Nations League", 0.5, 0.08),
        ("International Friendly", 0.3, 0.16)
    ]
    
    # 球队实力分级（ELO基础分）
    team_strength = {}
    for i, team in enumerate(teams):
        if team in ["Brazil", "Argentina", "France", "Germany", "Spain", "England"]:
            team_strength[team] = 1900 + random.randint(-50, 50)
        elif team in ["Portugal", "Netherlands", "Belgium", "Uruguay", "Italy", "Colombia"]:
            team_strength[team] = 1800 + random.randint(-50, 50)
        elif team in ["Mexico", "USA", "Japan", "South Korea", "Australia", "USA"]:
            team_strength[team] = 1700 + random.randint(-50, 50)
        elif i < 50:
            team_strength[team] = 1600 + random.randint(-50, 50)
        elif i < 100:
            team_strength[team] = 1500 + random.randint(-50, 50)
        else:
            team_strength[team] = 1400 + random.randint(-50, 50)
    
    matches = []
    start_date = datetime(2010, 1, 1)
    end_date = datetime(2024, 12, 31)
    
    # 生成6000场比赛
    for _ in range(6000):
        # 随机日期
        days_diff = (end_date - start_date).days
        random_days = random.randint(0, days_diff)
        match_date = start_date + timedelta(days=random_days)
        
        # 随机选择赛事
        tournament_data = random.choices(
            tournaments,
            weights=[t[2] for t in tournaments],
            k=1
        )[0]
        tournament = tournament_data[0]
        weight = tournament_data[1]
        
        # 随机选择球队（避免自己对自己）
        home_team = random.choice(teams)
        away_team = random.choice([t for t in teams if t != home_team])
        
        # 基于实力计算比分
        home_elo = team_strength[home_team]
        away_elo = team_strength[away_team]
        
        # 主场优势
        home_elo += 80
        
        # 预期进球
        home_expected = 1.5 + (home_elo - away_elo) / 400
        away_expected = 1.5 - (home_elo - away_elo) / 400
        
        # 添加随机性
        home_expected = max(0.3, min(4.0, home_expected + random.gauss(0, 0.5)))
        away_expected = max(0.3, min(4.0, away_expected + random.gauss(0, 0.5)))
        
        # 生成比分（泊松分布）
        home_score = int(random.gauss(home_expected, 0.8))
        away_score = int(random.gauss(away_expected, 0.8))
        
        # 确保比分合理
        home_score = max(0, min(10, home_score))
        away_score = max(0, min(10, away_score))
        
        # 确定结果
        if home_score > away_score:
            result = "home_win"
        elif home_score < away_score:
            result = "away_win"
        else:
            result = "draw"
        
        # 中立场（世界杯、洲际杯等）
        neutral = tournament in ["FIFA World Cup", "Copa America", "Africa Cup of Nations",
                                  "AFC Asian Cup", "CONCACAF Gold Cup", "FIFA Confederations Cup"]
        
        matches.append({
            'date': match_date.strftime('%Y-%m-%d'),
            'home_team': home_team,
            'away_team': away_team,
            'home_score': home_score,
            'away_score': away_score,
            'tournament': tournament,
            'city': 'Neutral',
            'country': 'Neutral',
            'neutral': neutral,
            'competition_weight': weight
        })
    
    df = pd.DataFrame(matches)
    
    # 按日期排序
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    
    logger.info(f"Generated {len(df)} synthetic matches")
    logger.info(f"Date range: {df['date'].min()} to {df['date'].max()}")
    logger.info(f"Teams: {df['home_team'].nunique() + df['away_team'].nunique()}")
    
    return df


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("历史数据导入脚本")
    logger.info("=" * 60)
    
    # 初始化数据库
    logger.info("Initializing database...")
    init_db()
    
    # 生成合成数据
    df = generate_synthetic_data()
    
    # 保存为CSV
    csv_file = "data/historical_international_matches_large.csv"
    df.to_csv(csv_file, index=False)
    logger.info(f"Saved to {csv_file}")
    
    # 导入数据库
    logger.info("\nImporting to database...")
    pipeline = HistoricalDataPipeline()
    
    try:
        stats = pipeline.import_matches(csv_file, source="synthetic_generation")
        
        logger.info("\n" + "=" * 60)
        logger.info("导入完成")
        logger.info("=" * 60)
        logger.info(f"总行数: {stats['total_rows']}")
        logger.info(f"成功导入: {stats['imported_rows']}")
        logger.info(f"跳过: {stats['skipped_rows']}")
        logger.info(f"重复: {stats['duplicated_rows']}")
        
    finally:
        pipeline.close()
    
    logger.info("\n数据导入完成！")


if __name__ == "__main__":
    main()
