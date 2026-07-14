"""
数据库连接模块
支持 SQLite（本地开发）和 PostgreSQL（生产环境）
根据 DATABASE_URL 自动选择后端
"""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from typing import Generator

from app.core.config import get_settings

settings = get_settings()

# 检测数据库类型
_db_url = settings.DATABASE_URL
_is_sqlite = _db_url.startswith("sqlite")
DB_BACKEND = "sqlite" if _is_sqlite else "postgresql"

# 根据数据库类型创建引擎
if _is_sqlite:
    engine = create_engine(
        _db_url,
        connect_args={"check_same_thread": False},
        echo=settings.DEBUG,
    )
else:
    engine = create_engine(
        _db_url,
        pool_pre_ping=True,
        echo=settings.DEBUG,
    )

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基类
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    获取数据库会话的依赖注入函数
    用于 FastAPI 路由中的依赖注入
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """初始化数据库，创建所有表"""
    Base.metadata.create_all(bind=engine)


def check_db_connection() -> bool:
    """
    轻量数据库连通性检查（用于健康检查）
    不写数据、不调外部 API、不加载模型
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
