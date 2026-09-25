"""
数据库连接模块
支持 SQLite（本地开发）和 PostgreSQL（生产环境）
根据 DATABASE_URL 自动选择后端
"""
import os
import threading
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# 检测数据库类型
_db_url = settings.DATABASE_URL
if _db_url.startswith("postgres://"):
    _db_url = "postgresql://" + _db_url[len("postgres://"):]
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
    global engine, SessionLocal, DB_BACKEND
    try:
        Base.metadata.create_all(bind=engine)
    except OperationalError:
        # Render services can retain a stale DATABASE_URL after a database is
        # removed. Keep startup deterministic only when the operator enables
        # the explicit emergency fallback; normal production remains strict.
        if os.getenv("DATABASE_FALLBACK_SQLITE", "false").lower() != "true":
            raise
        engine.dispose()
        engine = create_engine("sqlite:///./worldcup-v2.db", connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        DB_BACKEND = "sqlite-fallback"
        Base.metadata.create_all(bind=engine)


def check_db_connection(timeout: float = 5.0) -> bool:
    """
    轻量数据库连通性检查（用于健康检查）
    不写数据、不调外部 API、不加载模型
    带超时保护，防止连接不可达数据库时阻塞数十秒
    """
    result = {"ok": False}

    def _check():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            result["ok"] = True
        except Exception:
            result["ok"] = False

    t = threading.Thread(target=_check, daemon=True)
    t.start()
    t.join(timeout)
    return result["ok"]
