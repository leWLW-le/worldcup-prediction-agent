# FastAPI 路由与 Lifespan 管理使用指南

## 📋 概述

本指南介绍如何使用 FastAPI 的 lifespan 管理机制和完整的模拟预测 API。系统集成了 SQLite、PyTorch、ChromaDB 和 LLM Agent，提供端到端的世界杯预测服务。

---

## 🏗️ 架构设计

### 核心组件

1. **Lifespan Manager** ([main.py](file://J:\project\worldcup\main.py))
   - 应用启动时初始化所有服务
   - 应用关闭时清理资源
   - 管理全局状态（app.state）

2. **Simulation Router** ([simulation.py](file://J:\project\worldcup\app\api\simulation.py))
   - `/api/v1/simulation/predict`: 完整模拟接口
   - `/api/v1/simulation/health`: 健康检查

3. **Pydantic Models**
   - 严格的数据校验
   - 规范的 JSON 输出结构

---

## 🚀 Lifespan 管理

### 启动流程

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # === 启动阶段 ===
    
    # 1. 初始化 SQLite 数据库
    init_db()
    
    # 2. 加载 PyTorch 模型权重
    if weights_path.exists():
        feature_model = FeatureAttentionMixer()
        feature_model.load_state_dict(torch.load(weights_path))
        app.state.feature_model = feature_model
    
    # 3. 初始化 ChromaDB 和战术知识库
    kb = TacticalKnowledgeBase()
    app.state.tactical_kb = kb
    
    # 4. 初始化 LLM Explainer Agent
    agent = MatchExplainerAgent(...)
    app.state.explainer_agent = agent
    
    yield  # 应用运行期间
    
    # === 关闭阶段 ===
    
    # 保存模型状态
    torch.save(app.state.feature_model.state_dict(), ...)
    
    # 关闭数据库连接
    engine.dispose()
```

### 访问全局服务

在 API 路由中可以通过 `app.state` 访问全局服务：

```python
@router.post("/predict")
async def run_simulation(request: SimulationRequest, app_state: dict = Depends(...)):
    # 获取全局服务实例
    feature_model = app_state.feature_model
    tactical_kb = app_state.tactical_kb
    explainer_agent = app_state.explainer_agent
```

---

## 🎯 API 接口

### 1. 完整模拟接口

**端点**: `POST /api/v1/simulation/predict`

**请求体**:

```json
{
  "groups": [
    {
      "group_name": "Group A",
      "teams": [
        {
          "team_id": 1,
          "team_name": "Brazil",
          "elo_rating": 2100.0,
          "player_value": 600.0,
          "recent_form": 0.8,
          "injury_rate": 0.1
        },
        // ... 其他3支球队
      ]
    },
    // ... 其他11个小组
  ],
  "seed": 42,
  "enable_attention_adjustment": true,
  "generate_final_explanation": true
}
```

**响应结构**:

```json
{
  "status": "success",
  "tournament_winner_id": 1,
  "tournament_winner_name": "Brazil",
  "runner_up_id": 5,
  "runner_up_name": "France",
  "final_score": "2:1",
  
  "group_results": [
    {
      "group_name": "Group A",
      "standings": [
        {
          "rank": 1,
          "team_id": 1,
          "team_name": "Brazil",
          "played": 3,
          "wins": 3,
          "draws": 0,
          "losses": 0,
          "goals_for": 7,
          "goals_against": 2,
          "goal_difference": 5,
          "points": 9
        }
        // ... 其他排名
      ],
      "qualified_teams": [1, 2],
      "third_place_team": 3,
      "matches": [
        {
          "team_a_id": 1,
          "team_a_name": "Brazil",
          "team_b_id": 2,
          "team_b_name": "Germany",
          "score_a": 2,
          "score_b": 1,
          "winner_id": 1
        }
        // ... 其他比赛
      ]
    }
    // ... 其他11个小组
  ],
  
  "knockout_results": [
    {
      "round_name": "Round of 32",
      "team_a_id": 1,
      "team_a_name": "Brazil",
      "team_b_id": 32,
      "team_b_name": "Costa Rica",
      "score_a": 3,
      "score_b": 0,
      "winner_id": 1,
      "is_penalty_shootout": false,
      "explanation": "Strong offensive performance..."
    }
    // ... 其他淘汰赛
  ],
  
  "final_explanation": {
    "tactical_analysis": "巴西队通过边路传中和快速反击有效压制了德国队的中场控制...",
    "key_player_impact": "内马尔的个人突破和关键传球为球队创造了多次得分机会...",
    "historical_context": "两队在历史上共交手22次，巴西队以12胜6平4负占据优势...",
    "confidence_score": 0.85,
    "prediction_summary": "巴西 2:1 德国"
  },
  
  "total_matches": 64,
  "simulation_seed": 42,
  "attention_adjustment_enabled": true
}
```

### 2. 健康检查接口

**端点**: `GET /api/v1/simulation/health`

**响应**:

```json
{
  "status": "ok",
  "service": "simulation",
  "version": "1.0.0"
}
```

---

## 🔧 使用示例

### Python 客户端调用

```python
import requests
import json

# 构建请求数据
request_data = {
    "groups": [...],  # 12个小组数据
    "seed": 42,
    "enable_attention_adjustment": True,
    "generate_final_explanation": True
}

# 发送请求
response = requests.post(
    "http://localhost:8000/api/v1/simulation/predict",
    json=request_data,
    timeout=60
)

# 解析响应
result = response.json()
print(f"冠军: {result['tournament_winner_name']}")
print(f"决赛比分: {result['final_score']}")

# 查看 LLM 解释
if result['final_explanation']:
    explanation = result['final_explanation']
    print(f"\n战术分析: {explanation['tactical_analysis']}")
    print(f"关键球员: {explanation['key_player_impact']}")
    print(f"历史背景: {explanation['historical_context']}")
    print(f"置信度: {explanation['confidence_score']}")
```

### cURL 测试

```bash
curl -X POST "http://localhost:8000/api/v1/simulation/predict" \
  -H "Content-Type: application/json" \
  -d '{
    "groups": [...],
    "seed": 42,
    "enable_attention_adjustment": true,
    "generate_final_explanation": false
  }'
```

### 使用测试脚本

```bash
# 启动服务器
uvicorn main:app --reload

# 运行测试脚本
python test_api.py
```

---

## 📊 Pydantic 数据模型

### TeamInfo
```python
class TeamInfo(BaseModel):
    team_id: int                    # 球队ID
    team_name: str                  # 球队名称
    elo_rating: float               # Elo评分 (1000-2500)
    player_value: float             # 核心球员身价总和（百万欧元）
    recent_form: float              # 近期胜率 (0-1)
    injury_rate: float              # 伤病折损率 (0-1)
```

### GroupInfo
```python
class GroupInfo(BaseModel):
    group_name: str                 # 小组名称
    teams: List[TeamInfo]           # 4支球队 (min_items=4, max_items=4)
```

### SimulationRequest
```python
class SimulationRequest(BaseModel):
    groups: List[GroupInfo]         # 12个小组 (min_items=12, max_items=12)
    seed: Optional[int]             # 随机种子
    enable_attention_adjustment: bool  # 是否启用注意力调整
    generate_final_explanation: bool   # 是否生成LLM解释
```

### SimulationResponse
```python
class SimulationResponse(BaseModel):
    status: str                     # 状态
    tournament_winner_id: int       # 冠军队伍ID
    tournament_winner_name: str     # 冠军队伍名称
    runner_up_id: int               # 亚军队伍ID
    runner_up_name: str             # 亚军队伍名称
    final_score: str                # 决赛比分
    
    group_results: List[GroupStageResult]      # 小组赛结果
    knockout_results: List[KnockoutMatchResult] # 淘汰赛结果
    
    final_explanation: Optional[FinalExplanation]  # LLM解释
    
    total_matches: int              # 总比赛场次
    simulation_seed: Optional[int]  # 使用的随机种子
    attention_adjustment_enabled: bool  # 是否启用注意力调整
```

---

## 🛠️ 配置说明

### 环境变量

在 `.env` 文件中配置：

```bash
# 应用配置
APP_NAME="World Cup Prediction API"
APP_VERSION="1.0.0"
DEBUG=True

# 服务器配置
HOST=0.0.0.0
PORT=8000

# 数据库配置
DATABASE_URL="sqlite:///./worldcup.db"

# OpenAI API 配置（用于 LLM 解释器）
OPENAI_API_KEY="sk-your-api-key-here"
```

### 模型权重文件

将训练好的 PyTorch 模型权重放置在：

```
models/feature_mixer.pth
```

如果文件不存在，系统将使用未训练的模型。

---

## 🔄 工作流程

### 完整模拟流程

```
1. 接收请求
   ↓
2. 验证输入数据（Pydantic）
   ↓
3. 小组赛阶段
   ├─ 每组4队单循环
   ├─ 每场比赛调用 ProbabilityEngine
   ├─ 可选：使用 FeatureAttentionMixer 调整
   └─ 前两名晋级 + 部分第三名
   ↓
4. 淘汰赛阶段
   ├─ 32强 → 16强 → 8强 → 半决赛 → 决赛
   └─ 每场比赛调用概率引擎
   ↓
5. 生成决赛解释（可选）
   ├─ 调用 MatchExplainerAgent
   ├─ 检索战术知识库（ChromaDB）
   └─ 生成结构化解释（Pydantic Schema）
   ↓
6. 构建响应（Pydantic 校验）
   ↓
7. 返回规范化的 JSON
```

---

## 🧪 测试

### 单元测试

```python
# 测试 Pydantic 模型校验
def test_team_info_validation():
    # 有效的数据
    team = TeamInfo(
        team_id=1,
        team_name="Brazil",
        elo_rating=2100.0,
        player_value=600.0,
        recent_form=0.8,
        injury_rate=0.1
    )
    assert team.team_name == "Brazil"
    
    # 无效的数据（elo_rating 超出范围）
    with pytest.raises(ValidationError):
        TeamInfo(
            team_id=1,
            team_name="Brazil",
            elo_rating=3000.0,  # 超出范围
            player_value=600.0,
            recent_form=0.8,
            injury_rate=0.1
        )
```

### 集成测试

```bash
# 运行完整测试脚本
python test_api.py
```

---

## 🚨 错误处理

### 常见错误

1. **Validation Error (422)**
   - 原因：请求数据不符合 Pydantic 模型要求
   - 解决：检查字段类型、范围和必填项

2. **Connection Error**
   - 原因：服务器未启动
   - 解决：运行 `uvicorn main:app --reload`

3. **Timeout Error**
   - 原因：模拟计算时间过长
   - 解决：增加 timeout 参数或优化算法

### 错误响应格式

```json
{
  "detail": [
    {
      "loc": ["body", "groups", 0, "teams"],
      "msg": "ensure this value has at least 4 items",
      "type": "value_error.list.min_items"
    }
  ]
}
```

---

## 📈 性能优化

### 建议配置

- **CPU**: 4+ cores
- **RAM**: 8GB+
- **Storage**: SSD 推荐

### 优化策略

1. **使用随机种子复现结果**
   ```python
   "seed": 42  # 固定种子可复现相同结果
   ```

2. **禁用不必要的功能**
   ```python
   "enable_attention_adjustment": false  # 跳过注意力网络
   "generate_final_explanation": false   # 跳过 LLM 解释
   ```

3. **批量处理**
   - 避免频繁调用 API
   - 一次请求获取完整结果

---

## 🔐 安全注意事项

1. **生产环境配置**
   - 限制 CORS 允许的域名
   - 使用 HTTPS
   - 添加认证机制

2. **API Key 管理**
   - 不要硬编码 OpenAI API Key
   - 使用环境变量或密钥管理服务

3. **输入验证**
   - Pydantic 已提供基础验证
   - 额外业务逻辑验证应在服务层实现

---

## 📚 相关文档

- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [Pydantic 文档](https://docs.pydantic.dev/)
- [Feature Network 使用指南](file://J:\project\worldcup\FEATURE_NETWORK_GUIDE.md)
- [LLM Explainer 使用指南](file://J:\project\worldcup\LLM_EXPLAINER_GUIDE.md)

---

## ✅ 总结

通过本指南，您应该能够：

1. ✅ 理解 lifespan 管理机制
2. ✅ 使用 `/api/v1/simulation/predict` 接口
3. ✅ 构建符合 Pydantic 校验的请求
4. ✅ 解析规范化的 JSON 响应
5. ✅ 集成注意力网络和 LLM 解释器
6. ✅ 运行测试脚本验证功能

所有返回值均通过 Pydantic 严格校验，确保前端能收到极度规范的 JSON 树状结构！
