# Streamlit 调试面板使用指南

## 📋 概述

`debug_dashboard.py` 是一个基于 Streamlit 的交互式调试面板，用于可视化展示 FastAPI 世界杯预测服务的运行结果。它提供了直观的用户界面来控制和监控预测系统。

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install streamlit>=1.30.0 requests>=2.31.0
```

或重新安装所有依赖：

```bash
pip install -r requirements.txt
```

### 2. 启动 FastAPI 服务

在第一个终端窗口中：

```bash
uvicorn main:app --reload
```

确保服务运行在 `http://localhost:8000`

### 3. 启动 Streamlit 面板

在第二个终端窗口中：

```bash
streamlit run debug_dashboard.py
```

浏览器会自动打开 `http://localhost:8501`

---

## 🎨 界面布局

### 侧边栏（控制面板）

#### 🔗 API 配置
- **API 基础 URL**: 设置 FastAPI 服务的地址（默认: `http://localhost:8000/api/v1`）

#### 🎲 模拟参数
- **使用随机种子**: 勾选后可以使用固定种子复现结果
  - **随机种子**: 输入 0-999999 的整数（默认: 42）
- **启用注意力网络调整**: 使用 PyTorch 模型进行特征加权（默认: 开启）
- **生成 LLM 解释**: 为决赛生成战术分析（需要 OpenAI API Key）

#### 🚀 执行模拟
- **运行模拟**按钮: 一键调用 `/api/v1/simulation/predict` 接口

#### 💾 缓存管理
- **清除缓存**按钮: 删除上次运行的结果并刷新页面

#### ℹ️ 状态信息
- 显示是否有模拟结果和上次运行时间

---

### 主页面（三个 Tab）

#### 📊 Tab 1: Elo 排名表

展示所有 48 支球队的详细信息：

| 列名 | 说明 |
|------|------|
| 排名 | 按 Elo 评分排序 |
| 球队名称 | 球队全名 |
| 小组 | 所属小组（A-L） |
| Elo 评分 | 当前 Elo 评级 |
| 球员身价(百万€) | 核心球员总身价 |
| 近期胜率 | 最近比赛胜率 |
| 伤病率 | 主力球员伤病比例 |

**统计卡片**：
- 球队总数
- 平均 Elo 评分
- 最高 Elo 评分

---

#### 🔍 Tab 2: 预测结果 JSON

展示完整的 API 响应数据：

**关键指标卡片**：
- 冠军队伍
- 亚军队伍
- 决赛比分
- 总比赛场次

**完整响应结构**：
- 语法高亮的 JSON 代码块
- 可滚动查看所有字段
- 提供下载按钮保存为 `.json` 文件

**JSON 结构示例**：
```json
{
  "status": "success",
  "tournament_winner_id": 1,
  "tournament_winner_name": "Brazil",
  "runner_up_id": 5,
  "runner_up_name": "France",
  "final_score": "2:1",
  "group_results": [...],
  "knockout_results": [...],
  "final_explanation": {...},
  "total_matches": 64,
  "simulation_seed": 42,
  "attention_adjustment_enabled": true
}
```

---

#### 🧠 Tab 3: LLM 解释验证

展示 AI 生成的战术分析：

**置信度仪表盘**：
- 显示解释的可信程度（0-100%）

**战术相克分析**：
- 两队战术风格的克制关系
- 高位逼抢 vs 传控体系的对抗
- 阵型优势和劣势分析

**关键球员影响**：
- 核心球员的表现分析
- 决定性作用描述
- 个人能力对比赛的影响

**历史交锋摘要**：
- 两队历史交手记录
- 心理优势分析
- 经典战役回顾

**预测结果摘要**：
- 最终比分和胜负状态
- 绿色高亮显示框

---

## 🛠️ 功能特性

### 1. 交互式控制

- ✅ 实时调整模拟参数
- ✅ 一键触发完整模拟
- ✅ 动态显示加载状态

### 2. 结果缓存

- ✅ Session State 存储上次结果
- ✅ 避免重复调用 API
- ✅ 手动清除缓存机制

### 3. 错误处理

- ✅ API 连接失败提示
- ✅ 请求超时处理
- ✅ 友好的错误消息

### 4. 响应式设计

- ✅ 宽屏布局优化
- ✅ 自适应表格宽度
- ✅ 流畅的 UI 交互

---

## 📝 使用场景

### 场景 1: 调试预测算法

1. 设置固定随机种子（如 42）
2. 启用注意力网络
3. 运行模拟
4. 在 JSON Tab 中查看详细数据结构
5. 分析小组赛和淘汰赛结果

### 场景 2: 测试 LLM 解释质量

1. 勾选"生成 LLM 解释"
2. 确保已配置 OpenAI API Key
3. 运行模拟
4. 切换到 LLM 解释 Tab
5. 评估战术分析的准确性和可读性

### 场景 3: 对比不同参数的影响

1. 第一次运行：seed=42, 启用注意力
2. 记录结果
3. 第二次运行：seed=42, 禁用注意力
4. 对比两次结果的差异

### 场景 4: 数据导出

1. 运行模拟获取结果
2. 在 JSON Tab 中点击"下载 JSON 文件"
3. 保存为本地文件用于后续分析

---

## 🎯 最佳实践

### 性能优化

1. **关闭不必要的功能**
   - 如果不需要 LLM 解释，请关闭该选项以加快速度
   - 调试算法时可以禁用注意力网络

2. **使用固定种子**
   - 开发阶段使用固定种子便于复现问题
   - 测试阶段可以尝试不同种子验证稳定性

3. **合理设置超时**
   - 默认超时时间为 120 秒
   - 如需更长时间可适当调整代码

### 调试技巧

1. **检查 API 连接**
   ```python
   # 在浏览器中访问
   http://localhost:8000/docs
   ```

2. **查看控制台日志**
   - FastAPI 服务端会输出详细日志
   - Streamlit 终端会显示请求状态

3. **验证数据格式**
   - 在 JSON Tab 中检查响应结构
   - 确保所有必填字段都存在

---

## 🐛 常见问题

### Q1: 无法连接到 API 服务

**症状**: 显示 "❌ 无法连接到 API 服务"

**解决方案**:
```bash
# 1. 确认 FastAPI 服务正在运行
uvicorn main:app --reload

# 2. 检查端口是否正确
# 默认端口为 8000

# 3. 在浏览器中测试
curl http://localhost:8000/health
```

---

### Q2: 请求超时

**症状**: 显示 "⏱️ 请求超时"

**解决方案**:
1. 关闭 LLM 解释功能（耗时较长）
2. 检查网络连接
3. 增加超时时间（修改 `call_simulation_api` 函数中的 `timeout` 参数）

---

### Q3: LLM 解释为空

**症状**: LLM 解释 Tab 显示警告

**解决方案**:
1. 确保勾选了"生成 LLM 解释"
2. 检查 `.env` 文件中是否配置了 `OPENAI_API_KEY`
3. 确认 OpenAI API 余额充足

---

### Q4: Streamlit 页面空白

**症状**: 浏览器打开后页面不显示内容

**解决方案**:
```bash
# 1. 重启 Streamlit 服务
streamlit run debug_dashboard.py

# 2. 清除浏览器缓存
# Ctrl+Shift+Delete (Chrome)

# 3. 检查 Streamlit 版本
pip show streamlit
```

---

## 🎨 自定义样式

### 修改主题颜色

编辑 `debug_dashboard.py` 中的 CSS：

```python
st.markdown("""
<style>
    .main-header {
        color: #1f77b4;  /* 修改为主色调 */
    }
    .metric-card {
        border-left: 4px solid #1f77b4;  /* 修改边框颜色 */
    }
</style>
""", unsafe_allow_html=True)
```

### 添加新的统计卡片

在 `display_prediction_json` 函数中添加：

```python
col5, col6 = st.columns(2)
with col5:
    st.metric("新指标1", value1)
with col6:
    st.metric("新指标2", value2)
```

---

## 📊 数据流图

```
用户操作 (侧边栏)
    ↓
设置参数 (种子、开关)
    ↓
点击"运行模拟"
    ↓
call_simulation_api()
    ↓
POST /api/v1/simulation/predict
    ↓
FastAPI 服务处理
    ├─ 小组赛模拟
    ├─ 淘汰赛模拟
    └─ LLM 解释生成
    ↓
返回 JSON 响应
    ↓
保存到 session_state
    ↓
刷新页面
    ↓
Tab 1: Elo 排名表 (DataFrame)
Tab 2: 预测结果 JSON (代码块)
Tab 3: LLM 解释验证 (格式化文本)
```

---

## 🔗 相关资源

- [Streamlit 官方文档](https://docs.streamlit.io/)
- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [API 使用指南](file://J:\project\worldcup\API_GUIDE.md)
- [快速开始指南](file://J:\project\worldcup\QUICKSTART.md)

---

## ✅ 总结

通过本调试面板，您可以：

1. ✅ 直观地查看所有球队的 Elo 排名
2. ✅ 交互式地调整模拟参数
3. ✅ 一键触发完整的蒙特卡洛模拟
4. ✅ 查看规范化的 JSON 响应结构
5. ✅ 验证 LLM 生成的战术解释质量
6. ✅ 导出结果数据进行离线分析

**让调试和测试变得更加简单高效！** 🎉
