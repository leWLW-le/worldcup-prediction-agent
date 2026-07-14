"""
幂等数据库初始化脚本
- 创建缺失表
- 从 JSON 种子数据导入最低限度比赛数据（半决赛）
- 创建缺失球队
- 重复运行不插入重复数据
- 不 drop 表、不清空数据、不调用外部 API / LLM / Monte Carlo
"""
import json
import sys
import os
from pathlib import Path
from datetime import datetime

# 确保项目根目录在 sys.path 中
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.db.database import Base, engine, SessionLocal, DB_BACKEND
# 导入所有模型，确保 Base.metadata 包含这些表
import app.models.schemas  # noqa: F401
import app.models.agent_models  # noqa: F401
from app.models.schemas import Team
from app.models.agent_models import Fixture


# 半决赛种子数据（最低可用数据）
SEED_FIXTURES = [
    {
        "fixture_id": "seed_sf_1",
        "home_team": "France",
        "away_team": "Spain",
        "stage": "semi_finals",
        "status": "NS",
        "source": "manual_candidate",
        "source_level": "unverified_candidate",
    },
    {
        "fixture_id": "seed_sf_2",
        "home_team": "England",
        "away_team": "Argentina",
        "stage": "semi_finals",
        "status": "NS",
        "source": "manual_candidate",
        "source_level": "unverified_candidate",
    },
]

# 四强球队
SURVIVING_TEAMS = ["Argentina", "England", "France", "Spain"]


def init_tables():
    """创建所有缺失表（幂等）"""
    print(f"Database backend: {DB_BACKEND}")
    print("Creating tables if missing...")
    Base.metadata.create_all(bind=engine)
    print("Tables OK")


def seed_teams(session):
    """创建缺失的四强球队（幂等）"""
    created = 0
    for name in SURVIVING_TEAMS:
        existing = session.query(Team).filter(Team.name == name).first()
        if not existing:
            team = Team(name=name, current_elo=1800.0, confederation="")
            session.add(team)
            created += 1
    if created > 0:
        session.commit()
        print(f"Created {created} team(s)")
    else:
        print("Teams already exist, skipped")


def seed_fixtures(session):
    """导入半决赛种子数据（幂等）"""
    inserted = 0
    for seed in SEED_FIXTURES:
        existing = session.query(Fixture).filter(
            Fixture.fixture_id == seed["fixture_id"]
        ).first()
        if existing:
            continue
        fixture = Fixture(
            fixture_id=seed["fixture_id"],
            home_team=seed["home_team"],
            away_team=seed["away_team"],
            stage=seed["stage"],
            status=seed["status"],
            source=seed["source"],
            source_level=seed["source_level"],
            is_verified=False,
            needs_review=False,
            fetched_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(fixture)
        inserted += 1
    if inserted > 0:
        session.commit()
        print(f"Inserted {inserted} seed fixture(s)")
    else:
        print("Seed fixtures already exist, skipped")


def main():
    print("=" * 50)
    print("World Cup DB Init (idempotent)")
    print("=" * 50)

    # 1. 建表
    init_tables()

    # 2. 种子数据
    session = SessionLocal()
    try:
        seed_teams(session)
        seed_fixtures(session)
    except Exception as e:
        session.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        session.close()

    print("=" * 50)
    print("Init complete")
    print("=" * 50)


if __name__ == "__main__":
    main()
