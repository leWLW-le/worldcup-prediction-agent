# 2026 世界杯冠军预测 Agent

基于 **Agent + Tools** 架构的 2026 美加墨世界杯冠军预测智能体系统。通过五模型集成预测引擎、Bracket-Aware 蒙特卡洛模拟（10,000 次）、LLM 可解释性分析和交互式 What-If 沙盒，实现从数据采集到冠军预测的全流程自动化。

## 线上演示

- **前端面板**：https://worldcup-frontend-rpnj.onrender.com
- **后端 API**：https://worldcup-backend-k2sn.onrender.com
- **API 文档**：https://worldcup-backend-k2sn.onrender.com/docs

## 核心特性

**五模型集成预测** — 注意力神经网络 (30%) + ELO (25%) + XGBoost (20%) + Poisson (15%) + 路径概率 (10%)，加权集成降低单一模型偏见。

**Bracket-Aware 蒙特卡洛** — 10,000 次完整赛程模拟，自动感知真实对阵结构（已完赛的半决赛/决赛直接带入，仅对未完成的比赛概率采样）。

**Agent 智能体架构** — 支持 workflow（12 步固定流水线）和 LLM Planner（自主决策 + 反思 + workflow 兜底）双模式，13+ 标准化工具，跨运行持久学习记忆。

**LLM 可解释性** — ZhipuAI GLM-4-Flash 驱动的自然语言预测解释，内置 27 项技术术语自动净化，确保非技术用户也能理解。

**What-If 沙盒** — 交互式"如果...会怎样"分析：强制指定任何待赛比赛的胜者，重新运行 1,000 次模拟，展示冠军概率变化。

**多源数据整合** — API-Sports + football-data.org + 本地缓存 + 模板兜底，三级可信度自动降级，PostgreSQL 持久化存储。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 前端面板 | Streamlit（深蓝金色主题） |
| 数据库 | PostgreSQL (Render) / SQLite (本地) |
| 机器学习 | PyTorch (注意力网络) + XGBoost + scikit-learn |
| LLM | ZhipuAI GLM-4-Flash (LangChain 集成) |
| 数据处理 | Pandas + NumPy + SciPy |
| 部署 | Render (Docker) + GitHub Actions 保活 |

## 快速开始

### 本地运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量（复制模板并填写 API 密钥）
cp .env.example .env

# 3. 启动后端
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 4. 启动前端面板（另开终端）
streamlit run debug_dashboard.py
```

### Docker 部署

```bash
docker-compose up -d
# 后端: http://localhost:8001
# 前端: http://localhost:8501
```

## 项目结构

```
worldcup-prediction-agent/
├── main.py                          # FastAPI 应用入口
├── debug_dashboard.py               # Streamlit 可视化面板
├── render.yaml                      # Render 部署配置
├── docker-compose.yml               # Docker 编排
│
├── app/
│   ├── agents/                      # Agent 编排层
│   │   ├── worldcup_agent.py        # 核心预测 Agent（12 步流水线）
│   │   ├── agent_executor.py        # 工具执行引擎
│   │   ├── agent_memory.py          # 持久学习记忆
│   │   ├── llm_planner_agent.py     # LLM 规划 Agent
│   │   ├── tool_adapters.py         # 13+ 工具适配器
│   │   └── tool_registry.py         # 工具注册中心
│   │
│   ├── api/                         # API 路由
│   │   ├── agent.py                 # 预测 Agent 端点
│   │   ├── data.py                  # 数据刷新端点
│   │   ├── simulation.py            # 模拟端点
│   │   ├── scenario.py              # What-If 沙盒端点
│   │   ├── predictions.py           # 预测端点
│   │   └── teams.py                 # 球队端点
│   │
│   ├── services/                    # 业务逻辑（25+ 微服务）
│   │   ├── ensemble_prediction_service.py  # 五模型集成
│   │   ├── prediction_service.py           # ELO + Poisson 基线
│   │   ├── feature_network.py              # PyTorch 注意力网络
│   │   ├── tournament_state_service.py     # 锦标赛状态
│   │   ├── champion_explanation_service.py # AI 解释 + 术语净化
│   │   ├── llm_explainer.py               # LLM 比赛解释
│   │   ├── scenario_simulation_service.py  # What-If 沙盒引擎
│   │   └── scheduled_refresh_service.py    # 定时数据刷新
│   │
│   └── tools/                       # Agent 工具实现
│       ├── bracket_tool.py          # 淘汰赛 bracket（45KB）
│       ├── api_sports_tool.py       # API-Sports 集成
│       └── ...
│
├── scripts/                         # 工具脚本（50+）
│   └── run_champion_simulation.py   # Bracket-Aware Monte Carlo
│
├── data/                            # 数据文件
│   ├── simulation_distribution.json # 模拟结果
│   ├── final_agent_result.json      # 最终预测
│   └── agent_memory.json            # Agent 记忆
│
├── models/                          # 训练模型
│   ├── feature_network_v2_latest.pth  # 注意力网络权重
│   └── tree_predictor.pkl             # XGBoost 模型
│
└── tests/                           # 测试
    ├── test_bracket_integrity.py
    ├── test_final_result.py
    └── test_save_integration.py
```

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/agent/run-prediction` | POST | 一键运行完整冠军预测 |
| `/api/v1/agent/latest-result` | GET | 获取最新预测结果 |
| `/api/v1/data/full-refresh` | POST | 全量刷新（同步数据 + 模拟 + 更新结果） |
| `/api/v1/agent/refresh-data` | POST | 仅同步 API 数据 |
| `/api/v1/simulation/champion` | POST | 运行 Monte Carlo 模拟 |
| `/api/v1/scenario/run` | POST | What-If 沙盒模拟 |
| `/health` | GET | 健康检查 |

## 当前预测

截至 2026-07-16（半决赛阶段）：

| 排名 | 球队 | 夺冠概率 |
|------|------|----------|
| 1 | 西班牙 | 50.14% |
| 2 | 英格兰 | 34.02% |
| 3 | 阿根廷 | 15.84% |

## 详细文档

- [参赛提交文档](worldcup_prediction_agent.md) — 完整的系统架构、算法设计、创新点说明
- [项目总结](PROJECT_SUMMARY.md) — 成熟度评估与代码架构分析
- [架构设计](ARCHITECTURE.md) — Agent + Tools 架构设计文档
- [API 指南](API_GUIDE.md) — 完整 API 端点文档
- [概率引擎](PROBABILITY_ENGINE_GUIDE.md) — ELO + Poisson 引擎详解
- [特征网络](FEATURE_NETWORK_GUIDE.md) — PyTorch 注意力网络详解
- [LLM 解释](LLM_EXPLAINER_GUIDE.md) — LLM 可解释性模块说明
- [Streamlit 面板](STREAMLIT_DASHBOARD_GUIDE.md) — 前端面板使用指南

## 许可证

MIT License
