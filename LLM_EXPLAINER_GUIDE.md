# LLM 解释 Agent 使用指南

## 📋 概述

`MatchExplainerAgent` 是一个基于 LangChain 和 RAG（检索增强生成）技术的智能解释系统，用于为底层概率引擎生成的比赛预测结果提供专业、结构化的战术分析解释。

### 核心价值

- **强校验输出**：使用 Pydantic Schema 确保输出格式严格一致
- **工具化接口**：封装战术查询和历史记录查询为标准化工具（MCP 风格）
- **约束明确**：LLM 只能解释结果，绝对不能修改比分
- **可解释性**：提供战术分析、关键球员影响、历史背景三维度的解释

---

## 🏗️ 架构设计

### 核心组件

1. **MatchExplanation (Pydantic Schema)**
   - 定义结构化输出的数据模型
   - 包含战术分析、关键球员、历史背景、置信度等字段

2. **TacticalKnowledgeBase**
   - 模拟 ChromaDB 向量数据库
   - 存储球队战术风格、优缺点、关键球员等信息
   - 提供战术知识检索接口

3. **LangChain Tools (MCP 风格)**
   - `get_team_tactics`: 获取球队战术档案
   - `get_historical_record`: 查询历史交锋记录
   - `search_tactical_database`: 搜索战术数据库

4. **MatchExplainerAgent**
   - 主控制器，协调 LLM 和工具
   - 使用 Prompt 模板引导 LLM 行为
   - 支持结构化输出和回退机制

---

## 📦 API 文档

### MatchExplanation Schema

```python
class MatchExplanation(BaseModel):
    """比赛解释的结构化输出"""
    
    tactical_analysis: str = Field(
        description="战术相克分析"
    )
    
    key_player_impact: str = Field(
        description="关键球员影响"
    )
    
    historical_context: str = Field(
        description="历史交锋摘要"
    )
    
    confidence_score: float = Field(
        description="置信度评分（0-1）",
        ge=0.0,
        le=1.0
    )
    
    prediction_summary: str = Field(
        description="预测结果摘要（不得修改）"
    )
```

### MatchExplainerAgent 类

#### 初始化

```python
agent = MatchExplainerAgent(
    model_name="gpt-3.5-turbo",  # 或 "gpt-4"
    openai_api_key="your-api-key",  # OpenAI API 密钥
    use_local_model=False  # 是否使用本地模型
)
```

#### 主要方法

##### 1. `explain_match()`

生成单场比赛的解释报告。

```python
explanation = agent.explain_match(
    team_a_name="Brazil",
    team_a_elo=2100.0,
    team_b_name="Germany",
    team_b_elo=1950.0,
    score_a=2,
    score_b=1,
    winner_name="Brazil",
    adjustment=0.05,      # 注意力网络调整系数
    base_win_prob=0.65    # 基础胜率
)
```

**返回值：** `MatchExplanation` 对象

##### 2. `batch_explain()`

批量解释多场比赛。

```python
matches = [
    {
        "team_a_name": "Argentina",
        "team_a_elo": 2050.0,
        "team_b_name": "France",
        "team_b_elo": 2000.0,
        "score_a": 3,
        "score_b": 2,
        "winner_name": "Argentina"
    },
    # ... 更多比赛
]

explanations = agent.batch_explain(matches)
```

---

## 💻 使用示例

### 示例 1：基本用法

```python
from app.services.llm_explainer import MatchExplainerAgent

# 初始化 Agent
agent = MatchExplainerAgent(
    model_name="gpt-3.5-turbo",
    openai_api_key="sk-your-key"
)

# 生成解释
explanation = agent.explain_match(
    team_a_name="Brazil",
    team_a_elo=2100.0,
    team_b_name="Germany",
    team_b_elo=1950.0,
    score_a=2,
    score_b=1,
    winner_name="Brazil"
)

# 访问解释内容
print(f"战术分析:\n{explanation.tactical_analysis}")
print(f"\n关键球员:\n{explanation.key_player_impact}")
print(f"\n历史背景:\n{explanation.historical_context}")
print(f"\n置信度: {explanation.confidence_score:.2f}")
print(f"\n预测摘要: {explanation.prediction_summary}")
```

### 示例 2：与淘汰赛模拟器集成

```python
from app.services.tournament_sim import simulate_knockout_stage
from app.services.llm_explainer import MatchExplainerAgent

# 模拟淘汰赛
knockout_result = simulate_knockout_stage(...)

# 初始化解释 Agent
agent = MatchExplainerAgent(...)

# 为决赛生成解释
final_match = knockout_result["final"]["matches"][0]

explanation = agent.explain_match(
    team_a_name=final_match["team_a_name"],
    team_a_elo=final_match["team_a_elo"],
    team_b_name=final_match["team_b_name"],
    team_b_elo=final_match["team_b_elo"],
    score_a=final_match["score_a"],
    score_b=final_match["score_b"],
    winner_name=final_match["winner_name"]
)

print("=" * 70)
print(f"决赛解释报告: {final_match['team_a_name']} vs {final_match['team_b_name']}")
print("=" * 70)
print(f"\n【战术分析】\n{explanation.tactical_analysis}")
print(f"\n【关键球员】\n{explanation.key_player_impact}")
print(f"\n【历史背景】\n{explanation.historical_context}")
print(f"\n【置信度】{explanation.confidence_score:.2%}")
```

### 示例 3：使用工具函数

```python
from app.services.llm_explainer import (
    get_team_tactics,
    get_historical_record,
    search_tactical_database
)

# 查询球队战术
tactics = get_team_tactics.invoke({"team_name": "Brazil"})
print(tactics)

# 查询历史交锋
history = get_historical_record.invoke({
    "team_a": "Brazil",
    "team_b": "Germany"
})
print(history)

# 搜索战术数据库
results = search_tactical_database.invoke({
    "query": "Brazil attacking style"
})
print(results)
```

---

## 🔧 LangChain Tools（MCP 风格）

### Tool 1: get_team_tactics

**功能**：获取指定球队的战术风格和特点

**输入**：
```json
{"team_name": "Brazil"}
```

**输出**：
```
【Brazil 战术档案】
战术风格：技术流进攻足球，擅长边路突破和快速反击
优势：个人技术出色, 进攻创造力强, 定位球威胁大
劣势：防守定位球不稳定, 有时过于依赖个人能力
关键球员：内马尔, 维尼修斯, 阿利松
历史备注：5次世界杯冠军，拥有最辉煌的世界杯历史
```

### Tool 2: get_historical_record

**功能**：查询两队的历史交锋记录

**输入**：
```json
{"team_a": "Brazil", "team_b": "Germany"}
```

**输出**：
```
【Brazil vs Germany 历史交锋】
1. 2014年世界杯半决赛：德国 7-1 巴西（米内罗惨案）
2. 历史上巴西对德国稍占优势，但2014年的失利是巴西足球的痛点
3. 两队共交手21次，巴西12胜5平4负
```

### Tool 3: search_tactical_database

**功能**：在战术数据库中搜索相关信息

**输入**：
```json
{"query": "Brazil tactics"}
```

**输出**：
```
【战术数据库搜索结果】（查询：'Brazil tactics'）
1. [Brazil] Brazil的战术风格：技术流进攻足球，擅长边路突破和快速反击 (相关度: 0.90)
```

---

## ⚠️ 重要约束

### 1. 不可修改预测结果

Prompt 中明确告诫 LLM：
> "你只能解释传入的比分和胜负状态，绝对不能修改或推翻这些结果"

这是为了确保解释的一致性，避免 LLM 质疑底层概率引擎的预测。

### 2. 必须使用工具

LLM 被要求在使用工具查询战术信息和历史记录后再生成解释，确保解释基于事实而非臆测。

### 3. 结构化输出

所有输出必须符合 `MatchExplanation` Schema，通过 Pydantic 验证确保格式一致性。

---

## 🚀 高级配置

### 使用本地模型（Ollama）

```python
agent = MatchExplainerAgent(
    use_local_model=True  # 使用本地 Ollama 服务
)
```

需要先安装并启动 Ollama：
```bash
ollama pull llama2
ollama serve
```

### 自定义战术知识库

可以扩展 `TacticalKnowledgeBase` 类，添加更多球队数据或连接真实的 ChromaDB：

```python
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

class RealChromaKB:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings()
        self.db = Chroma(
            collection_name="tactical_knowledge",
            embedding_function=self.embeddings,
            persist_directory="./chroma_db"
        )
    
    def search(self, query: str, k: int = 5):
        results = self.db.similarity_search(query, k=k)
        return results
```

---

## 📊 输出示例

```
======================================================================
决赛解释报告: Brazil vs Belgium
======================================================================

【战术分析】
巴西队凭借技术流进攻足球的优势，通过边路突破和快速反击有效克制了比利时队的实用主义战术。巴西队在控球率和进攻创造力上的优势使得他们能够主导比赛节奏，而比利时队虽然身体对抗能力强，但在面对巴西队细腻的配合时显得办法不多。

【关键球员】
内马尔的组织能力和维尼修斯的边路突破是巴西队获胜的关键。内马尔在中场的穿针引线为前锋线创造了多次机会，而维尼修斯在左路的突破直接导致了第一个进球。相比之下，比利时队的德布劳内虽然表现积极，但缺乏足够的支持。

【历史背景】
两队在历史上交手不多，但巴西队心理优势明显。本场比赛延续了巴西队在对阵欧洲球队时的技术优势传统。

【置信度】85.00%

【预测摘要】
Brazil 2:1 Belgium
```

---

## 📝 总结

`MatchExplainerAgent` 提供了：
- ✅ 强校验的结构化输出
- ✅ 工具化的 MCP 风格接口
- ✅ 明确的约束机制
- ✅ 与现有系统的无缝集成
- ✅ 可扩展的知识库架构

让冷冰冰的比分预测变得有"灵魂"，为用户提供专业的战术分析解释！
