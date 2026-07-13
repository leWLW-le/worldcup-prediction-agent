"""
Fixtures 数据库模型
存储从外部 API 获取的真实比赛数据
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, JSON
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List, Dict, Any

from app.db.database import Base, engine


class Fixture(Base):
    """比赛数据表 - 存储从外部 API 获取的真实赛程和比分"""
    __tablename__ = "fixtures"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    fixture_id = Column(String(100), unique=True, index=True, nullable=False)  # 唯一标识
    api_fixture_id = Column(String(100), index=True)  # API 原始 fixture ID

    # 球队信息
    home_team = Column(String(100), nullable=False, index=True)
    away_team = Column(String(100), nullable=False, index=True)
    home_team_id = Column(String(50))
    away_team_id = Column(String(50))

    # 比赛信息
    match_date = Column(DateTime, index=True)
    stage = Column(String(50))  # group_stage, round_of_32, round_of_16, quarter_finals, semi_finals, final
    status = Column(String(50), index=True)  # NS, LIVE, FT, AET, PEN

    # 比分
    home_score = Column(Integer)
    away_score = Column(Integer)
    winner = Column(String(100))

    # 数据来源
    source = Column(String(50), index=True)  # football_data, api_football
    source_level = Column(String(50), index=True)  # external_real, verified_cache
    is_verified = Column(Boolean, default=False)
    needs_review = Column(Boolean, default=False)

    # 时间戳
    fetched_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 原始数据
    raw_payload = Column(Text)  # JSON 格式的原始 API 响应


def init_fixtures_table():
    """初始化 fixtures 表"""
    Base.metadata.create_all(bind=engine, tables=[Fixture.__table__])


class FixturesRepository:
    """Fixtures 数据访问层"""

    def __init__(self, db: Optional[Session] = None):
        if db is None:
            from app.db.database import SessionLocal
            self.db = SessionLocal()
            self._owns_session = True
        else:
            self.db = db
            self._owns_session = False

    def __del__(self):
        if self._owns_session and self.db:
            self.db.close()

    def get_all(self, season: int = 2026) -> List[Fixture]:
        """获取所有 fixtures"""
        return self.db.query(Fixture).order_by(Fixture.match_date).all()

    def get_by_source(self, source: str) -> List[Fixture]:
        """按来源获取 fixtures"""
        return self.db.query(Fixture).filter(Fixture.source == source).all()

    def get_count(self) -> int:
        """获取 fixtures 总数"""
        return self.db.query(Fixture).count()

    def get_by_fixture_id(self, fixture_id: str) -> Optional[Fixture]:
        """按 fixture_id 获取"""
        return self.db.query(Fixture).filter(Fixture.fixture_id == fixture_id).first()

    def upsert_fixture(self, fixture_data: Dict[str, Any]) -> bool:
        """插入或更新 fixture"""
        fixture_id = fixture_data.get("fixture_id")
        if not fixture_id:
            return False

        existing = self.get_by_fixture_id(fixture_id)
        if existing:
            # 更新
            for key, value in fixture_data.items():
                if hasattr(existing, key) and key != "id":
                    setattr(existing, key, value)
            existing.updated_at = datetime.utcnow()
        else:
            # 插入
            new_fixture = Fixture(**fixture_data)
            self.db.add(new_fixture)

        try:
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            return False

    def upsert_fixtures_batch(self, fixtures: List[Dict[str, Any]]) -> Dict[str, int]:
        """批量插入或更新 fixtures"""
        inserted = 0
        updated = 0

        for fixture_data in fixtures:
            fixture_id = fixture_data.get("fixture_id")
            if not fixture_id:
                continue

            existing = self.get_by_fixture_id(fixture_id)
            if existing:
                for key, value in fixture_data.items():
                    if hasattr(existing, key) and key not in ("id", "fixture_id"):
                        setattr(existing, key, value)
                existing.updated_at = datetime.utcnow()
                updated += 1
            else:
                new_fixture = Fixture(**fixture_data)
                self.db.add(new_fixture)
                inserted += 1

        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise e

        return {"inserted": inserted, "updated": updated}

    def get_data_status(self) -> Dict[str, Any]:
        """获取数据来源状态"""
        total = self.get_count()
        if total == 0:
            return {
                "fixtures_count": 0,
                "source": "unavailable",
                "source_level": "unavailable",
                "is_external_realtime": False,
                "is_verified": False,
                "last_updated": None,
            }

        # 按 source 统计
        sources = {}
        for row in self.db.query(Fixture.source, Fixture.source_level).distinct().all():
            src = row[0] or "unknown"
            level = row[1] or "unknown"
            sources[src] = level

        # 判断主要来源
        external_sources = {"football_data", "api_football"}
        has_external = bool(external_sources & set(sources.keys()))

        # 获取最近更新时间
        last_fixture = self.db.query(Fixture).order_by(Fixture.updated_at.desc()).first()
        last_updated = last_fixture.updated_at.isoformat() if last_fixture and last_fixture.updated_at else None

        if has_external:
            primary_source = next((s for s in ["football_data", "api_football"] if s in sources), "unknown")
            return {
                "fixtures_count": total,
                "source": primary_source,
                "source_level": "external_real",
                "is_external_realtime": True,
                "is_verified": True,
                "last_updated": last_updated,
            }
        else:
            return {
                "fixtures_count": total,
                "source": "db_cache",
                "source_level": "verified_cache",
                "is_external_realtime": False,
                "is_verified": True,
                "last_updated": last_updated,
            }

    def clear_all(self):
        """清空所有 fixtures"""
        self.db.query(Fixture).delete()
        self.db.commit()


# 初始化表
init_fixtures_table()
