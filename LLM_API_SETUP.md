# LLM API 配置指南

本文档介绍如何配置和接入不同的 LLM（大语言模型）API。

## 📋 支持的 LLM 提供商

### 1. OpenAI（推荐）

**适用场景**：有 OpenAI API Key，追求最佳效果

**配置步骤**：

1. 获取 API Key：访问 https://platform.openai.com/api-keys
2. 编辑 `.env` 文件：
   ```env
   OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   OPENAI_BASE_URL=https://api.openai.com/v1
   OPENAI_MODEL=gpt-3.5-turbo
   USE_LOCAL_MODEL=false
   ```

**推荐模型**：
- `gpt-3.5-turbo` - 性价比高，速度快
- `gpt-4` - 效果更好，成本较高
- `gpt-4o` - 最新多模态模型

---

### 2. 智谱 AI (GLM)

**适用场景**：国内用户，需要中文支持

**配置步骤**：

1. 注册账号：访问 https://open.bigmodel.cn/
2. 获取 API Key
3. 编辑 `.env` 文件：
   ```env
   OPENAI_API_KEY=your-zhipu-api-key
   OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
   OPENAI_MODEL=glm-4
   USE_LOCAL_MODEL=false
   ```

**推荐模型**：
- `glm-4` - 最新版本，性能优秀
- `glm-4-flash` - 快速响应版本

---

### 3. 阿里云通义千问

**适用场景**：阿里云用户，企业级应用

**配置步骤**：

1. 开通服务：访问 https://dashscope.aliyun.com/
2. 获取 API Key
3. 编辑 `.env` 文件：
   ```env
   OPENAI_API_KEY=your-dashscope-api-key
   OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
   OPENAI_MODEL=qwen-plus
   USE_LOCAL_MODEL=false
   ```

**推荐模型**：
- `qwen-plus` - 平衡性能和成本
- `qwen-max` - 最强性能
- `qwen-turbo` - 最快速度

---

### 4. 本地 Ollama

**适用场景**：无网络环境、数据隐私要求高、免费使用

**配置步骤**：

1. 安装 Ollama：访问 https://ollama.ai/
2. 下载模型：
   ```bash
   ollama pull llama2
   # 或
   ollama pull qwen2:7b
   # 或
   ollama pull glm4
   ```
3. 启动 Ollama 服务（默认运行在 http://localhost:11434）
4. 编辑 `.env` 文件：
   ```env
   USE_LOCAL_MODEL=true
   LOCAL_MODEL_URL=http://localhost:11434
   LOCAL_MODEL_NAME=llama2
   OPENAI_API_KEY=""
   ```

**推荐模型**：
- `llama2` - Meta 官方模型
- `qwen2:7b` - 阿里通义千问开源版
- `glm4` - 智谱 GLM 开源版
- `mistral` - Mistral AI 模型

---

## 🔧 配置示例

### 完整 `.env` 文件示例（OpenAI）

```env
# LLM API 配置
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-3.5-turbo
USE_LOCAL_MODEL=false

# 应用配置
APP_NAME="World Cup Prediction API"
APP_VERSION="1.0.0"
DEBUG=True

# 服务器配置
HOST=0.0.0.0
PORT=8000

# 数据库配置
DATABASE_URL="sqlite:///./worldcup.db"
```

### 完整 `.env` 文件示例（智谱 AI）

```env
# LLM API 配置
OPENAI_API_KEY=your-zhipu-api-key
OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
OPENAI_MODEL=glm-4
USE_LOCAL_MODEL=false

# 应用配置
APP_NAME="World Cup Prediction API"
APP_VERSION="1.0.0"
DEBUG=True

# 服务器配置
HOST=0.0.0.0
PORT=8000

# 数据库配置
DATABASE_URL="sqlite:///./worldcup.db"
```

### 完整 `.env` 文件示例（本地 Ollama）

```env
# LLM API 配置
USE_LOCAL_MODEL=true
LOCAL_MODEL_URL=http://localhost:11434
LOCAL_MODEL_NAME=qwen2:7b
OPENAI_API_KEY=""

# 应用配置
APP_NAME="World Cup Prediction API"
APP_VERSION="1.0.0"
DEBUG=True

# 服务器配置
HOST=0.0.0.0
PORT=8000

# 数据库配置
DATABASE_URL="sqlite:///./worldcup.db"
```

---

## 🚀 重启服务使配置生效

修改 `.env` 文件后，需要重启 FastAPI 服务：

```bash
# 停止当前服务（Ctrl+C）

# 重新启动
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

启动日志会显示使用的模型：
```
☁️  Using cloud model: gpt-3.5-turbo
✅ LLM Explainer Agent initialized
```

或
```
📡 Using local model: llama2
✅ LLM Explainer Agent initialized
```

---

## 🧪 测试 LLM 功能

### 方法 1：通过 Streamlit 面板

1. 打开 http://localhost:8501
2. 在侧边栏勾选 **"生成 LLM 解释"**
3. 点击 **"运行模拟"**
4. 切换到 **"LLM 解释验证"** Tab 查看结果

### 方法 2：通过 API 直接调用

```python
import requests

request_data = {
    "groups": [...],  # 12个小组数据
    "seed": 42,
    "enable_attention_adjustment": True,
    "generate_final_explanation": True  # 启用 LLM 解释
}

response = requests.post(
    "http://localhost:8000/api/v1/simulation/predict",
    json=request_data,
    timeout=120
)

result = response.json()
print(result["final_explanation"])
```

---

## ⚠️ 常见问题

### Q1: 提示 "LLM Agent initialization skipped"

**原因**：API Key 无效或未配置

**解决方案**：
1. 检查 `.env` 文件中 `OPENAI_API_KEY` 是否正确
2. 确保没有多余的空格或引号
3. 重启服务

### Q2: 调用超时或失败

**原因**：网络连接问题或 API 配额不足

**解决方案**：
1. 检查网络连接
2. 确认 API Key 余额充足
3. 尝试切换其他模型提供商

### Q3: 本地模型响应慢

**原因**：本地硬件资源有限

**解决方案**：
1. 使用较小的模型（如 7B 参数）
2. 增加系统内存
3. 考虑使用 GPU 加速

### Q4: 中文输出质量不佳

**原因**：某些模型对中文支持不够好

**解决方案**：
1. 切换到智谱 GLM 或通义千问
2. 使用 GPT-4 而非 GPT-3.5

---

## 💰 成本参考

| 提供商 | 模型 | 输入价格 | 输出价格 | 备注 |
|--------|------|----------|----------|------|
| OpenAI | gpt-3.5-turbo | $0.0005/1K tokens | $0.0015/1K tokens | 性价比高 |
| OpenAI | gpt-4 | $0.03/1K tokens | $0.06/1K tokens | 效果最好 |
| 智谱 AI | glm-4 | ¥0.1/1K tokens | ¥0.1/1K tokens | 中文友好 |
| 阿里云 | qwen-plus | ¥0.004/1K tokens | ¥0.012/1K tokens | 企业级 |
| Ollama | llama2 | 免费 | 免费 | 需本地硬件 |

*注：以上价格为参考值，实际以官方为准*

---

## 📚 相关文档

- [OpenAI API 文档](https://platform.openai.com/docs)
- [智谱 AI 文档](https://open.bigmodel.cn/dev/api)
- [通义千问文档](https://help.aliyun.com/zh/dashscope/)
- [Ollama 文档](https://ollama.ai/docs)
- [LangChain 文档](https://python.langchain.com/docs/get_started/introduction)

---

## ✨ 总结

本项目支持多种 LLM 提供商，你可以根据需求选择：

- **追求效果** → OpenAI GPT-4
- **性价比** → OpenAI GPT-3.5 或 智谱 GLM-4
- **中文支持** → 智谱 GLM 或 通义千问
- **数据隐私/免费** → 本地 Ollama

配置完成后，即可在 Streamlit 面板中体验完整的 LLM 战术解释功能！⚽🏆
