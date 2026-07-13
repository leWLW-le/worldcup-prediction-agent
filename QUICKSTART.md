# 快速启动指南

## 🚀 5分钟快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量（可选）

创建 `.env` 文件：

```bash
# OpenAI API Key（用于 LLM 解释器，如不需要可留空）
OPENAI_API_KEY=sk-your-api-key-here

# 其他配置（使用默认值即可）
APP_NAME="World Cup Prediction API"
DEBUG=True
HOST=0.0.0.0
PORT=8000
```

### 3. 启动服务器

```bash
uvicorn main:app --reload
```

访问 http://localhost:8000/docs 查看 API 文档。

### 4. 测试 API

```bash
python test_api.py
```

---

## 📋 完整示例

### 简单模拟（无注意力调整）

```python
import requests

request_data = {
    "groups": [...],  # 12个小组数据
    "seed": 42,
    "enable_attention_adjustment": False,
    "generate_final_explanation": False
}

response = requests.post(
    "http://localhost:8000/api/v1/simulation/predict",
    json=request_data
)

result = response.json()
print(f"冠军: {result['tournament_winner_name']}")
```

### 完整模拟（启用所有功能）

```python
import requests

request_data = {
    "groups": [...],  # 12个小组数据
    "seed": 42,
    "enable_attention_adjustment": True,   # 启用 PyTorch 注意力网络
    "generate_final_explanation": True     # 生成 LLM 战术解释
}

response = requests.post(
    "http://localhost:8000/api/v1/simulation/predict",
    json=request_data,
    timeout=60
)

result = response.json()

# 查看结果
print(f"🏆 冠军: {result['tournament_winner_name']}")
print(f"🥈 亚军: {result['runner_up_name']}")
print(f"⚽ 决赛比分: {result['final_score']}")

# 查看 LLM 解释
if result['final_explanation']:
    exp = result['final_explanation']
    print(f"\n📊 战术分析: {exp['tactical_analysis']}")
    print(f"⭐ 关键球员: {exp['key_player_impact']}")
    print(f"📜 历史背景: {exp['historical_context']}")
    print(f"🎯 置信度: {exp['confidence_score']}")
```

---

## 🔍 调试技巧

### 查看详细日志

启动时添加 `--log-level debug`:

```bash
uvicorn main:app --reload --log-level debug
```

### 检查服务状态

```bash
curl http://localhost:8000/health
```

### 查看 Swagger UI

浏览器访问: http://localhost:8000/docs

可以在线测试所有 API 接口！

---

## 🐛 常见问题

### Q: ModuleNotFoundError: No module named 'torch'

A: 安装 PyTorch:
```bash
pip install torch
```

### Q: Connection refused

A: 确保服务器已启动:
```bash
uvicorn main:app --reload
```

### Q: Validation Error

A: 检查请求数据是否符合 Pydantic 模型要求，特别是：
- 必须有 12 个小组
- 每个小组必须有 4 支球队
- elo_rating 范围: 1000-2500
- recent_form 和 injury_rate 范围: 0-1

---

## 📚 下一步

- [API 详细使用指南](file://J:\project\worldcup\API_GUIDE.md)
- [Feature Network 文档](file://J:\project\worldcup\FEATURE_NETWORK_GUIDE.md)
- [LLM Explainer 文档](file://J:\project\worldcup\LLM_EXPLAINER_GUIDE.md)
