# 世界杯冠军预测 Agent 系统 - 项目架构文档

## 📋 项目概述

本项目是 **WorldCupPredictionAgent**，一个基于 Agent + Tools + State 架构的世界杯冠军预测系统。

核心设计：
- **Agent 编排层** (`app/agents/`) - WorldCupPredictionAgent 按步骤执行完整预测流程
- **Tools 工具层** (`app/tools/`) - 封装 API 数据采集、历史数据、爬虫、特征构建、比赛预测、淘汰赛推演、LLM 解释
- **Service 服务层** (`app/services/`) - 保留原有 ProbabilityEngine、TournamentSim、LLM Explainer 等核心算法
- **API 接口层** (`app/api/`) - FastAPI RESTful 接口，包含 Agent 一键预测端点
- **前端展示层** - Streamlit Dashboard，展示完整 Agent 流程

技术栈：FastAPI + Streamlit + SQLite + SQLAlchemy + 智谱AI + API-Sports

### 核心能力

用户点击「运行冠军预测 Agent」后，系统自动完成：

1. **数据计划** → 2. **数据采集** (API-Sports + 历史CSV + 爬虫) → 3. **数据校验** (DataQualityAgent)
→ 4. **特征构建** (FeatureBuilderTool) → 5. **小组赛预测** → 6. **淘汰赛逐轮推演**
→ 7. **冠军预测** → 8. **推理解释** (LLM + 规则兜底) → 9. **可视化数据输出**

**重要原则：**
- 冠军必须由数据和预测算法算出，LLM 只负责解释推理
- 即使爬虫失败、LLM 余额不足，Agent 仍能降级运行
- 真实已结束比赛不会被预测覆盖

## 🏗️ 架构设计

### Agent + Tools 分层架构

```
┌─────────────────────────────────────────┐
│       Streamlit Dashboard (前端)         │
│         debug_dashboard.py              │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│     Agent API Layer (Agent 接口层)       │
│   POST /api/v1/agent/run-prediction     │
│   POST /api/v1/agent/refresh-data       │
│   GET  /api/v1/agent/status             │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│   Agent Orchestration (Agent 编排层)     │
│   WorldCupPredictionAgent               │
│   DataQualityAgent + AgentState          │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│        Tools Layer (工具层)              │
│   APISportsTool | HistoricalDataTool     │
│   ScraperTool   | FeatureBuilderTool     │
│   MatchPredictorTool | BracketTool       │
│   ExplanationTool                        │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│    Service Layer (核心算法服务层)         │
│   ProbabilityEngine | TournamentSim      │
│   MatchExplainerAgent | PredictionService│
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│      Database Layer (数据库层)           │
│   SQLite + SQLAlchemy                    │
│   agent_runs | predicted_matches         │
│   team_features | agent_reasoning_steps  │
└─────────────────────────────────────────┘
```

## 📁 目录结构详解

```
worldcup/
├── main.py                      # 应用入口，注册 Agent 路由
├── debug_dashboard.py           # Streamlit Agent 预测面板
├── init_data.py                 # 数据初始化脚本
├── requirements.txt             # Python 依赖包
├── .env                         # 环境配置 (API key, LLM 等)
│
├── data/
│   └── historical_international_matches.csv  # 历史国际比赛数据
│
├── models/
│   └── feature_mixer_latest.pth  # PyTorch 模型权重
│
└── app/
    ├── agents/                  # Agent 编排层
    │   ├── agent_state.py       # AgentState 全局状态记录
    │   ├── worldcup_agent.py    # WorldCupPredictionAgent 核心编排
    │   └── data_quality_agent.py # DataQualityAgent 数据质量检查
    │
    ├── tools/                   # Tools 工具层
    │   ├── api_sports_tool.py   # API-Sports 数据采集
    │   ├── historical_data_tool.py # 历史 CSV 数据加载
    │   ├── scraper_tool.py      # 爬虫补充数据
    │   ├── feature_builder_tool.py # 球队特征构建
    │   ├── match_predictor_tool.py # 单场比赛预测
    │   ├── bracket_tool.py      # 淘汰赛推演
    │   └── explanation_tool.py  # LLM + 规则解释
    │
    ├── api/                     # API 路由层
    │   ├── agent.py             # Agent 一键预测接口
    │   ├── teams.py             # 球队管理接口
    │   ├── predictions.py       # 预测相关接口
    │   ├── simulation.py        # 模拟辅助模块
    │   └── routes.py            # 路由注册中心
    │
    ├── services/                # 核心算法服务层
    │   ├── probability_engine.py # 概率引擎 (Elo + 泊松分布)
    │   ├── tournament_sim.py    # 锦标赛赛制模拟
    │   ├── prediction_service.py # 预测算法服务
    │   ├── llm_explainer.py     # LLM 解释器
    │   └── feature_network.py   # PyTorch 特征网络
    │
    ├── models/                  # 数据模型层
    │   ├── agent_models.py      # Agent DB 模型 (4张表)
    │   ├── schemas.py           # SQLAlchemy ORM 模型
    │   └── pydantic_models.py   # Pydantic 验证模型
    │
    ├── core/                    # 核心配置层
    │   ├── config.py            # 应用配置 (pydantic-settings)
    │   └── scheduler.py         # APScheduler 定时任务
    │
    ├── db/
    │   └── database.py          # 数据库连接和会话管理
    │
    └── data/
        ├── api_fetcher.py       # Football API 客户端
        └── web_scraper.py       # Playwright 爬虫
```

## 🔧 核心技术栈

### 后端框架
- **FastAPI 0.109.0** - 高性能异步 Web 框架
- **Uvicorn 0.27.0** - ASGI 服务器
- **Pydantic 2.5.3** - 数据验证和设置管理

### 数据库
- **SQLAlchemy 2.0.25** - ORM 框架
- **Alembic 1.13.1** - 数据库迁移工具
- **SQLite** - 轻量级数据库（可替换为 PostgreSQL/MySQL）

### 数据处理与科学计算
- **Pandas 2.2.0** - 数据分析
- **NumPy 1.26.3** - 数值计算
- **SciPy 1.12.0** - 科学计算（泊松分布等）

## 🔌 API 接口

### Agent 接口 (核心)

```
POST   /api/v1/agent/run-prediction   # 一键运行完整冠军预测 Agent
POST   /api/v1/agent/refresh-data     # 仅刷新 API-Sports 数据
GET    /api/v1/agent/status           # 最近一次 Agent 运行状态
```

### 辅助接口

```
GET    /api/v1/teams/                 # 获取球队列表
GET    /api/v1/teams/{id}             # 获取单个球队
POST   /api/v1/predictions/tournament # 预测整个锦标赛
POST   /api/v1/predictions/match/{id} # 预测单场比赛
```

## 🎯 核心功能模块

### 1. WorldCupPredictionAgent (`app/agents/worldcup_agent.py`)

**执行流程（12 步）：**
1. 设定预测目标
2. 生成数据收集计划
3. 调用 APISportsTool 获取赛程、球队、积分榜、实时比分
4. 调用 HistoricalDataTool 加载历史比赛
5. 可选调用 ScraperTool 获取补充信息
6. 调用 DataQualityAgent 检查数据质量
7. 调用 FeatureBuilderTool 构建球队特征
8. 调用 BracketTool + MatchPredictorTool 预测小组赛
9. 推演淘汰赛（32强→16强→8强→半决赛→决赛）
10. 确定冠军和亚军
11. 调用 ExplanationTool 生成解释
12. 生成可视化数据

### 2. DataQualityAgent (`app/agents/data_quality_agent.py`)

检查 8 项数据质量指标：
- 赛程、球队、近期战绩、历史比赛、Elo/FIFA排名、实时比分、身价数据、关键字段
- 输出 is_usable / score / warnings / blocking_errors

### 3. Tools 工具层

| 工具 | 文件 | 功能 |
|------|------|------|
| APISportsTool | api_sports_tool.py | API-Sports 数据采集，带缓存 |
| HistoricalDataTool | historical_data_tool.py | 本地 CSV 历史比赛加载 |
| ScraperTool | scraper_tool.py | 爬虫补充数据（失败不阻塞） |
| FeatureBuilderTool | feature_builder_tool.py | 球队特征构建，缺失字段自动降权 |
| MatchPredictorTool | match_predictor_tool.py | 单场预测（泊松分布 + Elo） |
| BracketTool | bracket_tool.py | 小组赛→淘汰赛→冠军完整推演 |
| ExplanationTool | explanation_tool.py | LLM 解释 + 规则兜底 |

## 🗄️ 数据库设计

### Agent 专用表

```
agent_runs (Agent 运行记录)
  ├── id (PK)
  ├── objective, season
  ├── predicted_champion, predicted_runner_up
  ├── data_quality_score
  ├── final_explanation
  ├── status (pending/running/completed/failed)
  ├── errors_json
  └── created_at

agent_reasoning_steps (推理步骤)
  ├── id (PK)
  ├── agent_run_id (FK → agent_runs)
  ├── step_order, step_text
  └── created_at

predicted_matches (预测比赛)
  ├── id (PK)
  ├── agent_run_id (FK → agent_runs)
  ├── stage (group/round_of_32/.../final)
  ├── home_team, away_team
  ├── predicted_home_score, predicted_away_score
  ├── predicted_winner, confidence
  ├── source (real_result / agent_prediction)
  └── reasoning_json

team_features (球队特征快照)
  ├── id (PK)
  ├── agent_run_id (FK → agent_runs)
  ├── team_name, elo_rating, fifa_rank
  ├── recent_win_rate, recent_goals_for_avg, recent_goals_against_avg
  ├── attack_score, defense_score, power_score
  └── data_confidence
```

### 原有业务表

```
Team (球队)
  ├── id (PK)
  ├── name, country_code
  ├── fifa_ranking, elo_rating
  
Match (比赛)
  ├── id (PK), stage, group
  ├── home_team_id (FK), away_team_id (FK)
  ├── home_score, away_score, is_completed

Prediction (预测)
  ├── id (PK), match_id (FK)
  ├── predicted_home_score, predicted_away_score
  ├── confidence, reasoning
```

## 🔐 配置管理

通过 `app/core/config.py` 集中管理配置：

```python
class Settings(BaseSettings):
    APP_NAME: str = "World Cup Prediction API"
    DATABASE_URL: str = "sqlite:///./worldcup.db"
    DATA_DIR: str = "app/data"
    PREDICTION_MODEL_PATH: str = "app/data/models"
```

支持环境变量覆盖（`.env` 文件）。

## 🚀 应用生命周期管理

使用 FastAPI 的 `lifespan` 特性：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动阶段
    init_db()              # 初始化数据库
    load_models()          # 加载预测模型
    load_historical_data() # 加载历史数据
    
    yield  # 应用运行
    
    # 关闭阶段
    engine.dispose()       # 关闭数据库连接
```

## 📊 类型注解规范

严格使用 Python 3.10+ 类型注解：

```python
# ✅ 正确示例
from typing import Optional, List

def get_teams() -> List[TeamResponse]:
    ...

def predict(
    home_team: Team,
    away_team: Team,
    model_type: str = "elo"
) -> dict[str, int | float | str]:
    ...

# 可选类型
confidence: Optional[float] = None
```

## 🧪 测试策略

### API 测试 (`test_api.py`)

```bash
# 运行测试
python test_api.py
```

**测试覆盖：**
- 健康检查端点
- 球队 CRUD 操作
- 比赛预测功能

### 手动测试

访问 Swagger UI：http://localhost:8001/docs

## 📈 性能优化建议

1. **数据库连接池** - SQLAlchemy 已内置连接池
2. **异步支持** - FastAPI 原生支持异步
3. **缓存策略** - 可使用 `lru_cache` 缓存配置和预测结果
4. **批量操作** - 使用 SQLAlchemy 的 `bulk_insert_mappings`

## 🔮 后续扩展方向

### 短期目标
1. **完善预测算法**
   - 实现完整的锦标赛预测逻辑
   - 集成更多预测模型（机器学习）
   - 添加模型 ensemble 机制

2. **数据采集**
   - 接入 FIFA API
   - 网页抓取历史数据
   - 实时更新球队排名

### 中期目标
3. **可视化前端**
   - 赛程树/对阵图展示
   - 预测结果可视化
   - 交互式推理过程展示

4. **高级分析**
   - 历史数据挖掘
   - 球队表现趋势分析
   - 球员影响力评估

### 长期目标
5. **实时预测**
   - 根据比赛进程动态调整
   - 多模型投票机制
   - 用户反馈学习

6. **部署优化**
   - Docker 容器化
   - CI/CD 流水线
   - 生产环境监控

## 🛡️ 安全考虑

1. **CORS 配置** - 生产环境应限制具体域名
2. **输入验证** - Pydantic 自动验证所有输入
3. **SQL 注入防护** - SQLAlchemy ORM 参数化查询
4. **错误处理** - 统一异常处理，不暴露敏感信息

## 📝 开发规范

1. **代码风格** - 遵循 PEP 8
2. **类型注解** - 所有函数必须有类型注解
3. **文档字符串** - 所有公共函数/类必须有 docstring
4. **错误处理** - 使用 HTTPException 返回标准错误
5. **日志记录** - 关键操作记录日志

## 🎓 学习资源

- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 文档](https://docs.sqlalchemy.org/)
- [Pydantic V2 文档](https://docs.pydantic.dev/)
- [ELO 评分系统](https://en.wikipedia.org/wiki/Elo_rating_system)

## 🖥️ Streamlit Dashboard

`debug_dashboard.py` 提供完整的 Agent 预测展示面板，按顺序展示：

1. Agent 任务目标
2. 数据收集计划
3. 数据源状态
4. 数据质量报告
5. 球队实力排行榜
6. 小组赛预测结果
7. 淘汰赛对阵树
8. 决赛预测
9. 预测冠军
10. Agent 推理过程
11. LLM 解释报告

启动方式：
```bash
streamlit run debug_dashboard.py
```

## 🚀 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 .env 文件（API key、LLM key）

# 3. 启动 FastAPI 后端
python main.py

# 4. 启动 Streamlit 前端（新终端）
streamlit run debug_dashboard.py
```

---

**版本**: 2.0.0  
**最后更新**: 2026-07-09  
**本项目是 WorldCupPredictionAgent** - 基于 Agent 编排的世界杯冠军预测系统
