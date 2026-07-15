# 2026 世界杯冠军预测 Agent · 参赛提交文档

**项目名称**：World Cup Prediction Agent — 世界杯冠军预测智能体  
**线上地址**：  
- 前端面板：https://worldcup-frontend.onrender.com  
- 后端 API：https://worldcup-backend-k2sn.onrender.com  
- API 文档：https://worldcup-backend-k2sn.onrender.com/docs  

**GitHub 仓库**：https://github.com/leWLW-le/worldcup-prediction-agent  
**技术栈**：Python 3.12 / FastAPI / Streamlit / PyTorch / XGBoost / LangChain / SQLAlchemy / PostgreSQL  
**生成时间**：2026-07-16  

---

## 一、系统架构设计

### 1.1 整体架构概览

系统采用 **Agent + Tools** 智能体架构，区别于传统的线性 Pipeline。核心分为四层：

```
┌─────────────────────────────────────────────────────────┐
│                   Streamlit 可视化面板                     │
│         （深蓝金色主题 · 交互式 What-If 沙盒）              │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP REST API
┌────────────────────────▼────────────────────────────────┐
│                  FastAPI 后端服务层                        │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Agent 编排层 │  │  工具注册中心  │  │  API 路由层   │  │
│  │  (4种运行模式) │  │  (13+ 工具)   │  │  (6组端点)    │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────────┘  │
│         │                 │                              │
│  ┌──────▼─────────────────▼──────────────────────────┐  │
│  │              服务层 (25+ 微服务模块)                  │  │
│  │  集成预测 · 概率引擎 · 锦标赛状态 · LLM解释 · 沙盒   │  │
│  └──────────────────────┬────────────────────────────┘  │
└─────────────────────────┼───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│                    数据与存储层                            │
│  PostgreSQL · JSON 数据文件 · 训练模型 · Agent 记忆       │
└─────────────────────────────────────────────────────────┘
```

**四种运行模式**：

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `workflow` | 固定 12 步顺序流水线，稳定基线 | 生产环境默认模式 |
| `llm_planner_safe` | LLM 自主决策工具调用，失败时回退到 workflow | 智能探索 + 安全兜底 |
| `llm_planner_strict` | LLM 自主决策，无回退，不完整则标记失败 | 纯 LLM 能力验证 |
| `llm_planner` | `llm_planner_safe` 的别名 | 向后兼容 |

### 1.2 Agent 编排引擎

Agent 是系统的"大脑"，负责协调从数据采集到最终预测的完整链路。

**12 步流水线（workflow 模式）**：

1. **设定目标** — 明确预测赛季和任务
2. **数据计划** — 定义需要采集的数据维度（赛程、球队、积分榜、实时比分、历史数据）
3. **API 数据采集** — 调用 API-Sports 获取实时赛程、球队信息、小组积分榜
4. **历史数据加载** — 从本地数据库加载 2018+ 年国际赛事历史数据
5. **数据质量检查** — 8 项检查：API 密钥、赛程可用性、球队数据、来源可信度分级
6. **特征构建** — 构建 25 维球队特征向量（ELO、攻防、状态、经验等）
7. **小组赛预测** — 模拟 12 组 × 4 队单循环，确定 32 强出线名额
8. **淘汰赛预测** — 从 32 强 → 16 强 → 8 强 → 半决赛 → 决赛逐轮推演
9. **冠军确认** — 多级回退链：Monte Carlo 第一 > 决赛胜者 > 实力评分最高 > 出线队首名
10. **AI 解释生成** — LLM 生成冠军预测的自然语言解释
11. **可视化构建** — 构建前端消费的结构化数据
12. **结果保存** — 原子写入 JSON，确保数据一致性

**LLM 智能规划器**（`llm_planner_safe` 模式）：

LLM 规划器最多执行 20 步自主决策，每步包括：选择工具 → 执行 → 反思 → 决定下一步。系统内置定期反思机制（每 4 步一次），评估进度并调整策略。若 20 步内未完成，自动回退到 workflow 补齐缺失步骤。

**Agent 记忆系统**：

跨运行持久化学习，存储在 `agent_memory.json`：

| 记忆类型 | 内容 | 容量 |
|----------|------|------|
| 预测历史 | 每次运行的冠军、状态、数据质量、工具调用摘要 | 最近 50 次 |
| 工具可靠性 | 每个工具的总调用次数、成功率、失败类型分布 | 无限 |
| 经验教训 | 自动检测的模式（如 API 限流→跳过 API 工具） | 最近 20 条 |

记忆系统会注入到 LLM 规划器的上下文中，使 Agent "越用越聪明"。

### 1.3 工具注册中心

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

## 二、数据采集能力

### 2.1 多源数据整合

系统支持三级数据源，按可信度自动降级：

| 可信度等级 | 数据源 | 说明 |
|-----------|--------|------|
| HIGH（高） | API-Sports, football-data.org | 外部权威 API 实时数据 |
| MEDIUM（中） | 本地数据库缓存 / API 缓存 | 已验证的历史抓取数据 |
| LOW（低） | LLM 生成 / 模板数据 | 当外部 API 不可用时的兜底 |
| PREDICTION | 模型预测输出 | 尚未验证的预测结果 |

### 2.2 数据维度覆盖

| 数据类别 | 内容 | 规模 |
|----------|------|------|
| 参赛球队 | 48 支球队 × 12 小组（A-L），含真实 ELO 评分 | 48 队 |
| 历史赛事 | 2018 年至今国际比赛数据（CSV） | 数千场 |
| 球队特征 | 25 维特征向量（详见 2.3） | 48 × 25 维 |
| 训练数据 | 预构建特征对数据集 | 5.4MB |
| 赛程数据 | 小组赛 + 淘汰赛完整赛程，存储于 PostgreSQL | 104+ 场 |
| 实时数据 | API-Sports 实时比分和赛程更新 | 按需拉取 |

### 2.3 球队特征工程（25 维）

每支球队用 25 个维度刻画，分为 5 大类：

**基础实力（5 维）**：ELO 评分、ELO 年变化、ELO 三年变化、世界杯经验指数、大赛积分

**近期状态（6 维）**：近 5 场胜率、近 10 场胜率、近 5 场进球、近 10 场进球、近 5 场平局数、近 10 场平局数

**进攻能力（4 维）**：进攻评分、场均进球、射门估计、大胜率

**防守能力（4 维）**：防守评分、场均失球、零封率、进球稳定性

**综合指标（6 维）**：世界杯夺冠次数、球队身价指数、平均年龄、东道主标记、历史最佳成绩、上届表现

比赛预测时，系统构建 **67 维特征对向量**：25 维（主队）+ 25 维（客队）+ 17 维（差值特征），经 z-score 标准化后输入模型。

---

## 三、分析决策能力 — 预测逻辑与决策链路

### 3.1 五模型集成预测引擎

系统的核心预测引擎由 5 个独立模型加权集成，兼顾不同维度的预测能力：

| 模型 | 权重 | 技术特点 |
|------|------|----------|
| **神经网络 V2**（FeatureAttentionMixerV2） | 30% | PyTorch 注意力特征网络，67 维输入 → 3 类输出（胜/平/负），softmax 概率 |
| **ELO 评分模型** | 25% | 经典 ELO 差分模型，主场加成 +100 ELO，Poisson 分布采样进球 |
| **XGBoost** | 20% | 梯度提升树模型，基于历史赛事训练 |
| **Poisson 分布模型** | 15% | 基于 ELO 差分的预期进球 → Poisson 采样比分 |
| **路径概率模型** | 10% | 考虑淘汰赛路径难度的修正模型 |

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

### 3.2 ELO + Poisson 基线预测

作为集成引擎的基线，ELO 模型提供稳健的预测锚点：

- **胜率映射**：`ELO_diff = (主队ELO - 客队ELO) + 100（主场加成）`
- **预期进球**：`xG_home = max(0, 1.5 + ELO_diff / 400)`，`xG_away = max(0, 1.5 - ELO_diff / 400)`
- **比分采样**：从 `Poisson(xG_home)` 和 `Poisson(xG_away)` 独立采样
- **置信度**：`min(0.95, 0.5 + |ELO_diff| / 2000)`，线性增长，上限 95%

### 3.3 蒙特卡洛模拟（10,000 次）

这是系统的核心推理引擎，通过大规模随机模拟推演完整赛程：

**算法流程**：

1. **确定存活球队**：从数据库查询已完成赛果，自动识别当前阶段和仍有夺冠可能的球队
2. **检测对阵结构**：查询半决赛/决赛 fixture，判断是否已进入特定对阵（bracket-aware）
3. **单次模拟**：
   - 已完赛比赛 → 直接使用真实赛果
   - 待进行的半决赛 → 用集成模型概率采样胜者
   - 已晋级决赛的球队 → 直接带入
   - 决赛 → 组合所有晋级球队，逐场模拟至产生冠军
4. **统计聚合**：10,000 次模拟后，统计每支球队的夺冠频率作为概率

**Bracket-Aware 机制**（核心创新）：

当半决赛已部分或全部完成时，系统自动切换为"对阵感知"模式：
- 已完成的半决赛 → 胜者直接晋级决赛，不再重新模拟
- 未完成的半决赛 → 正常概率采样
- 决赛 → 由已晋级球队 + 采样胜者组成

这确保了模拟严格遵循真实赛程结构，而非随机配对。

**严格断言验证**：
- 冠军必须属于 surviving_teams
- champion_counts 总和必须等于 n_simulations
- 概率总和必须约等于 1.0

### 3.4 小组赛模拟（48 队 → 32 强）

完整的 48 队 12 小组模拟：
- 每组 4 队单循环（6 场比赛）
- 每组前 2 名 + 8 支成绩最好的第 3 名 → 晋级 32 强
- 使用集成模型预测每场小组赛的胜/平/负概率
- 平局时通过积分、净胜球、进球数排名

### 3.5 推理过程的可解释性

系统在多个层面提供可解释的推理依据：

**比赛级别**：LLM 生成每场关键比赛的战术分析，包含 `tactical_analysis`（战术分析）、`key_player_impact`（关键球员影响）、`historical_context`（历史背景）、`confidence_score`（置信度）、`prediction_summary`（预测摘要）。

**冠军级别**：生成结构化解释，包含核心优势分析（攻防/状态/经验/路径五维雷达图）、关键因素、剩余路径对手分析、竞争格局判断。

**输出净化**：内置 27 个技术术语黑名单（ensemble、xgboost、Monte Carlo、ELO 等），自动替换为用户友好的表述（如 "ELO评分" → "综合实力评分"，"蒙特卡洛模拟" → "大量模拟推演"）。

---

## 四、可视化呈现

### 4.1 页面整体设计

采用 Streamlit 构建的深色主题数据面板，营造专业体育数据可视化风格：

- **配色方案**：深蓝渐变背景（#0a1628 → #132d54）+ 金色高亮（#ffd700）
- **视觉风格**：卡片式布局 + 毛玻璃效果（backdrop-filter blur）+ 渐变边框
- **全中文界面**：所有标签、说明、分析文本均为中文
- **响应式布局**：自适应桌面和移动端

### 4.2 八大可视化模块

**模块一：冠军展示卡（Champion Card）**  
大型金色奖杯图标 + 冠军名称（3rem 金色字体）+ 夺冠概率 + 实力标签（夺冠热门 / 强力竞争者 / 有力争夺者 / 潜在黑马）。实力标签基于 team_strength_index 阈值（0.75 / 0.6 / 0.45）自动判定。

**模块二：AI 冠军解释（AI Champion Explanation）**  
LLM 生成的结构化分析，包含战术优势、关键因素、路径分析。支持 Markdown 渲染，含章节标题高亮、百分比数字高亮、结论段落特殊样式。

**模块三：淘汰赛路径图（Knockout Roadmap）**  
水平布局展示 32 强 → 16 强 → 8 强 → 半决赛 → 决赛 → 冠军的完整路径。绿色边框 = 已完赛（真实比分），黄色边框 = 预测（预测比分）。

**模块四：Top 5 夺冠概率条形图**  
金色渐变水平条形图，网格布局（球队名 | 条形 | 百分比），直观展示各队夺冠概率分布。

**模块五：What-If 沙盒模拟器（核心交互亮点）**  
这是系统最具差异化的功能模块：
- 用户选择一场待进行的比赛
- 强制指定胜者
- 系统重新运行 1,000 次 Monte Carlo 模拟
- 展示沙盒冠军概率（蓝色条形）、可能的决赛对阵、晋级概率
- 官方预测 vs 沙盒预测对比表（含 delta 箭头：↑上升 / ↓下降 / 已淘汰）
- AI 沙盒解读（LLM 生成）

**模块六：数据状态指示器**  
实时显示数据源健康状态（绿色 = 外部 API / 蓝色 = 缓存数据 / 红色 = 降级模式），让用户清楚当前预测的数据基础。

**模块七：AI 分析流程展示**  
可折叠面板展示 5 步 AI 分析过程：数据采集 → 历史分析 → 集成模型 → Monte Carlo 模拟 → AI 解释。

**模块八：操作面板**  
三个核心操作按钮：重新预测（调用 run-prediction）、刷新数据（调用 full-refresh）、清除缓存。

### 4.3 前端技术架构

```
Streamlit Dashboard (debug_dashboard.py, ~890 行)
  ├── 数据加载: HTTP API (/agent/final-result) + 本地 JSON 回退
  ├── 缓存: 300 秒 TTL 缓存，避免频繁请求
  ├── 一致性校验: top5[0] 必须匹配解释中的冠军
  ├── 自定义 CSS: ~520 行深蓝金色主题样式
  └── 交互组件: Selectbox / Radio / Button / Expander
```

---

## 五、创新与创意

### 5.1 预测逻辑创新

**创新点 1：五模型集成预测**

不同于单一模型方案，系统集成了 5 个异构模型（注意力神经网络 + ELO + XGBoost + Poisson + 路径概率），各有侧重：神经网络捕捉非线性特征交互，ELO 提供稳健基线，XGBoost 擅长表格数据，Poisson 处理进球分布，路径模型修正赛程难度偏差。加权集成降低了单一模型的偏见和方差。

**创新点 2：Bracket-Aware 蒙特卡洛模拟**

传统 Monte Carlo 模拟在赛事进行中往往忽略已有的对阵结构，随机配对存活球队。系统创新性地引入对阵感知机制：自动检测已完成的半决赛/决赛，将已晋级球队直接带入后续模拟，仅对未完成的比赛进行概率采样。这确保了模拟结构与真实赛程严格一致。

**创新点 3：渐进式赛果融合**

系统支持随着赛事推进，逐步注入真实赛果。已完赛的比赛锁定为真实结果，10,000 次模拟仅推演未完成比赛。这意味着每进行一场真实比赛，预测精度就提升一步 — 系统从"赛前预测"进化为"赛中实时预测"。

**创新点 4：自动数据源降级**

三级数据源（外部 API → 本地缓存 → 模板兜底）自动切换，确保系统在任何网络环境下都能运行。数据质量检查 Agent 执行 8 项验证，实时报告数据可信度等级。

### 5.2 Agent 设计创新

**创新点 5：双模式智能体架构**

系统同时支持固定流水线（workflow）和 LLM 自主规划（llm_planner）两种模式。LLM 规划器基于 Chain-of-Thought 推理，自主选择工具、评估结果、调整策略，并具备定期反思能力。safe 模式提供 workflow 兜底，strict 模式则完全依赖 LLM 决策 — 为研究和生产提供灵活选择。

**创新点 6：跨运行持久学习**

Agent 记忆系统记录每次预测的结果、工具可靠性、失败模式，并自动检测经验教训（如"API 限流时应跳过 API 工具"）。这些记忆注入到后续 LLM 规划上下文中，实现跨运行的持续学习。

**创新点 7：What-If 沙盒模拟器**

在冠军预测之外，提供交互式"如果...会怎样"分析：用户可强制指定任何待赛比赛的胜者，系统重新运行 1,000 次 Monte Carlo 模拟，展示该假设下的冠军概率变化。这让教练组、分析师和球迷能探索不同赛果的连锁影响。

**创新点 8：可解释性输出净化**

LLM 生成的解释经过 27 个技术术语的自动替换，确保最终用户看到的是自然语言（"综合实力评分"而非"ELO 评分"，"大量模拟推演"而非"蒙特卡洛模拟"）。这在保持技术严谨性的同时，让非技术用户也能理解预测依据。

### 5.3 工程化创新

**创新点 9：原子写入与一致性保障**

所有预测结果通过 `atomic_write_json`（先写临时文件再 `os.replace`）保存，避免写入中断导致的数据损坏。`_validate_prediction_snapshot` 执行多维度一致性断言（冠军 = top5[0] = 解释中的冠军 = 淘汰赛胜者），验证失败时保留上一次有效快照，写入诊断文件。

**创新点 10：淘汰赛 bracket 完整性验证**

`validate_bracket_integrity` 验证整个淘汰赛树的结构完整性：胜者链、晋级链接、预测胜者一致性。验证失败时不保存结果，防止错误数据传播。

---

## 六、加分项

### 6.1 实时赛况追踪能力

系统通过 API-Sports 集成实现实时赛况追踪：
- 定时调度器（APScheduler）自动拉取最新赛程和比分
- 104+ 场比赛数据存储在 PostgreSQL 数据库
- 锦标赛状态服务自动识别当前阶段（小组赛 / 32 强 / 16 强 / 8 强 / 半决赛 / 决赛 / 已结束）
- 存活球队和淘汰球队实时更新

### 6.2 What-If 沙盒交互分析

在标准预测之外，额外提供：
- 用户可选择任何待进行的比赛
- 强制指定胜者后重新模拟
- 展示沙盒冠军概率 vs 官方预测的 delta 变化
- AI 生成沙盒结果解读
- 已淘汰球队自动标记

### 6.3 工程化质量

| 维度 | 实现 |
|------|------|
| 数据校验 | Pydantic v2 全链路数据模型校验 |
| 数据库 ORM | SQLAlchemy 2.0 + Alembic 迁移 |
| 错误处理 | 工具级失败计数 + 自动回退 + 非致命错误设计 |
| 原子操作 | JSON 原子写入 + 数据库事务 |
| 一致性验证 | 预测快照断言 + bracket 完整性验证 + API 一致性检查 |
| 部署方案 | Docker Compose + Render IaC + 健康检查 |
| 保活机制 | GitHub Actions 定时 ping 防止 Render 免费层休眠 |
| 文档体系 | 15 份专项文档覆盖架构、API、数据库、各模块 |

### 6.4 数据规模

| 数据维度 | 数量 |
|----------|------|
| 参赛球队 | 48 队（12 小组 × 4 队） |
| 球队特征 | 25 维 × 48 队 = 1,200 个特征值 |
| 特征对向量 | 67 维（25 主 + 25 客 + 17 差值） |
| 历史训练数据 | 数千场国际赛事 |
| 训练数据集 | 5.4MB 预构建特征对 |
| 赛程数据 | 104+ 场（存储于 PostgreSQL） |
| 集成模型 | 5 个异构模型 |
| Monte Carlo 模拟 | 10,000 次完整赛程推演 |
| Agent 工具 | 13+ 个标准化工具 |
| 技术文档 | 15 份专项指南 |

---

## 七、项目文件结构

```
worldcup-prediction-agent/
├── main.py                              # FastAPI 应用入口（lifespan 管理）
├── debug_dashboard.py                   # Streamlit 可视化面板（~890 行）
├── requirements.txt                     # Python 依赖（30+ 包）
├── render.yaml                          # Render.com IaC 部署配置
├── docker-compose.yml                   # Docker Compose 编排
├── Dockerfile.backend                   # 后端 Docker 镜像
├── Dockerfile.frontend                  # 前端 Docker 镜像
├── worldcup.db                          # SQLite 主数据库
│
├── app/                                 # 核心应用代码
│   ├── agents/                          # Agent 编排层（7 个模块）
│   │   ├── worldcup_agent.py            # 核心预测 Agent（77KB，12 步流水线）
│   │   ├── agent_executor.py            # Agent 执行引擎（工具调度 + 错误处理）
│   │   ├── agent_state.py               # Agent 全局状态（30+ 字段）
│   │   ├── agent_memory.py              # Agent 持久记忆（跨运行学习）
│   │   ├── llm_planner_agent.py         # LLM 规划 Agent（CoT + 反思）
│   │   ├── data_quality_agent.py        # 数据质量检查 Agent（8 项检查）
│   │   ├── tool_registry.py             # 工具注册中心
│   │   ├── tool_adapters.py             # 工具适配器层（13+ 工具）
│   │   └── tool_schemas.py              # 工具 Schema 定义
│   │
│   ├── api/                             # FastAPI 路由（6 组端点）
│   │   ├── agent.py                     # /agent/run-prediction, /agent/status
│   │   ├── data.py                      # /data/full-refresh
│   │   ├── simulation.py                # /simulation/*
│   │   ├── scenario.py                  # /scenario/* (What-If 沙盒)
│   │   ├── predictions.py               # /predictions/*
│   │   └── teams.py                     # /teams/*
│   │
│   ├── services/                        # 业务逻辑层（25+ 微服务）
│   │   ├── ensemble_prediction_service.py  # 五模型集成预测
│   │   ├── prediction_service.py           # ELO + Poisson 基线
│   │   ├── probability_engine.py           # 概率计算引擎
│   │   ├── feature_network.py              # PyTorch 注意力网络
│   │   ├── tournament_state_service.py     # 锦标赛状态追踪
│   │   ├── champion_explanation_service.py # 冠军解释生成 + 术语净化
│   │   ├── llm_explainer.py               # LLM 比赛解释 Agent
│   │   ├── scenario_simulation_service.py  # What-If 沙盒引擎
│   │   ├── scheduled_refresh_service.py    # 定时数据刷新
│   │   ├── data_source_manager.py          # 多源数据管理
│   │   └── ... (15+ 其他服务)
│   │
│   ├── tools/                           # Agent 工具实现
│   │   ├── bracket_tool.py              # 淘汰赛 bracket 生成（45KB）
│   │   ├── api_sports_tool.py           # API-Sports 集成
│   │   ├── explanation_tool.py          # LLM 解释封装
│   │   └── ... (9+ 其他工具)
│   │
│   ├── models/                          # 数据模型
│   │   ├── agent_models.py              # SQLAlchemy ORM 模型
│   │   └── ... (Pydantic Schema)
│   │
│   ├── data/                            # 数据获取
│   │   ├── api_fetcher.py               # API-Sports / football-data.org
│   │   ├── web_scraper.py               # Playwright 爬虫
│   │   └── football_cache.db            # SQLite 缓存
│   │
│   ├── db/                              # 数据库连接
│   └── core/                            # 配置与调度
│
├── scripts/                             # 工具脚本（50+ 文件）
│   ├── run_champion_simulation.py       # Monte Carlo 模拟（bracket-aware）
│   └── ... (数据导入/模型训练/回测/部署验证)
│
├── data/                                # 数据文件
│   ├── simulation_distribution.json     # Monte Carlo 模拟结果
│   ├── final_agent_result.json          # 最终预测结果
│   ├── agent_memory.json                # Agent 持久记忆
│   ├── team_ratings.csv                 # 球队 ELO 评分
│   ├── historical_international_matches_large.csv  # 历史赛事数据
│   └── training_dataset_v2.csv          # 训练数据集
│
├── models/                              # 训练模型
│   ├── feature_network_v2_latest.pth    # PyTorch 注意力网络权重
│   ├── tree_predictor.pkl               # XGBoost 模型
│   └── feature_stats_v2.json            # 特征标准化统计
│
├── tests/                               # 测试
│   ├── test_bracket_integrity.py        # Bracket 完整性测试（29KB）
│   ├── test_final_result.py             # 最终结果验证（18KB）
│   └── test_save_integration.py         # 保存集成测试（15KB）
│
└── .github/workflows/
    └── render-keepalive.yml             # Render 保活（每 12 分钟 ping）
```

---

## 八、部署架构

### 8.1 Render 云部署

```
┌─────────────────────────────────────────┐
│              Render Cloud               │
│                                         │
│  ┌─────────────────────┐               │
│  │  worldcup-backend   │ (Free Tier)   │
│  │  FastAPI + Uvicorn  │               │
│  │  Port: $PORT        │               │
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
│  │  Health: /_stcore/  │               │
│  │         health      │               │
│  └─────────────────────┘               │
└─────────────────────────────────────────┘

GitHub Actions → 每 12 分钟 ping 健康检查
                 防止免费层自动休眠
```

### 8.2 环境变量配置

| 变量 | 用途 |
|------|------|
| `API_FOOTBALL` | API-Sports 密钥 |
| `FOOTBALL_DATA_API` | football-data.org 密钥 |
| `OPENAI_API_KEY` | ZhipuAI GLM-4-Flash 密钥 |
| `OPENAI_BASE_URL` | LLM API 端点 |
| `DATABASE_URL` | PostgreSQL 连接串 |
| `ENABLE_SCHEDULER` | 是否启用定时数据刷新 |
| `MODEL_PATH` | PyTorch 模型权重路径 |

### 8.3 本地 Docker 部署

```bash
# Docker Compose 一键启动
docker-compose up -d

# 后端: http://localhost:8001 (FastAPI)
# 前端: http://localhost:8501 (Streamlit)
```

---

## 总结

本系统是一个工程完整性极高的 2026 世界杯冠军预测 Agent，具备以下核心能力：

**数据采集**：多源三级数据整合（API-Sports + football-data.org + 本地缓存 + 模板兜底），48 队 25 维特征工程，PostgreSQL 持久化存储。

**分析决策**：五模型集成预测（注意力神经网络 30% + ELO 25% + XGBoost 20% + Poisson 15% + 路径 10%），10,000 次 Bracket-Aware 蒙特卡洛模拟，渐进式真实赛果融合。

**智能体架构**：Agent + Tools 分层设计，4 种运行模式（workflow / LLM safe / LLM strict），13+ 标准化工具，跨运行持久学习记忆，LLM Chain-of-Thought 规划与反思。

**可解释性**：LLM 驱动的自然语言预测解释，27 项技术术语自动净化，五维雷达图（攻防/状态/经验/路径），What-If 沙盒交互分析。

**可视化呈现**：深蓝金色主题 Streamlit 面板，8 大功能模块，冠军卡 + 淘汰赛路径图 + 概率条形图 + 沙盒模拟器，全中文交互界面。

**工程化质量**：原子写入 + 一致性断言 + bracket 完整性验证 + Docker 容器化 + Render IaC + GitHub Actions 保活 + 15 份技术文档。
