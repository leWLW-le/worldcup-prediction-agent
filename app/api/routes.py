"""
API 路由注册模块
集中管理所有 API 路由，包括球队、预测和模拟功能
"""
from fastapi import APIRouter

from app.api import teams, predictions, simulation, agent, data, scenario

# 创建主路由器
api_router = APIRouter()

# 注册子路由
api_router.include_router(teams.router)
api_router.include_router(predictions.router)
api_router.include_router(simulation.router)
api_router.include_router(agent.router)
api_router.include_router(data.router)
api_router.include_router(scenario.router)
