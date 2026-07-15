"""
核心配置模块
使用 pydantic-settings 管理应用配置
LLM 相关配置强制从 .env 文件读取，不受系统环境变量影响
"""
import os
import logging
from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_env_file() -> dict:
    """
    直接从 .env 文件解析配置。
    返回所有键值对（跳过注释和空行）。
    """
    env_values = {}
    env_path = Path(".env")
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    env_values[key] = value
    return env_values


# 模块加载时立即解析 .env 文件
_env_file_values = _load_env_file()


class Settings(BaseSettings):
    """应用配置类"""
    
    # 应用基础配置
    APP_NAME: str = "World Cup Prediction API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # 数据库配置
    DATABASE_URL: str = "sqlite:///./worldcup.db"
    
    # 数据目录
    DATA_DIR: str = "app/data"
    
    # Football API 配置
    # football-data.org
    FOOTBALL_DATA_API: str = ""  # 优先使用
    FOOTBALL_DATA_API_KEY: str = ""  # 兼容
    # API-Football (api-sports)
    API_FOOTBALL: str = ""  # 优先使用
    API_FOOTBALL_KEY: str = ""  # 兼容
    APISPORTS_KEY: str = ""  # 兼容旧版
    API_FOOTBALL_MAX_DAILY_CALLS: int = 100

    @property
    def football_data_api_key(self) -> str:
        """football-data.org API Key，优先级: FOOTBALL_DATA_API > FOOTBALL_DATA_API_KEY"""
        return self.FOOTBALL_DATA_API or self.FOOTBALL_DATA_API_KEY or ""

    @property
    def api_football_key(self) -> str:
        """API-Football Key，优先级: API_FOOTBALL > API_FOOTBALL_KEY > APISPORTS_KEY"""
        return self.API_FOOTBALL or self.API_FOOTBALL_KEY or self.APISPORTS_KEY or ""
    
    # 预测模型配置
    PREDICTION_MODEL_PATH: str = "app/data/models"
    MODEL_PATH: str = "models/feature_network_v2_latest.pth"

    # 调度器开关（生产环境多实例时只在一个实例启用）
    ENABLE_SCHEDULER: bool = True

    # 运行环境: development / production
    ENVIRONMENT: str = "development"
    
    # LLM API 配置（用于 LLM 解释器）
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-3.5-turbo"
    USE_LOCAL_MODEL: bool = False
    LOCAL_MODEL_URL: str = "http://localhost:11434"
    LOCAL_MODEL_NAME: str = "llama2"
    
    def __init__(self, **kwargs):
        # 强制用 .env 文件中的值覆盖 LLM 相关配置
        # 这样即使系统环境变量设置了其他值，也以 .env 为准
        for key in ["OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL",
                     "USE_LOCAL_MODEL", "LOCAL_MODEL_URL", "LOCAL_MODEL_NAME",
                     "FOOTBALL_DATA_API", "FOOTBALL_DATA_API_KEY",
                     "API_FOOTBALL", "API_FOOTBALL_KEY", "APISPORTS_KEY",
                     "API_FOOTBALL_MAX_DAILY_CALLS"]:
            if key in _env_file_values:
                val = _env_file_values[key]
                if key == "USE_LOCAL_MODEL":
                    kwargs[key] = val.lower() == "true"
                elif key in ("PORT", "API_FOOTBALL_MAX_DAILY_CALLS"):
                    kwargs[key] = int(val)
                else:
                    kwargs[key] = val
        super().__init__(**kwargs)


@lru_cache()
def get_settings() -> Settings:
    """
    获取配置单例
    
    注意：.env 文件中的配置会强制覆盖系统环境变量，
    确保本地配置始终优先生效。
    """
    settings = Settings()
    
    # 强制使用 .env 文件中的值覆盖系统环境变量
    # 这确保了 .env 中的 LLM API 配置不会被系统环境变量覆盖
    if "OPENAI_API_KEY" in _env_file_values:
        settings.OPENAI_API_KEY = _env_file_values["OPENAI_API_KEY"]
    if "OPENAI_BASE_URL" in _env_file_values:
        settings.OPENAI_BASE_URL = _env_file_values["OPENAI_BASE_URL"]
    if "OPENAI_MODEL" in _env_file_values:
        settings.OPENAI_MODEL = _env_file_values["OPENAI_MODEL"]
    
    return settings


def validate_settings(s: Settings) -> None:
    """
    启动时校验必需的环境变量。
    生产环境缺少必需配置时抛出 ValueError。
    """
    errors = []
    is_prod = s.ENVIRONMENT in ("production", "prod")

    # 生产环境不允许使用 SQLite 默认值
    if is_prod and s.DATABASE_URL.startswith("sqlite"):
        errors.append(
            "DATABASE_URL is using SQLite (default). "
            "Production must use PostgreSQL."
        )

    # 生产环境必须有真实 LLM API Key
    if is_prod and not s.OPENAI_API_KEY:
        errors.append(
            "OPENAI_API_KEY is not set. "
            "Production requires a valid API key."
        )

    # MODEL_PATH 文件可以不存在（降级运行），但路径不能为空
    if not s.MODEL_PATH.strip():
        errors.append("MODEL_PATH is empty.")

    if errors:
        msg = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        logger.error(msg)
        raise ValueError(msg)

    # 打印配置状态（不输出密钥）
    logger.info("Environment: %s", s.ENVIRONMENT)
    logger.info("Database: %s", "SQLite" if s.DATABASE_URL.startswith("sqlite") else "PostgreSQL")
    logger.info("Model path: %s", s.MODEL_PATH)
    logger.info("Scheduler: %s", "enabled" if s.ENABLE_SCHEDULER else "disabled")
    logger.info("LLM API key: %s", "configured" if s.OPENAI_API_KEY else "MISSING")
