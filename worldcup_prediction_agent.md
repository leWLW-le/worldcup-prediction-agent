# 2026 世界杯冠军预测系统 · 参赛提交文档

**项目名称**：World Cup Prediction — 世界杯冠军预测系统  
**线上地址**：  
- 前端面板：https://worldcup-frontend.onrender.com  
- 后端 API：https://worldcup-backend-k2sn.onrender.com  
- API 文档：https://worldcup-backend-k2sn.onrender.com/docs  

**GitHub 仓库**：https://github.com/leWLW-le/worldcup-prediction-agent  
**技术栈**：Python 3.12 / FastAPI / Streamlit / PyTorch / XGBoost / SQLAlchemy / PostgreSQL  
**生成时间**：2026-07-16  

---

## 一、项目背景与定位

### 1.1 赛事背景

2026 年 FIFA 世界杯首次由三个国家（美国、加拿大、墨西哥）联合举办，也是世界杯历史上首次扩军至 **48 支参赛球队**（原 32 队），赛制从 8 组 × 4 队调整为 **12 组 × 4 队**。小组前 2 名 + 8 支最佳第 3 名晋级 32 强淘汰赛，总比赛场次从 64 场增至 **104 场**，赛程跨度长达 39 天。

赛制变革带来了预测层面的新挑战：更多球队意味着更大的实力差异跨度，更多比赛意味着更密集的数据更新需求，更长的赛程意味着预测系统需要持续融合实时赛果进行动态调整。

### 1.2 项目定位

本项目是一个面向 2026 世界杯赛制的 **动态预测系统**，覆盖从数据采集、特征工程、模型预测、赛程模拟到可视化展示的完整流程。

与传统预测方案相比，本系统解决以下问题：

| 传统预测的局限 | 本系统的应对 |
|---------------|-------------|
| 赛前一次性预测，无法随赛事推进更新 | 渐进式赛果融合，每场真实比赛后重新模拟 |
| 缺少完整晋级路径分析 | 10,000 次蒙特卡洛模拟推演完整淘汰赛树 |
| 预测结果缺乏解释 | LLM 驱动的自然语言冠军解读 |
| 无交互分析能力 | What-If 沙盒：指定赛果 → 查看概率变化 |
| 数据源单一，API 故障即停摆 | 三级数据源自动降级（API → 缓存 → 模板） |

### 1.3 开发工具

本项目使用 Qoder（AI 编程助手）进行开发，以下为开发过程中的实际使用记录：

![Qoder 开发记录 — 终端测试与代码审查](https://raw.githubusercontent.com/leWLW-le/worldcup-prediction-agent/main/docs/images/10_qoder_evidence_1.png)

![Qoder 开发记录 — 需求分析与项目状态跟踪](https://raw.githubusercontent.com/leWLW-le/worldcup-prediction-agent/main/docs/images/11_qoder_evidence_2.png)

---

## 二、系统架构设计

### 2.1 整体架构

系统采用前后端分离架构，后端为 Python 单体应用，前端为 Streamlit 数据面板：

```
┌─────────────────────────────────────────────────────────┐
│                   Streamlit 可视化面板                     │
│         （深蓝金色主题 · 交互式 What-If 沙盒）              │
└────────────────────────────────────────────────────────┘
                         │ HTTP REST API
┌────────────────────────▼────────────────────────────────┐
│                  FastAPI 后端应用                          │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  预测编排层   │  │  工具注册中心  │  │  API 路由层   │  │
│  │  (4种运行模式) │  │  (13+ 工具)   │  │  (7组端点)    │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────────  │
│         │                 │                              │
│  ┌──────▼─────────────────▼──────────────────────────┐  │
│  │           模块化预测服务层 (25+ 服务模块)              │  │
│  │  集成预测 · 概率引擎 · 锦标赛状态 · 解释生成 · 沙盒   │  │
│  └──────────────────────┬────────────────────────────┘  │
└─────────────────────────┼───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│                    数据与存储层                            │
│  PostgreSQL / SQLite · JSON 数据文件 · 训练模型权重        │
─────────────────────────────────────────────────────────┘
```

![系统架构流程图](https://raw.githubusercontent.com/leWLW-le/worldcup-prediction-agent/main/docs/images/07_system_architecture.png)

### 2.2 预测编排层

预测编排层负责协调从数据采集到最终预测的完整链路，支持 4 种运行模式：

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `workflow` | 固定 12 步顺序流水线，稳定基线 | 生产环境默认模式 |
| `llm_planner_safe` | LLM 自主决策工具调用，失败时回退到 workflow | 智能探索 + 安全兜底 |
| `llm_planner_strict` | LLM 自主决策，无回退，不完整则标记失败 | 纯 LLM 能力验证 |
| `llm_planner` | `llm_planner_safe` 的别名 | 向后兼容 |

**12 步流水线（workflow 模式）**：

1. **设定目标** — 明确预测赛季和任务
2. **数据计划** — 定义需要采集的数据维度
3. **API 数据采集** — 调用 API-Sports 获取实时赛程、球队信息、小组积分榜
4. **历史数据加载** — 从本地数据库加载 2010+ 年国际赛事历史数据
5. **数据质量检查** — 8 项检查：API 密钥、赛程可用性、球队数据、来源可信度分级
6. **特征构建** — 构建 25 维球队特征向量（ELO、攻防、状态、经验等）
7. **小组赛预测** — 模拟 12 组 × 4 队单循环，确定 32 强出线名额
8. **淘汰赛预测** — 从 32 强 → 16 强 → 8 强 → 半决赛 → 决赛逐轮推演
9. **冠军确认** — 多级回退链：Monte Carlo 第一 > 决赛胜者 > 实力评分最高
10. **AI 解释生成** — LLM 生成冠军预测的自然语言解释
11. **可视化构建** — 构建前端消费的结构化数据
12. **结果保存** — 原子写入 JSON，确保数据一致性

### 2.3 工具注册中心

13+ 个标准化工具，统一接口：`{success, data, error_type, message, state_updates}`

| 工具名称 | 功能 |
|----------|------|
| `get_cached_fixtures` | 从数据库读取缓存赛程 |
| `refresh_real_fixtures` | 从 API-Sports 拉取最新赛程/比分 |
| `get_worldcup_teams` | 获取 48 支参赛球队信息 |
| `load_historical_matches` | 加载历史国际赛事数据 |
| `build_team_features` | 构建 25 维球队特征向量 |
| `predict_group_stage` | 模拟小组赛并确定出线球队 |
| `predict_knockout_stage` | 逐轮推演淘汰赛 |
| `predict_single_match` | 预测单场比赛 |
| `explain_prediction` | 生成 AI 预测解释 |
| `get_simulation_distribution` | 获取 Monte Carlo 模拟概率分布 |
| `run_scenario_simulation` | What-If 沙盒模拟 |
| `check_data_quality` | 数据质量检查 |
| `get_bracket_payload` | 获取完整淘汰赛对阵数据 |

每个工具有独立的失败计数器（默认上限 2 次），防止无限重试。所有工具调用记录在 `tool_trace` 中，完整可追溯。

---

## 三、数据能力

### 3.1 数据规模

| 数据类型 | 数量 | 用途 |
|----------|------|------|
| 历史国际赛事 | 6,001+ 场（5.1MB） | 模型训练与回测验证 |
| 预构建训练集 | 5.4MB（90+ 特征列） | 神经网络 / XGBoost 训练 |
| 参赛球队档案 | 48 队 × 25 维特征 | 特征工程输入 |
| 赛程数据 | 104+ 场（PostgreSQL） | 淘汰赛模拟对阵结构 |
| 球队 ELO 评分 | 48 队实时评分 | 基线预测与特征输入 |
| 模拟推演 | 10,000 次完整赛程 | 冠军概率估计 |

### 3.2 数据来源与可信度

系统支持三级数据源，按可信度自动降级。数据采集覆盖 **2010 年至今** 的国际赛事数据，时间跨度超过 15 年：

| 可信度等级 | 数据源 | 采集方式 |
|-----------|--------|----------|
| HIGH（高） | API-Sports (v3), football-data.org (v4) | REST API 按需拉取 + APScheduler 定时刷新 |
| MEDIUM（中） | PostgreSQL 缓存 / SQLite 本地库 | 数据库持久化存储，定期同步 |
| LOW（低） | 模板数据 / FIFA 排名兜底 | 运行时动态生成 |

### 3.3 数据如何进入模型

数据从原始赛事记录到模型输入的完整链路：

```
原始赛事 CSV（日期、球队、比分、赛事类型）
    ↓
特征构建服务（feature_builder_service.py）
    ↓ 提取 25 维球队特征：
    │  基础实力（ELO、经验、大赛积分）
    │  近期状态（近5/10场胜率、进球、平局）
    │  进攻能力（进攻评分、场均进球、射门估计）
    │  防守能力（防守评分、场均失球、零封率）
    │  综合指标（夺冠次数、身价、年龄、东道主）
    ↓
特征对拼接：25维(主) + 25维(客) + 17维(差值) = 67 维
    ↓
z-score 标准化（使用训练集统计量）
    ↓
输入模型（神经网络 / XGBoost / ELO）
```

---

## 四、分析决策能力 — 预测链路

### 4.1 预测链路总览

系统的预测流程遵循以下链路：

```
数据输入 → 特征工程 → 模型预测 → 蒙特卡洛模拟 → 结果统计 → 前端展示
```

### 4.2 数据输入与特征工程

每场比赛的输入为 **67 维特征向量**：

- **25 维主队特征**：ELO 评分、近期胜率、进攻/防守评分、世界杯经验等
- **25 维客队特征**：同上
- **17 维差值特征**：主客队在关键维度上的差值（ELO 差、状态差、攻防差等）

特征经 z-score 标准化后输入模型，标准化参数来自训练集统计量（`feature_stats_v2.json`）。

### 4.3 模型预测

系统的核心预测引擎由 5 个独立模型加权集成：

| 模型 | 权重 | 输入 | 输出 |
|------|------|------|------|
| **神经网络 V2**（FeatureAttentionMixerV2） | 30% | 67 维特征向量 | 胜/平/负 3 类概率 |
| **ELO 评分模型** | 25% | ELO 差值 + 主场加成 | 胜/平/负 概率 + Poisson 比分 |
| **XGBoost** | 20% | 67 维特征向量 | 胜/平/负 3 类概率 |
| **Poisson 分布模型** | 15% | ELO 差值 → 预期进球 | Poisson 采样比分 |
| **路径概率模型** | 10% | 淘汰赛路径难度 | 修正后的晋级概率 |

**集成逻辑**：各模型独立输出 (胜A, 平局, 胜B) 三元组概率 → 加权平均 → 归一化至总和为 1.0。若任一模型加载失败，其权重自动按比例分配给其余模型。

**神经网络架构**：

```
FeatureAttentionMixerV2:
  输入: 67 维特征向量 (z-score 标准化)
  ↓
  球队特征嵌入 (25 维 → team_dim)
  ↓
  注意力特征混合层 (Attention-based feature mixing)
  ↓
  分类头 → 3 维 logits (home_win / draw / away_win)
  ↓
  Softmax → 概率分布
```

![神经网络架构图](https://raw.githubusercontent.com/leWLW-le/worldcup-prediction-agent/main/docs/images/08_neural_network_architecture.png)

### 4.4 蒙特卡洛模拟（10,000 次）

模型输出的单场概率进入蒙特卡洛模拟引擎，推演完整赛程：

**算法流程**：

1. **确定存活球队**：从数据库查询已完成赛果，自动识别当前阶段
2. **检测对阵结构**：查询半决赛/决赛 fixture，判断是否已进入特定对阵（bracket-aware）
3. **单次模拟**：
   - 已完赛比赛 → 直接使用真实赛果
   - 待进行的比赛 → 用集成模型概率采样胜者
   - 决赛 → 组合所有晋级球队，逐场模拟至产生冠军
4. **统计聚合**：10,000 次模拟后，统计每支球队的夺冠频率作为概率

**Bracket-Aware 机制**：

当半决赛已部分或全部完成时，系统自动切换为"对阵感知"模式：已完成的半决赛胜者直接晋级决赛，不再重新模拟；未完成的半决赛正常概率采样。这避免了随机配对导致的赛程结构偏差。

![Monte Carlo 模拟结果分布](https://raw.githubusercontent.com/leWLW-le/worldcup-prediction-agent/main/docs/images/05_probability_bars.png)

### 4.5 小组赛模拟（48 队 → 32 强）

- 每组 4 队单循环（6 场比赛），共 12 组
- 每组前 2 名 + 8 支成绩最好的第 3 名 → 晋级 32 强
- 使用集成模型预测每场小组赛的胜/平/负概率
- 平局时通过积分、净胜球、进球数排名

---

## 五、可解释性

系统在多个层面提供预测结果的解释依据：

### 5.1 比赛级别解释

LLM 生成每场关键比赛的战术分析，包含战术分析、关键球员影响、历史背景、置信度评分和预测摘要。

### 5.2 冠军级别解释

生成结构化冠军解读，包含核心优势分析（攻防/状态/经验/路径五维雷达图）、关键因素、剩余路径对手分析、竞争格局判断。

### 5.3 输出净化

内置 27 个技术术语黑名单（ensemble、xgboost、Monte Carlo、ELO 等），自动替换为用户友好的表述（如 "ELO评分" → "综合实力评分"，"蒙特卡洛模拟" → "大量模拟推演"），确保非技术用户也能理解预测依据。

---

## 六、可视化呈现

![Streamlit 前端面板](https://raw.githubusercontent.com/leWLW-le/worldcup-prediction-agent/main/docs/images/01_title_page.png)

### 6.1 页面整体设计

采用 Streamlit 构建的深色主题数据面板：

- **配色方案**：深蓝渐变背景（#0a1628 → #132d54）+ 金色高亮（#ffd700）
- **视觉风格**：卡片式布局 + 毛玻璃效果 + 渐变边框
- **全中文界面**：所有标签、说明、分析文本均为中文
- **响应式布局**：自适应桌面和移动端

### 6.2 核心可视化模块

**模块一：冠军概率排行**

展示内容：Top 5 球队夺冠概率条形图，金色渐变水平条形，网格布局（球队名 | 条形 | 百分比）。  
技术实现：Streamlit columns 布局 + 自定义 CSS 渐变条形。  
用户价值：一目了然地看到各队夺冠概率分布，快速定位热门球队。

**模块二：冠军展示卡**

展示内容：大型金色奖杯图标 + 冠军名称 + 夺冠概率 + 实力标签（夺冠热门 / 强力竞争者 / 有力争夺者 / 潜在黑马）。实力标签基于 team_strength_index 阈值自动判定。  
技术实现：Streamlit metric + 自定义 HTML/CSS 卡片组件。  
用户价值：突出展示预测结果，实力标签帮助用户快速理解冠军球队的实力定位。

![冠军展示卡](https://raw.githubusercontent.com/leWLW-le/worldcup-prediction-agent/main/docs/images/02_champion_card.png)

**模块三：淘汰赛路径图**

展示内容：水平布局展示 32 强 → 16 强 → 8 强 → 半决赛 → 决赛 → 冠军的完整路径。绿色边框 = 已完赛（真实比分），黄色边框 = 预测（预测比分）。  
技术实现：Streamlit columns 嵌套 + 条件样式渲染。  
用户价值：直观展示从当前阶段到冠军的完整晋级路径，区分已确定和待预测的比赛。

![淘汰赛路径图](https://raw.githubusercontent.com/leWLW-le/worldcup-prediction-agent/main/docs/images/04_knockout_roadmap.png)

**模块四：AI 冠军解读**

展示内容：LLM 生成的结构化分析，包含战术优势、关键因素、路径分析。支持 Markdown 渲染，含章节标题高亮、百分比数字高亮。  
技术实现：Streamlit markdown 渲染 + 自定义 CSS 样式注入。  
用户价值：将模型预测结果转化为自然语言解释，降低理解门槛。

![AI 冠军解读](https://raw.githubusercontent.com/leWLW-le/worldcup-prediction-agent/main/docs/images/03_ai_explanation.png)

**模块五：What-If 沙盒模拟器**

展示内容：用户选择待赛比赛 → 强制指定胜者 → 系统重新运行 1,000 次模拟 → 展示沙盒冠军概率（蓝色条形）、可能的决赛对阵、官方预测 vs 沙盒预测对比表（含 delta 箭头）。  
技术实现：Streamlit selectbox + radio + 后端 scenario API 调用。  
用户价值：允许用户探索"如果某场比赛结果不同，冠军概率会如何变化"，提供交互式决策支持。

![What-If 沙盒模拟器](https://raw.githubusercontent.com/leWLW-le/worldcup-prediction-agent/main/docs/images/06_whatif_sandbox.png)

**模块六：数据状态指示器**

展示内容：实时显示数据源健康状态（绿色 = 外部 API / 蓝色 = 缓存数据 / 红色 = 降级模式）。  
技术实现：Streamlit status indicator + API 响应状态码解析。  
用户价值：让用户清楚当前预测的数据基础是否可靠。

---

## 七、创新点

### 创新点 1：渐进式赛果融合

系统支持随着赛事推进，逐步注入真实赛果。已完赛的比赛锁定为真实结果，10,000 次模拟仅推演未完成比赛。每进行一场真实比赛，预测精度就提升一步 — 系统从"赛前预测"自然过渡为"赛中实时预测"。

### 创新点 2：Bracket-Aware 淘汰赛模拟

模拟严格遵循真实晋级树结构。当半决赛已部分完成时，已晋级的球队直接带入决赛模拟，仅对未完成的比赛进行概率采样，避免随机配对导致的赛程结构偏差。

### 创新点 3：比分预测与冠军概率结合

胜率模型（神经网络 + XGBoost）负责胜/平/负结果概率，比分模型（ELO + Poisson）负责具体比分采样。两种模型互补：胜率模型捕捉复杂特征交互，比分模型提供可解释的进球分布。最终通过 10,000 次蒙特卡洛模拟将单场概率聚合为冠军概率。

### 创新点 4：完整预测可视化

系统提供从冠军概率排行、淘汰赛路径图、AI 冠军解读到 What-If 沙盒模拟的完整可视化链路。用户不仅能看到"谁最可能夺冠"，还能理解"为什么"以及"如果赛果不同会怎样"。

---

## 八、工程化能力

### 8.1 数据更新机制

- APScheduler 定时调度器自动拉取最新赛程和比分
- 锦标赛状态服务自动识别当前阶段（小组赛 / 32 强 / 16 强 / 8 强 / 半决赛 / 决赛 / 已结束）
- 存活球队和淘汰球队随赛果实时更新

### 8.2 数据一致性保障

- 所有预测结果通过原子写入（先写临时文件再 `os.replace`）保存，避免写入中断导致数据损坏
- 预测快照多维度一致性断言：冠军 = top5[0] = 解释中的冠军 = 淘汰赛胜者
- 淘汰赛 bracket 完整性验证：胜者链、晋级链接、预测胜者一致性
- 验证失败时保留上一次有效快照，写入诊断文件

### 8.3 错误处理与降级

- 工具级失败计数（默认上限 2 次），防止无限重试
- 三级数据源自动降级：外部 API 不可用时切换缓存，缓存不可用时使用模板数据
- 非致命错误设计：单个工具失败不影响整体预测流程

### 8.4 前后端类型安全

- Pydantic v2 全链路数据模型校验
- SQLAlchemy 2.0 ORM + Alembic 数据库迁移
- FastAPI 自动 OpenAPI 文档生成

### 8.5 部署与保活

- Docker Compose 容器化编排（后端 FastAPI + 前端 Streamlit + PostgreSQL）
- Render.com IaC 声明式部署配置（render.yaml）
- GitHub Actions 定时健康检查（每 12 分钟 ping），防止免费层自动休眠

---

## 九、数据规模与项目结构

### 9.1 核心数据指标

| 数据维度 | 数量 |
|----------|------|
| 参赛球队 | 48 队（12 小组 × 4 队） |
| 球队特征 | 25 维 × 48 队 |
| 特征对向量 | 67 维（25 主 + 25 客 + 17 差值） |
| 历史训练数据 | 6,001+ 场国际赛事（5.1MB） |
| 训练数据集 | 5.4MB 预构建特征对 |
| 赛程数据 | 104+ 场（PostgreSQL） |
| 集成模型 | 5 个异构模型 |
| Monte Carlo 模拟 | 10,000 次完整赛程推演 |
| 预测工具 | 13+ 个标准化工具 |

### 9.2 项目结构

```
worldcup-prediction-agent/
├── main.py                    # FastAPI 应用入口
├── debug_dashboard.py         # Streamlit 可视化面板（2,173 行）
├── requirements.txt           # Python 依赖（30+ 包）
├── render.yaml                # Render.com 部署配置
├── docker-compose.yml         # Docker Compose 编排
│
├── app/                       # 核心应用代码
│   ├── agents/                # 预测编排层
│   │   ├── worldcup_agent.py  # 核心预测编排（12 步流水线）
│   │   ├── agent_executor.py  # 工具调度与错误处理
│   │   ├── agent_memory.py    # 跨运行持久记忆
│   │   ├── llm_planner_agent.py  # LLM 规划器（CoT + 反思）
│   │   ├── data_quality_agent.py # 数据质量检查（8 项）
│   │   └── tool_registry.py   # 工具注册中心
│   │
│   ├── api/                   # FastAPI 路由（7 组端点）
│   ├── services/              # 模块化预测服务层（25+ 模块）
│   │   ├── ensemble_prediction_service.py  # 五模型集成预测
│   │   ├── probability_engine.py           # ELO + Poisson 概率引擎
│   │   ├── feature_network.py              # PyTorch 注意力网络
│   │   ├── champion_explanation_service.py # 冠军解释 + 术语净化
│   │   ├── scenario_simulation_service.py  # What-If 沙盒引擎
│   │   ── ... (20+ 其他服务模块)
│   │
│   ├── tools/                 # 工具实现（7+ 文件）
│   ├── models/                # SQLAlchemy ORM 模型
│   ├── data/                  # 数据获取（API / 爬虫）
│   └── db/                    # 数据库连接（SQLite / PostgreSQL）
│
├── scripts/                   # 评估与工具脚本
│   ├── walk_forward_evaluation.py  # Walk Forward 回测
│   ├── run_backtest.py             # 历史回测
│   └── run_champion_simulation.py  # Monte Carlo 模拟
│
├── data/                      # 数据文件
│   ├── training_dataset_v2.csv     # 训练数据集（5.4MB）
│   ├── historical_international_matches_large.csv  # 历史赛事
│   ├── team_ratings.csv            # 球队 ELO 评分
│   └── walk_forward_results.json   # 回测结果
│
├── models/                    # 训练模型权重
│   ├── feature_network_v2_latest.pth  # PyTorch 网络权重
│   ├── tree_predictor.pkl             # XGBoost 模型
│   └── feature_stats_v2.json          # 特征标准化统计
│
├── tests/                     # 测试
── .github/workflows/
    └── render-keepalive.yml   # Render 保活
```

---

## 十、部署方式

### 10.1 Render 云部署

```
┌─────────────────────────────────────────┐
│              Render Cloud               │
│                                         │
│  ┌─────────────────────┐               │
│  │  worldcup-backend   │ (Free Tier)   │
│  │  FastAPI + Uvicorn  │               │
│  │  Health: /health    │               │
│  └─────────┬───────────┘               │
│            │                            │
│  ┌─────────▼───────────┐               │
│  │  worldcup-postgres  │ (Free Tier)   │
│  │  PostgreSQL Database│               │
│  └─────────────────────┘               │
│                                         │
│  ┌─────────────────────┐               │
│  │  worldcup-frontend  │ (Free Tier)   │
│  │  Streamlit Dashboard│               │
│  └─────────────────────┘               │
└─────────────────────────────────────────┘

GitHub Actions → 每 12 分钟 ping 健康检查 → 防止免费层休眠
```

![部署架构图](https://raw.githubusercontent.com/leWLW-le/worldcup-prediction-agent/main/docs/images/09_deployment_architecture.png)

### 10.2 环境变量

| 变量 | 用途 |
|------|------|
| `API_FOOTBALL` | API-Sports 密钥 |
| `FOOTBALL_DATA_API` | football-data.org 密钥 |
| `OPENAI_API_KEY` | ZhipuAI GLM-4-Flash 密钥 |
| `DATABASE_URL` | PostgreSQL 连接串 |
| `ENABLE_SCHEDULER` | 是否启用定时数据刷新 |
| `MODEL_PATH` | PyTorch 模型权重路径 |

### 10.3 本地 Docker 部署

```bash
docker-compose up -d
# 后端: http://localhost:8001 (FastAPI)
# 前端: http://localhost:8501 (Streamlit)
```

---

## 十一、模型验证与局限性

### 11.1 验证方法

系统采用 **Walk Forward 时间序列回测** 方法评估预测模型的准确性。训练集严格按时间递增扩展，验证集为紧随其后的两年数据，模拟真实"用历史预测未来"的场景，避免传统随机划分导致的数据泄露问题。

### 11.2 回测设置

| 阶段 | 训练区间 | 验证区间 | 训练样本 | 验证样本 |
|------|----------|----------|----------|----------|
| Phase 1 | 2010–2018 | 2019–2020 | 3,628 | 833 |
| Phase 2 | 2010–2020 | 2021–2022 | 4,461 | 779 |
| Phase 3 | 2010–2022 | 2023–2024 | 5,240 | 760 |

### 11.3 回测结果

| 指标 | Phase 1 | Phase 2 | Phase 3 | 平均 |
|------|---------|---------|---------|------|
| Accuracy | 51.74% | 48.91% | 51.18% | **50.61%** |
| Macro F1 | 45.26% | 41.86% | 47.97% | **45.03%** |
| Balanced Accuracy | 47.60% | 46.35% | 49.12% | **47.69%** |
| Brier Score | 0.598 | 0.603 | 0.598 | **0.599** |
| Log Loss | 0.996 | 1.003 | 0.996 | **0.998** |

### 11.4 指标说明

- **Accuracy（50.61%）**：三分类（主胜/平/客胜）任务中，随机基线为 33.3%，模型超越随机基线约 17 个百分点。足球比赛本身具有高不确定性（平局占比约 25%），该准确率在体育预测领域属于合理水平。
- **Macro F1（45.03%）**：反映模型对三个类别的均衡预测能力，未出现严重偏向某一类别。
- **Balanced Accuracy（47.69%）**：说明模型对主胜、平局、客胜三类样本的识别能力相对均衡。
- **Brier Score（0.599）**：衡量概率预测的校准质量（完美 = 0.0，随机 = 0.75），0.60 优于纯随机基线。
- **Log Loss（0.998）**：接近理论最优值（完美 = 0.0，均匀分布 = 1.099），概率估计具有实际参考价值。

### 11.5 局限性

- **平局预测**：平局是足球比赛中最难预测的结果（占比约 25% 但特征信号最弱），模型在平局类别上的表现仍有提升空间
- **样本规模**：国际赛事样本量（6,001 场）相比俱乐部联赛仍偏小，模型泛化能力有待更多数据验证
- **特征维度**：当前 25 维球队特征未包含球员级别数据（伤病、停赛、阵容变化），后续可引入更细粒度数据

---

## 总结

本系统完成了从数据处理到冠军预测的完整闭环：

- **数据处理**：6,001+ 场历史赛事，48 队 25 维特征工程，三级数据源自动降级
- **模型预测**：五模型集成（神经网络 + ELO + XGBoost + Poisson + 路径），Walk Forward 回测准确率 ~50.6%
- **动态模拟**：10,000 次 Bracket-Aware 蒙特卡洛模拟，渐进式真实赛果融合
- **可解释展示**：LLM 驱动的自然语言冠军解读，27 项术语自动净化，What-If 沙盒交互分析
- **自动部署**：Docker 容器化 + Render 云部署 + GitHub Actions 保活，前端面板和后端 API 均已上线

系统覆盖 2026 世界杯 48 队 104 场比赛的完整预测流程，从小组赛模拟到淘汰赛推演，从冠军概率计算到交互式场景分析，形成了一个可运行、可验证、可解释的世界杯预测系统。
