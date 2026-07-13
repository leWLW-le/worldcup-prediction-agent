"""
CRUD 功能测试脚本
验证 Team, Match, SimulationRecord 的增删改查功能
"""
from datetime import datetime
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, init_db
from app.models.schemas import Team, Match, SimulationRecord
from app.models.pydantic_models import (
    TeamCreate, TeamUpdate,
    MatchCreate, MatchUpdate,
    SimulationRecordCreate
)
from app import crud


def test_team_crud():
    """测试球队 CRUD"""
    print("\n" + "="*60)
    print("测试球队 CRUD")
    print("="*60)
    
    db = SessionLocal()
    
    try:
        # 1. 创建球队
        print("\n1️⃣  创建球队...")
        team_data = TeamCreate(
            name="Brazil",
            confederation="CONMEBOL",
            current_elo=2050.5
        )
        team = crud.create_team(db, team_data)
        print(f"✅ 创建成功: {team.name} (ELO: {team.current_elo})")
        
        # 2. 获取球队
        print("\n2️⃣  获取球队...")
        retrieved_team = crud.get_team(db, team.id)
        print(f"✅ 获取成功: {retrieved_team.name}")
        
        # 3. 更新球队
        print("\n3️⃣  更新球队...")
        update_data = TeamUpdate(current_elo=2060.0)
        updated_team = crud.update_team(db, team.id, update_data)
        print(f"✅ 更新成功: ELO {updated_team.current_elo}")
        
        # 4. 获取所有球队
        print("\n4️⃣  获取所有球队...")
        teams = crud.get_teams(db)
        print(f"✅ 共 {len(teams)} 支球队")
        
        # 5. 按 ELO 范围查询
        print("\n5️⃣  按 ELO 范围查询...")
        high_elo_teams = crud.get_teams_by_elo_range(db, 2000, 2100)
        print(f"✅ ELO 2000-2100 的球队: {len(high_elo_teams)} 支")
        
        # 6. 删除球队
        print("\n6️⃣  删除球队...")
        deleted = crud.delete_team(db, team.id)
        print(f"✅ 删除{'成功' if deleted else '失败'}")
        
        print("\n✅ 球队 CRUD 测试通过！")
        
    except Exception as e:
        print(f"\n❌ 球队 CRUD 测试失败: {e}")
        raise
    finally:
        db.close()


def test_match_crud():
    """测试比赛 CRUD"""
    print("\n" + "="*60)
    print("测试比赛 CRUD")
    print("="*60)
    
    db = SessionLocal()
    
    try:
        # 先创建两支球队
        team_a = crud.create_team(db, TeamCreate(name="Argentina", confederation="CONMEBOL", current_elo=2100))
        team_b = crud.create_team(db, TeamCreate(name="France", confederation="UEFA", current_elo=2080))
        
        # 1. 创建比赛
        print("\n1️⃣  创建比赛...")
        match_data = MatchCreate(
            date=datetime(2026, 7, 15, 20, 0),
            team_a_id=team_a.id,
            team_b_id=team_b.id,
            is_knockout=True,
            tournament_type="World Cup 2026"
        )
        match = crud.create_match(db, match_data)
        print(f"✅ 创建成功: {match.team_a_id} vs {match.team_b_id}")
        
        # 2. 获取比赛
        print("\n2️⃣  获取比赛...")
        retrieved_match = crud.get_match(db, match.id)
        print(f"✅ 获取成功: 淘汰赛={retrieved_match.is_knockout}")
        
        # 3. 更新比赛结果
        print("\n3️⃣  更新比赛结果...")
        update_data = MatchUpdate(score_a=2, score_b=1)
        updated_match = crud.update_match(db, match.id, update_data)
        print(f"✅ 更新成功: {updated_match.score_a}-{updated_match.score_b}")
        
        # 4. 获取所有比赛
        print("\n4️⃣  获取所有比赛...")
        matches = crud.get_matches(db)
        print(f"✅ 共 {len(matches)} 场比赛")
        
        # 5. 按赛事类型查询
        print("\n5️⃣  按赛事类型查询...")
        wc_matches = crud.get_matches_by_tournament(db, "World Cup 2026")
        print(f"✅ World Cup 2026 比赛: {len(wc_matches)} 场")
        
        # 清理数据
        crud.delete_match(db, match.id)
        crud.delete_team(db, team_a.id)
        crud.delete_team(db, team_b.id)
        
        print("\n✅ 比赛 CRUD 测试通过！")
        
    except Exception as e:
        print(f"\n❌ 比赛 CRUD 测试失败: {e}")
        raise
    finally:
        db.close()


def test_simulation_record_crud():
    """测试模拟记录 CRUD"""
    print("\n" + "="*60)
    print("测试模拟记录 CRUD")
    print("="*60)
    
    db = SessionLocal()
    
    try:
        # 先创建一支球队作为冠军
        champion = crud.create_team(db, TeamCreate(name="Spain", confederation="UEFA", current_elo=2020))
        
        # 1. 创建模拟记录
        print("\n1️⃣  创建模拟记录...")
        import json
        simulation_log = {
            "total_simulations": 10000,
            "method": "Monte Carlo",
            "iterations": 10000,
            "top_4": ["Spain", "Brazil", "Argentina", "France"]
        }
        record_data = SimulationRecordCreate(
            version="v1.0-monte-carlo",
            champion_team_id=champion.id,
            simulation_log=json.dumps(simulation_log, ensure_ascii=False)
        )
        record = crud.create_simulation_record(db, record_data)
        print(f"✅ 创建成功: 版本={record.version}, 冠军ID={record.champion_team_id}")
        
        # 2. 获取模拟记录
        print("\n2️⃣  获取模拟记录...")
        retrieved_record = crud.get_simulation_record(db, record.id)
        print(f"✅ 获取成功: {retrieved_record.version}")
        
        # 3. 解析 JSON 日志
        print("\n3️⃣  解析 JSON 日志...")
        log_data = crud.parse_simulation_log(retrieved_record)
        if log_data:
            print(f"✅ 解析成功: 总模拟次数={log_data['total_simulations']}")
        
        # 4. 获取所有模拟记录
        print("\n4️⃣  获取所有模拟记录...")
        records = crud.get_simulation_records(db)
        print(f"✅ 共 {len(records)} 条记录")
        
        # 5. 获取统计数据
        print("\n5️⃣  获取统计数据...")
        stats = crud.get_simulation_stats(db)
        print(f"✅ 统计: 总记录数={stats['total_simulations']}")
        
        # 6. 按版本查询
        print("\n6️⃣  按版本查询...")
        version_record = crud.get_simulation_record_by_version(db, "v1.0-monte-carlo")
        print(f"✅ 找到版本记录: {version_record.version if version_record else 'None'}")
        
        # 清理数据
        crud.delete_simulation_record(db, record.id)
        crud.delete_team(db, champion.id)
        
        print("\n✅ 模拟记录 CRUD 测试通过！")
        
    except Exception as e:
        print(f"\n❌ 模拟记录 CRUD 测试失败: {e}")
        raise
    finally:
        db.close()


def main():
    """运行所有测试"""
    print("\n" + "🚀"*30)
    print("开始 CRUD 功能测试")
    print("🚀"*30)
    
    # 初始化数据库
    init_db()
    
    try:
        test_team_crud()
        test_match_crud()
        test_simulation_record_crud()
        
        print("\n" + "✨"*30)
        print("✅ 所有 CRUD 测试通过！")
        print("✨"*30 + "\n")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        raise


if __name__ == "__main__":
    main()
