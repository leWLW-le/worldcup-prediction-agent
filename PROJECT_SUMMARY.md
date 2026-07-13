# 2026 世界杯冠军预测系统 — 项目总结

> 生成日期：2026-07-12

---

## 一、项目概述

**WorldCupPredictionAgent** 是一个基于 Agent + Tools 架构的 2026 美加墨世界杯冠军预测系统。系统通过多源数据采集、ELO 评分 + 泊松分布概率引擎、PyTorch 注意力特征网络、以及 LLM 智能规划，完成从数据收集到冠军预测的全流程自动化，并通过 Streamlit 可视化面板呈现结果。

**技术栈**：Python 3.12 / FastAPI / Streamlit / SQLAlchemy / PyTorch / LangChain / ChromaDB / APScheduler

**当前预测结果**：法国队夺冠（决赛 1-0 胜英格兰）

---

## 二、项目定性

### 2.1 项目定位

这是一个**工程完整性较高的学术/演示级预测系统**，具备以下特征：

- **架构设计成熟**：Agent + Tools 分层清晰，12 步流水线覆盖完整预测链路
- **算法组合合理**：ELO + 泊松分布作为基线，PyTorch 注意力网络做特征增强，LLM 做可解释性输出
- **工程规范良好**：Pydantic 数据校验、SQLAlchemy ORM、统一工具注册中心、CORS 配置
- **文档体系完善**：13 份专项文档覆盖架构、API、数据库、各模块实现细节

### 2.2 成熟度评估

| 维度 | 评级 | 说明 |
|------|------|------|
| 架构设计 | ★★★★☆ | Agent+Tools 分层清晰，但 LLM Planner 与 Workflow 双模式增加了复杂度 |
| 算法实现 | ★★★☆☆ | ELO+泊松是经典方案，PyTorch 特征网络有潜力但权重文件仅 21KB（可能未充分训练） |
| 数据工程 | ★★★☆☆ | 支持 API-Sports + football-data.org + Playwright 爬虫，但 API 配额已耗尽，当前依赖模板数据 |
| 可视化 | ★★★★☆ | Streamlit 深蓝金色主题精美，冠军之路路径图有创意，但缺少交互式探索 |
| 测试覆盖 | ★★☆☆☆ | 21 个诊断脚本替代了正规单元测试，缺少 CI/CD 和回归测试 |
| 预测准确率 | ★★★☆☆ | 方向准确率 70.2%，但存在严重的主胜偏向（详见回测报告） |

### 2.3 核心优势

1. **多模式预测**：支持固定流水线（workflow）和 LLM 智能规划（llm_planner）两种模式
2. **可解释性**：LLM Explainer Agent 生成自然语言预测依据，而非黑箱输出
3. **完整赛制模拟**：48 队 12 小组 → 32 强 → 16 强 → 8 强 → 半决赛 → 决赛，含加时/点球规则
4. **战术知识库**：ChromaDB 向量数据库存储战术知识，辅助 LLM 生成专业解释

### 2.4 主要不足

1. **数据源受限**：外部 API 配额耗尽，当前使用模板/缓存数据，预测结果可靠性受限
2. **模型偏向**：回测显示模型严重偏向预测主胜（97.9%），平局和客胜预测能力弱
3. **特征网络未充分训练**：PyTorch 模型权重文件仅 21KB，可能未经大规模数据训练
4. **缺少在线学习**：无法根据新比赛结果动态更新 ELO 评分和模型参数

---

## 三、代码架构

### 3.1 目录结构

```
J:\project\worldcup\
├── main.py                          # FastAPI 应用入口（lifespan 管理）
├── debug_dashboard.py               # Streamlit 可视化面板（~850 行）
├── backtest.py                      # 回测模块（新增）
├── init_data.py / init_worldcup_data.py  # 数据初始化脚本
├── verify_system.py                 # 系统验证脚本
├── requirements.txt                 # 23 个 Python 依赖
├── .env                             # 环境变量配置
├── worldcup.db                      # SQLite 主数据库（880KB）
├── prediction_result.json           # 缓存的预测结果（142KB）
├── backtest_result.json             # 回测结果（新增）
│
├── app/                             # 核心应用代码
│   ├── agents/                      # Agent 编排层
│   │   ├── worldcup_agent.py        # 核心预测 Agent（44KB，12 步流水线）
│   │   ├── agent_executor.py        # Agent 执行引擎
│   │   ├── agent_memory.py          # Agent 记忆管理
│   │   ├── agent_state.py           # Agent 全局状态
│   │   ├── llm_planner_agent.py     # LLM 规划 Agent
│   │   ├── data_quality_agent.py    # 数据质量检查 Agent（8 项检查）
│   │   ├── tool_registry.py         # 工具注册中心
│   │   ├── tool_adapters.py         # 工具适配层（26KB）
│   │   ── tool_schemas.py          # 工具输入输出 Schema
│   │
│   ├── services/                    # 核心算法服务
│   │   ├── probability_engine.py    # ELO + 泊松概率引擎
│   │   ├── tournament_sim.py        # 完整锦标赛模拟（32KB）
│   │   ├── feature_network.py       # PyTorch 注意力特征网络
│   │   ├── prediction_service.py    # 预测服务封装
│   │   ├── llm_explainer.py         # LLM 解释 Agent（33KB）
│   │   ├── team_rating_service.py   # 球队评分服务
│   │   ├── feature_builder_service.py # 特征构建服务
│   │   ├── path_difficulty_service.py # 夺冠路径难度计算
│   │   ├── recent_form_service.py   # 近期状态分析
│   │   ├── team_stats_service.py    # 球队统计服务
│   │   ├── bootstrap_service.py     # 数据引导服务
│   │   ├── data_source_manager.py   # 数据源管理
│   │   ├── fixture_repository.py    # 比赛数据仓库
│   │   ├── real_tournament_data.py  # 真实赛事数据集成
│   │   ── worldcup_sync_service.py # 世界杯数据同步
│   │
│   ├── tools/                       # Agent 工具层
│   │   ├── bracket_tool.py          # 完整淘汰赛模拟（43KB）
│   │   ├── match_predictor_tool.py  # 单场比赛预测
│   │   ├── explanation_tool.py      # LLM + 规则解释生成
│   │   ├── feature_builder_tool.py  # 球队特征构建
│   │   ├── api_sports_tool.py       # API-Sports 数据采集
│   │   ├── football_data_tool.py    # football-data.org 集成
│   │   ├── scraper_tool.py          # Playwright 网页爬虫
│   │   ├── historical_data_tool.py  # 历史 CSV 数据加载
│   │   └── llm_csv_assistant_tool.py # LLM CSV 助手
│   │
│   ├── api/                         # API 路由层
│   │   ├── routes.py                # 路由注册
│   │   ├── agent.py                 # Agent 端点（run-prediction, status）
│   │   ├── simulation.py            # 模拟端点（21KB）
│   │   ├── predictions.py           # 预测端点
│   │   ├── teams.py                 # 球队管理端点
│   │   └── data.py                  # 数据端点
│   │
│   ├── models/                      # 数据模型
│   │   ├── schemas.py               # SQLAlchemy ORM 模型
│   │   ├── pydantic_models.py       # Pydantic 校验模型
│   │   ├── agent_models.py          # Agent 数据库表（4 张表）
│   │   └── fixtures.py              # 比赛 ORM 模型
│   │
│   ├── data/                        # 数据采集层
│   │   ├── api_fetcher.py           # Football API 客户端（22KB）
│   │   ├── web_scraper.py           # Playwright 爬虫（24KB）
│   │   └── football_cache.db        # API 数据缓存（180KB）
│   │
│   ├── db/
│   │   └── database.py              # SQLAlchemy 引擎、会话、Base
│   │
│   └── core/
│       ├── config.py                # Pydantic-settings 配置（.env 加载）
│       └── scheduler.py             # APScheduler 定时任务
│
├── data/                            # 静态数据文件
│   ├── historical_international_matches.csv  # 67 场历史比赛
│   ├── team_ratings.csv             # 48 支球队 ELO 评分
│   ├── team_aliases.csv             # 球队别名映射
│   ├── competition_weights.csv      # 赛事权重
│   ├── data_manifest.json           # 数据源状态清单
│   ├── agent_memory.json            # Agent 记忆状态
│   └── cache/
│       └── worldcup_2026_teams_api.csv  # API 缓存数据
│
├── models/
│   └── feature_mixer_latest.pth     # PyTorch 模型权重（21KB）
│
├── scripts/                         # 22 个工具脚本
│   ├── run_full_acceptance.py       # 完整验收测试
│   ├── sync_live_worldcup.py        # 同步实时世界杯数据
│   ├── sync_external_fixtures.py    # 同步外部比赛数据
│   ├── migrate_fixtures_schema.py   # 数据库迁移
│   ├── check_visualization_data_consistency.py  # 可视化数据一致性检查
│   └── ...（其余 17 个调试/检查脚本）
│
└── docs/                            # 13 份文档
    ├── README.md                    # 项目概览
    ├── ARCHITECTURE.md              # 架构设计
    ├── API_GUIDE.md                 # API 使用指南
    ├── DATABASE_GUIDE.md            # 数据库设计
    ├── FEATURE_NETWORK_GUIDE.md     # 特征网络文档
    ├── KNOCKOUT_SIM_GUIDE.md        # 淘汰赛模拟文档
    ├── LLM_API_SETUP.md             # LLM API 配置
    ├── LLM_EXPLAINER_GUIDE.md       # LLM 解释器文档
    ├── PROBABILITY_ENGINE_GUIDE.md  # 概率引擎文档
    ├── STREAMLIT_DASHBOARD_GUIDE.md # 面板使用指南
    ├── TOURNAMENT_SIM_GUIDE.md      # 锦标赛模拟文档
    ├── TASK4_SUMMARY.md             # 任务 4 总结
    └── TASK5_SUMMARY.md             # 任务 5 总结
```

### 3.2 模块依赖关系

```
                    ┌─────────────────┐
                    │   Streamlit UI  │  debug_dashboard.py
                    │   (可视化面板)   │
                    └────────┬────────┘
                             │ HTTP API
                    ┌────────▼────────┐
                    │    FastAPI      │  main.py
                    │   (后端服务)     │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼──────┐ ┌────▼─────┐ ┌──────▼──────
     │  Agent 编排层  │ │ API 路由  │ │  定时任务    │
     │  worldcup_    │ │ /api/v1/ │ │ APScheduler │
     │  agent.py     │ │          │ │             │
     └────────┬──────┘ └──────────┘ └─────────────┘
              │
     ┌────────▼──────────────────────────┐
     │         Tool Registry             │
     │  (统一工具注册中心)                │
     └──┬────┬────┬────┬────┬────┬───────┘
        │    │    │    │    │    │
   ┌────▼┐ ┌▼───┐ ▼──┐ ┌▼──┐ ┌▼──┐ ▼──────┐
   │API  │ │历史│ │爬虫│ │特征│ │比分│ │淘汰赛  │
   │数据  │ │数据│ │   │ │构建│ │预测│ │模拟    │
   └─────┘ ────┘ └───┘ ───┘ └───┘ └───────┘
        │         │              │
   ┌────▼─────────▼──────────────▼────
   │         Services 算法层            │
   │  ┌──────────┐  ┌──────────────┐  │
   │  │Probability│  │  Feature     │  │
   │  │ Engine   │  │  Network     │  │
   │  │(ELO+泊松)│  │  (PyTorch)   │  │
   │  └──────────┘  └──────────────┘  │
   │  ┌──────────┐  ┌──────────────┐  │
   │  │Tournament│  │  LLM         │  │
   │  │ Sim      │  │  Explainer   │  │
   │  └──────────┘  └──────────────┘  │
   └──────────────────────────────────┘
              │
     ┌────────▼────────┐
     │   SQLite 数据库  │  worldcup.db
     │  (7+ 张表)       │
     └─────────────────┘
```

### 3.3 核心预测流水线（12 步）

`WorldCupPredictionAgent.run()` 执行以下 12 步：

| 步骤 | 工具/服务 | 功能 |
|------|----------|------|
| 1 | LLM Planner / Workflow | 决定执行路径（智能规划 or 固定流程） |
| 2 | APISportsTool | 从 API-Sports 获取实时比赛数据 |
| 3 | HistoricalDataTool | 加载历史比赛 CSV 数据 |
| 4 | ScraperTool | Playwright 爬取补充数据 |
| 5 | DataQualityAgent | 8 项数据质量检查 |
| 6 | FeatureBuilderTool | 构建球队多维特征（ELO、身价、状态、伤病） |
| 7 | FeatureAttentionMixer | PyTorch 注意力网络加权特征 |
| 8 | TournamentSim | 48 队小组赛模拟（12 组 × 6 场） |
| 9 | BracketTool | 淘汰赛完整模拟（32 强 → 决赛） |
| 10 | MatchPredictorTool | 逐场 ELO + 泊松比分预测 |
| 11 | ChampionExplanation | 冠军解释生成 |
| 12 | LLM Explainer | 自然语言预测依据输出 |

### 3.4 数据库设计

**7 张核心表**：

| 表名 | 用途 | 关键列 |
|------|------|--------|
| `fixtures` | 比赛记录 | id, home_team, away_team, home_score, away_score, status, source |
| `teams` | 球队信息 | id, name, elo_rating, fifa_rank, group |
| `agent_runs` | Agent 运行记录 | id, season, mode, status, started_at, completed_at |
| `agent_predictions` | 预测结果 | id, run_id, match_id, predicted_winner, confidence |
| `agent_memory` | Agent 记忆 | id, key, value, created_at |
| `data_sources` | 数据源状态 | id, name, status, last_sync, fixtures_count |
| `knockout_bracket` | 淘汰赛对阵 | id, round, home_team, away_team, winner, source |

### 3.5 API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/v1/agent/run-prediction` | 运行完整预测 |
| GET | `/api/v1/agent/status` | 获取 Agent 状态 |
| POST | `/api/v1/data/refresh-fixtures` | 刷新比赛数据 |
| GET | `/api/v1/data/status` | 数据源状态 |
| GET | `/api/v1/teams` | 球队列表 |
| GET | `/api/v1/predictions` | 预测结果 |
| POST | `/api/v1/simulation/run` | 运行模拟 |

---

## 四、回测结果

基于 67 场历史比赛（2022-2025 年国际赛事）的回测评估：

### 4.1 核心指标

| 指标 | 数值 | 基线对比 |
|------|------|----------|
| 胜平负方向准确率 | **70.2%** (47/67) | — |
| 仅胜负准确率（排除平局） | **83.9%** | — |
| 精确比分准确率 | **11.9%** | 随机基线 ~2-3% |
| Top-3 比分覆盖率 | **34.3%** | — |
| Brier 分数 | **0.4834** | 频率基线 0.46 |
| 对数损失 | **1.5721** | 随机基线 1.10 |

### 4.2 按结果类型

| 结果 | 准确率 | 样本数 |
|------|--------|--------|
| 主胜 | 97.9% | 47 场 |
| 平局 | 0.0% | 11 场 |
| 客胜 | 11.1% | 9 场 |

### 4.3 按赛事

| 赛事 | 方向准确率 | 比分准确率 | Brier |
|------|-----------|-----------|-------|
| FIFA World Cup | 62.5% | 0.0% | 0.446 |
| FIFA World Cup Qualifier | 80.0% | 20.0% | 0.358 |
| UEFA Euro | 75.0% | 16.7% | 0.529 |
| UEFA Nations League | 77.8% | 11.1% | 0.588 |
| Friendly | 61.5% | 7.7% | 0.440 |

### 4.4 关键发现

1. **主胜偏向严重**：模型几乎总是预测主胜，导致主胜"准确率"虚高（97.9%），但平局和客胜预测能力极弱
2. **高置信度区间失准**：90-100% 置信度区间实际准确率仅 55.6%，模型对"稳赢"判断过于乐观
3. **比分预测有亮点**：11.9% 的精确比分准确率远超随机水平，说明泊松分布的比分建模基本有效
4. **预选赛表现最好**：FIFA 世界杯预选赛方向准确率 80%，Brier 分数最低（0.358），因为强弱分明

---

## 五、可视化界面改进建议

当前 Streamlit 面板已包含：冠军预测卡片、LLM 解释、冠军之路淘汰赛路径图、夺冠热门排行、重点比赛。以下是可以增加的内容：

### 5.1 数据探索类

| 功能 | 说明 | 优先级 |
|------|------|--------|
| **球队实力雷达图** | 用雷达图展示每支球队的 ELO、进攻、防守、近期状态、身价等多维特征，支持两两对比 | 高 |
| **小组赛积分榜** | 以表格形式展示 12 个小组的模拟积分排名（队名、胜平负、进球、净胜球、积分） | 高 |
| **夺冠概率分布图** | 用条形图或饼图展示所有 48 支球队的夺冠概率分布，而非仅 Top 8 | 高 |
| **历史交锋记录** | 点击任意两支球队，展示历史交锋战绩（胜负平、进球数） | 中 |

### 5.2 预测分析类

| 功能 | 说明 | 优先级 |
|------|------|--------|
| **比赛概率详情** | 点击淘汰赛任意场次，弹出胜/平/负概率分布和 Top-3 比分预测 | 高 |
| **夺冠路径难度** | 展示冠军从小组赛到决赛每一轮的对手和胜率，可视化"夺冠难度曲线" | 高 |
| **蒙特卡洛模拟结果** | 展示多次模拟的冠军分布（如运行 1000 次，法国夺冠 350 次 = 35%） | 中 |
| **敏感性分析** | 调整某队 ELO 评分 ±100，观察夺冠概率变化，展示关键因素 | 中 |

### 5.3 模型评估类

| 功能 | 说明 | 优先级 |
|------|------|--------|
| **回测结果面板** | 将 backtest.py 的结果可视化：准确率趋势、Brier 分数、校准曲线 | 高 |
| **预测 vs 实际对比** | 如果有实时数据，展示预测比分与实际比分的散点对比图 | 中 |
| **模型参数调节器** | 提供滑块调整 ELO K 因子、泊松 λ 权重等参数，实时查看预测变化 | 中 |

### 5.4 交互体验类

| 功能 | 说明 | 优先级 |
|------|------|--------|
| **球队搜索/筛选** | 支持按大洲、FIFA 排名、ELO 区间筛选球队 | 中 |
| **预测模式切换** | 在面板中直接切换 workflow / llm_planner 模式并对比结果 | 低 |
| **数据刷新状态** | 实时显示数据源连接状态、API 配额余量、上次同步时间 | 中 |
| **导出报告** | 一键导出预测结果为 PDF 或 Excel | 低 |

### 5.5 推荐优先实现

如果只选 3 个最值得做的：

1. **球队实力雷达图 + 两两对比** — 直观展示模型使用的特征，增强可解释性
2. **回测结果可视化** — 让使用者了解模型的可靠性和局限性
3. **比赛概率详情弹窗** — 点击淘汰赛场次查看胜平负概率和比分预测，提升交互深度

---

## 六、后续工作建议

### 6.1 短期（1-2 周）

- [ ] 修复模型主胜偏向问题（调整 ELO 主场优势系数或引入平局先验）
- [ ] 补充正规单元测试（pytest），覆盖概率引擎和锦标赛模拟
- [ ] 将回测模块集成到 CI 流程，每次代码变更自动评估准确率

### 6.2 中期（1 个月）

- [ ] 获取真实 API 数据源（API-Sports 付费套餐或 football-data.org 升级）
- [ ] 用历史数据训练 PyTorch 特征注意力网络（当前 21KB 权重可能未充分训练）
- [ ] 实现在线 ELO 更新机制，比赛结束后自动更新评分

### 6.3 长期

- [ ] 引入更多特征（球员伤病、天气、裁判、旅行距离）
- [ ] 支持用户自定义参数并实时重算
- [ ] 多届世界杯回测（2018、2022）验证模型泛化能力
