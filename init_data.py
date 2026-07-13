"""
数据初始化脚本
用于加载示例球队和比赛数据
"""
from sqlalchemy.orm import Session
from app.db.database import SessionLocal, init_db
from app.models.schemas import Team, Match


def init_sample_data():
    """初始化示例数据"""
    # 创建数据库表
    init_db()
    
    db = SessionLocal()
    
    try:
        # 检查是否已有数据
        if db.query(Team).first():
            print("数据已存在，跳过初始化")
            return
        
        print("开始初始化示例数据...")
        
        # 添加示例球队（2026世界杯部分参赛队伍）
        teams_data = [
            {"name": "Argentina", "confederation": "CONMEBOL", "current_elo": 2100.0},
            {"name": "France", "confederation": "UEFA", "current_elo": 2080.0},
            {"name": "Brazil", "confederation": "CONMEBOL", "current_elo": 2060.0},
            {"name": "England", "confederation": "UEFA", "current_elo": 2040.0},
            {"name": "Spain", "confederation": "UEFA", "current_elo": 2020.0},
            {"name": "Germany", "confederation": "UEFA", "current_elo": 2000.0},
            {"name": "Portugal", "confederation": "UEFA", "current_elo": 1980.0},
            {"name": "Netherlands", "confederation": "UEFA", "current_elo": 1960.0},
        ]
        
        teams = []
        for team_data in teams_data:
            team = Team(**team_data)
            db.add(team)
            teams.append(team)
        
        db.commit()
        
        # 刷新以获取 ID
        for team in teams:
            db.refresh(team)
        
        print(f"✅ 添加了 {len(teams)} 支球队")
        
        # 添加示例比赛（小组赛）
        from datetime import datetime
        matches_data = [
            {
                "date": datetime(2026, 6, 15, 18, 0),
                "team_a_id": teams[0].id,  # Argentina
                "team_b_id": teams[1].id,  # France
                "tournament_type": "World Cup 2026"
            },
            {
                "date": datetime(2026, 6, 15, 21, 0),
                "team_a_id": teams[2].id,  # Brazil
                "team_b_id": teams[3].id,  # England
                "tournament_type": "World Cup 2026"
            },
        ]
        
        for match_data in matches_data:
            match = Match(**match_data)
            db.add(match)
        
        db.commit()
        print(f"✅ 添加了 {len(matches_data)} 场比赛")
        
        print("✨ 示例数据初始化完成！")
        
    except Exception as e:
        db.rollback()
        print(f"❌ 初始化失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_sample_data()
