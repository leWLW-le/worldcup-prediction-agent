"""
数据管理 API

POST /api/v1/data/bootstrap-local-csv  - 初始化本地 CSV 数据
POST /api/v1/data/refresh-fixtures     - 刷新外部 fixtures 数据
POST /api/v1/data/full-refresh         - 全量刷新（赛程→存活球队→模拟→结果）
GET  /api/v1/data/status               - 获取数据来源状态
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["data"])


class BootstrapCSVRequest(BaseModel):
    """初始化本地 CSV 请求体"""
    season: int = Field(default=2026, description="世界杯赛季")
    use_llm: bool = Field(default=True, description="是否使用智谱 AI 辅助整理")


class RefreshFixturesRequest(BaseModel):
    """刷新 fixtures 请求体"""
    season: int = Field(default=2026, description="世界杯赛季")


@router.post("/bootstrap-local-csv")
def bootstrap_local_csv(request: BootstrapCSVRequest = None):
    """
    初始化本地 CSV 数据。

    1. 调用 API-Sports 获取真实 teams / fixtures / live。
    2. 导出 API cache CSV。
    3. 可选用智谱 AI 整理 team_aliases / team_ratings / competition_weights。
    4. 返回 data_manifest。
    """
    from app.services.bootstrap_service import bootstrap_local_data

    if request is None:
        request = BootstrapCSVRequest()

    result = bootstrap_local_data(season=request.season, use_llm=request.use_llm)
    return result


@router.post("/refresh-fixtures")
def refresh_fixtures(request: RefreshFixturesRequest = None):
    """
    刷新外部 fixtures 数据。
    
    优先级：
    1. football-data.org
    2. API-Football
    3. fixtures 表缓存
    4. unavailable
    """
    from app.services.data_source_manager import DataSourceManager

    if request is None:
        request = RefreshFixturesRequest()

    mgr = DataSourceManager()
    result = mgr.refresh_fixtures(season=request.season)
    return result


@router.get("/status")
def get_data_status():
    """
    获取数据来源状态。
    """
    from app.services.data_source_manager import DataSourceManager

    mgr = DataSourceManager()
    status = mgr.get_data_status()
    return status


@router.post("/full-refresh")
def full_refresh(request: RefreshFixturesRequest = None):
    """
    全量刷新流水线：

    1. 刷新 fixtures（从外部 API 拉取最新赛程/比分）
    2. 识别 surviving_teams（仍有夺冠可能的球队）
    3. Monte Carlo 模拟（只在 surviving_teams 中模拟）
    4. 更新 final_agent_result.json

    Dashboard "刷新数据" 按钮应调用此接口。
    """
    from app.services.scheduled_refresh_service import run_full_refresh_pipeline

    if request is None:
        request = RefreshFixturesRequest()

    result = run_full_refresh_pipeline(season=request.season)
    return result
