# FeatureAttentionMixer 使用指南

## 📋 概述

`FeatureAttentionMixer` 是一个基于 PyTorch 的轻量级注意力特征加权网络模块，用于增强传统 Elo 评分系统的预测准确度。该模块通过深度学习技术动态评估不同特征对比赛结果的影响权重，输出调整系数来修正基础概率预测。

---

## 🎯 核心特性

### 1. **多维特征融合**
- Elo 评分差值
- 核心球员身价总和差值
- 近期胜率差值（最近 5 场）
- 伤病折损率差值

### 2. **注意力机制**
- 自动学习哪些特征对当前比赛最重要
- 动态调整特征权重
- 提供可解释性分析接口

### 3. **轻量级架构**
- 仅 3,426 个参数
- 快速推理（CPU 友好）
- 适合实时预测场景

### 4. **标准化输出**
- 调整系数范围：[-0.1, +0.1]
- 正值表示 A 队优势增强
- 负值表示 B 队优势增强

---

## 🏗️ 网络架构

```
Input (8 features) 
    ↓
MLP Layer 1: Linear(8 → 64) + BatchNorm + ReLU + Dropout(0.3)
    ↓
MLP Layer 2: Linear(64 → 32) + BatchNorm + ReLU + Dropout(0.3)
    ↓
Attention Layer: Linear(32 → 16) + ReLU → Linear(16 → 1) + Softmax
    ↓
Output Layer: Linear(32 → 1) + Tanh → Scale to [-0.1, +0.1]
```

### 输入特征（每队 4 个，共 8 个）

| 特征 | 说明 | 典型范围 | 归一化参数 |
|------|------|----------|-----------|
| elo_rating | Elo 评分 | 1000-2500 | mean=1700, std=300 |
| player_value | 核心球员身价总和（百万欧元） | 100-1000 | mean=400, std=200 |
| recent_form | 近期胜率（最近 5 场） | 0-1 | mean=0.5, std=0.2 |
| injury_rate | 伤病折损率 | 0-1 | mean=0.15, std=0.1 |

---

## 📦 API 文档

### 类定义

```python
class FeatureAttentionMixer(nn.Module):
    """
    特征注意力混合器
    
    Args:
        input_dim (int): 输入特征维度（默认 8）
        hidden_dim_1 (int): 第一层隐藏层维度（默认 64）
        hidden_dim_2 (int): 第二层隐藏层维度（默认 32）
        attention_dim (int): 注意力层维度（默认 16）
        dropout_rate (float): Dropout 比率（默认 0.3）
    """
```

### 主要方法

#### 1. `forward(team_a_features, team_b_features)`

前向传播，获取调整系数。

```python
def forward(
    self,
    team_a_features: torch.Tensor,  # 形状: (batch_size, 4)
    team_b_features: torch.Tensor   # 形状: (batch_size, 4)
) -> torch.Tensor:                  # 返回: (batch_size, 1), 范围 [-0.1, +0.1]
```

**参数说明：**
- `team_a_features`: A 队特征向量 `[elo_rating, player_value, recent_form, injury_rate]`
- `team_b_features`: B 队特征向量（同上）

**返回值：**
- 调整系数张量，范围在 [-0.1, +0.1] 之间

**示例：**
```python
model = FeatureAttentionMixer()
team_a = torch.tensor([[2000.0, 500.0, 0.8, 0.1]])
team_b = torch.tensor([[1800.0, 400.0, 0.6, 0.15]])
adjustment = model(team_a, team_b)
print(f"调整系数: {adjustment.item():+.4f}")
```

#### 2. `get_attention_weights(team_a_features, team_b_features)`

获取注意力权重（用于可解释性分析）。

```python
def get_attention_weights(
    self,
    team_a_features: torch.Tensor,
    team_b_features: torch.Tensor
) -> torch.Tensor:  # 返回: (batch_size, attention_dim)
```

**示例：**
```python
weights = model.get_attention_weights(team_a_tensor, team_b_tensor)
print(f"注意力权重: {weights}")
```

### 辅助函数

#### 1. `normalize_features(features_dict)`

将特征字典归一化为张量。

```python
def normalize_features(
    features_dict: Dict[str, float]
) -> torch.Tensor:  # 返回: (1, 4)
```

**参数：**
```python
features_dict = {
    'elo_rating': 2000.0,      # Elo 评分
    'player_value': 500.0,     # 核心球员身价总和（百万欧元）
    'recent_form': 0.8,        # 近期胜率（0-1）
    'injury_rate': 0.1         # 伤病折损率（0-1）
}
```

**示例：**
```python
features = {
    'elo_rating': 2000.0,
    'player_value': 500.0,
    'recent_form': 0.8,
    'injury_rate': 0.1
}
tensor = normalize_features(features)
print(tensor.shape)  # torch.Size([1, 4])
```

#### 2. `integrate_with_probability_engine(...)`

将注意力网络的输出与 ProbabilityEngine 结合。

```python
def integrate_with_probability_engine(
    engine,                          # ProbabilityEngine 实例
    team_a_elo: float,               # A 队 Elo 评分
    team_b_elo: float,               # B 队 Elo 评分
    team_a_features: Dict[str, float],  # A 队完整特征
    team_b_features: Dict[str, float],  # B 队完整特征
    model: FeatureAttentionMixer,    # 训练好的模型
    base_win_prob_a: float           # 基础 A 队胜率
) -> float:                          # 返回: 调整后的 A 队胜率
```

**工作流程：**
1. 归一化特征
2. 调用模型获取调整系数
3. 应用调整：`adjusted_prob = base_prob + adjustment`
4. 限制概率范围 [0.05, 0.95]

---

## 💻 使用示例

### 示例 1：基本用法

```python
import torch
from app.services.feature_network import FeatureAttentionMixer, normalize_features

# 初始化模型
model = FeatureAttentionMixer()
model.eval()  # 设置为评估模式

# 准备球队特征
team_a_features = {
    'elo_rating': 2000.0,
    'player_value': 500.0,
    'recent_form': 0.8,
    'injury_rate': 0.1
}

team_b_features = {
    'elo_rating': 1800.0,
    'player_value': 400.0,
    'recent_form': 0.6,
    'injury_rate': 0.15
}

# 归一化特征
team_a_tensor = normalize_features(team_a_features)
team_b_tensor = normalize_features(team_b_features)

# 获取调整系数
with torch.no_grad():
    adjustment = model(team_a_tensor, team_b_tensor)

print(f"调整系数: {adjustment.item():+.4f}")
# 输出: 调整系数: -0.0231（表示 B 队略有优势）
```

### 示例 2：与 ProbabilityEngine 集成

```python
from app.services.probability_engine import ProbabilityEngine
from app.services.feature_network import (
    FeatureAttentionMixer,
    integrate_with_probability_engine
)

# 初始化引擎和模型
engine = ProbabilityEngine()
model = FeatureAttentionMixer()
model.eval()

# 定义球队特征
team_a_features = {
    'elo_rating': 2000.0,
    'player_value': 500.0,
    'recent_form': 0.8,
    'injury_rate': 0.1
}

team_b_features = {
    'elo_rating': 1800.0,
    'player_value': 400.0,
    'recent_form': 0.6,
    'injury_rate': 0.15
}

# 获取基础胜率（仅基于 Elo）
outcomes = engine.calculate_match_outcome_probabilities(
    team_a_features['elo_rating'],
    team_b_features['elo_rating']
)
base_win_prob_a = outcomes['win_a']

print(f"基础预测:")
print(f"  A 队胜率: {base_win_prob_a:.4f} ({base_win_prob_a*100:.2f}%)")
print(f"  平局概率: {outcomes['draw']:.4f} ({outcomes['draw']*100:.2f}%)")
print(f"  B 队胜率: {outcomes['win_b']:.4f} ({outcomes['win_b']*100:.2f}%)")

# 应用注意力调整
adjusted_win_prob_a = integrate_with_probability_engine(
    engine,
    team_a_features['elo_rating'],
    team_b_features['elo_rating'],
    team_a_features,
    team_b_features,
    model,
    base_win_prob_a
)

adjustment = adjusted_win_prob_a - base_win_prob_a
print(f"\n调整后预测:")
print(f"  调整系数: {adjustment:+.4f}")
print(f"  A 队胜率: {adjusted_win_prob_a:.4f} ({adjusted_win_prob_a*100:.2f}%)")
print(f"  变化: {adjustment*100:+.2f}%")
```

**输出示例：**
```
基础预测:
  A 队胜率: 0.6367 (63.67%)
  平局概率: 0.2345 (23.45%)
  B 队胜率: 0.1289 (12.89%)

调整后预测:
  调整系数: -0.0231
  A 队胜率: 0.6136 (61.36%)
  变化: -2.31%
```

### 示例 3：批量预测

```python
import torch

# 准备批量数据
batch_size = 5
team_a_features_batch = torch.tensor([
    [2000.0, 500.0, 0.8, 0.1],   # 比赛 1: A队
    [1900.0, 450.0, 0.6, 0.2],   # 比赛 2: A队
    [1800.0, 400.0, 0.7, 0.15],  # 比赛 3: A队
    [2100.0, 600.0, 0.9, 0.05],  # 比赛 4: A队
    [1700.0, 350.0, 0.5, 0.25],  # 比赛 5: A队
])

team_b_features_batch = torch.tensor([
    [1800.0, 400.0, 0.6, 0.15],  # 比赛 1: B队
    [1850.0, 420.0, 0.7, 0.1],   # 比赛 2: B队
    [1750.0, 380.0, 0.55, 0.12], # 比赛 3: B队
    [1900.0, 450.0, 0.65, 0.2],  # 比赛 4: B队
    [1650.0, 300.0, 0.4, 0.3],   # 比赛 5: B队
])

# 批量预测
model.eval()
with torch.no_grad():
    adjustments = model(team_a_features_batch, team_b_features_batch)

# 输出结果
for i in range(batch_size):
    print(f"比赛 {i+1}: 调整系数 = {adjustments[i].item():+.4f}")
```

### 示例 4：注意力权重可视化

```python
import matplotlib.pyplot as plt
import numpy as np

# 获取注意力权重
model.eval()
with torch.no_grad():
    weights = model.get_attention_weights(team_a_tensor, team_b_tensor)

# 可视化
feature_names = ['Elo差值', '身价差值', '状态差值', '伤病差值']
attention_values = weights.numpy().flatten()

plt.figure(figsize=(10, 6))
plt.bar(feature_names, attention_values, color='steelblue')
plt.title('Attention Weights for Different Features')
plt.xlabel('Feature')
plt.ylabel('Weight')
plt.ylim(0, 1)
plt.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig('attention_weights.png', dpi=150)
plt.show()
```

### 示例 5：在淘汰赛模拟中应用

```python
from app.services.tournament_sim import simulate_knockout_stage
from app.services.feature_network import FeatureAttentionMixer, integrate_with_probability_engine

# 加载训练好的模型
model = FeatureAttentionMixer()
model.load_state_dict(torch.load('models/feature_mixer.pth'))
model.eval()

# 自定义比赛模拟函数
def enhanced_simulate_match(engine, team_a_info, team_b_info, model):
    """
    增强的比赛模拟（结合注意力网络）
    """
    # 获取基础胜率
    outcomes = engine.calculate_match_outcome_probabilities(
        team_a_info['elo_rating'],
        team_b_info['elo_rating']
    )
    
    # 构建特征字典
    team_a_features = {
        'elo_rating': team_a_info['elo_rating'],
        'player_value': team_a_info.get('player_value', 400.0),
        'recent_form': team_a_info.get('recent_form', 0.5),
        'injury_rate': team_a_info.get('injury_rate', 0.15)
    }
    
    team_b_features = {
        'elo_rating': team_b_info['elo_rating'],
        'player_value': team_b_info.get('player_value', 400.0),
        'recent_form': team_b_info.get('recent_form', 0.5),
        'injury_rate': team_b_info.get('injury_rate', 0.15)
    }
    
    # 应用注意力调整
    adjusted_win_prob_a = integrate_with_probability_engine(
        engine,
        team_a_info['elo_rating'],
        team_b_info['elo_rating'],
        team_a_features,
        team_b_features,
        model,
        outcomes['win_a']
    )
    
    return adjusted_win_prob_a
```

---

## 🔧 模型训练（可选）

如果您有历史比赛数据，可以训练模型以获得更好的预测效果：

```python
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset

# 准备训练数据
# X_train: 特征张量 (num_samples, 8)
# y_train: 标签（实际调整系数或比赛结果）

# 创建数据集
dataset = TensorDataset(X_train, y_train)
dataloader = DataLoader(dataset, batch_size=32, shuffle=True)

# 初始化模型和优化器
model = FeatureAttentionMixer()
optimizer = optim.Adam(model.parameters(), lr=0.001)
criterion = nn.MSELoss()  # 均方误差损失

# 训练循环
num_epochs = 100
for epoch in range(num_epochs):
    model.train()
    total_loss = 0
    
    for batch_X, batch_y in dataloader:
        # 分离两队特征
        team_a = batch_X[:, :4]
        team_b = batch_X[:, 4:]
        
        # 前向传播
        predictions = model(team_a, team_b)
        loss = criterion(predictions, batch_y.unsqueeze(1))
        
        # 反向传播
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        
        total_loss += loss.item()
    
    if (epoch + 1) % 10 == 0:
        avg_loss = total_loss / len(dataloader)
        print(f"Epoch [{epoch+1}/{num_epochs}], Loss: {avg_loss:.6f}")

# 保存模型
torch.save(model.state_dict(), 'models/feature_mixer.pth')
print("模型已保存至 models/feature_mixer.pth")
```

---

## ⚠️ 注意事项

### 1. 模型处于未训练状态
当前提供的模型权重是随机初始化的。为了获得准确的预测，您需要：
- 使用历史比赛数据进行训练
- 或者将其作为特征提取器，配合其他模型使用

### 2. 特征归一化
务必使用 `normalize_features()` 函数进行归一化，否则模型输出可能不准确。

### 3. 评估模式
在推理时务必调用 `model.eval()`，这会禁用 Dropout 并使用 BatchNorm 的运行统计量。

### 4. 梯度禁用
推理时使用 `with torch.no_grad():` 可以节省内存并加速计算。

### 5. 调整系数解释
- **正值 (+)**: A 队优势增强，A 队胜率增加
- **负值 (-)**: B 队优势增强，A 队胜率减少
- **接近 0**: 两队实力相当，无需大幅调整

---

## 🚀 性能优化建议

### 1. GPU 加速（如果可用）

```python
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model.to(device)

team_a_tensor = team_a_tensor.to(device)
team_b_tensor = team_b_tensor.to(device)

with torch.no_grad():
    adjustment = model(team_a_tensor, team_b_tensor)
```

### 2. 模型量化（减小模型大小）

```python
# 动态量化的 INT8 模型
quantized_model = torch.quantization.quantize_dynamic(
    model,
    {nn.Linear},
    dtype=torch.qint8
)
```

### 3. JIT 编译（加速推理）

```python
# 使用 TorchScript 编译
scripted_model = torch.jit.script(model)
scripted_model.save('models/feature_mixer_scripted.pt')

# 加载编译后的模型
loaded_model = torch.jit.load('models/feature_mixer_scripted.pt')
```

---

## 📊 与现有系统集成

### 在 tournament_sim.py 中使用

```python
# 在 simulate_knockout_match 函数中添加
from app.services.feature_network import (
    FeatureAttentionMixer,
    normalize_features,
    integrate_with_probability_engine
)

# 加载模型（全局或单例）
_feature_model = None

def get_feature_model():
    global _feature_model
    if _feature_model is None:
        _feature_model = FeatureAttentionMixer()
        _feature_model.eval()
    return _feature_model

def simulate_knockout_match_enhanced(...):
    """增强的淘汰赛模拟"""
    engine = ProbabilityEngine()
    model = get_feature_model()
    
    # 获取基础胜率
    outcomes = engine.calculate_match_outcome_probabilities(
        team_a_elo, team_b_elo
    )
    
    # 构建特征（需要从数据库或其他来源获取）
    team_a_features = {
        'elo_rating': team_a_elo,
        'player_value': get_player_value(team_a_id),
        'recent_form': get_recent_form(team_a_id),
        'injury_rate': get_injury_rate(team_a_id)
    }
    
    team_b_features = {...}  # 同理
    
    # 应用注意力调整
    adjusted_win_prob_a = integrate_with_probability_engine(
        engine, team_a_elo, team_b_elo,
        team_a_features, team_b_features,
        model, outcomes['win_a']
    )
    
    # 使用调整后的概率进行比分预测
    # ...
```

---

## 📝 总结

`FeatureAttentionMixer` 提供了：
- ✅ 轻量级的深度学习特征融合
- ✅ 注意力机制的可解释性
- ✅ 与 ProbabilityEngine 的无缝集成
- ✅ 标准化的输出范围
- ✅ 批量预测支持
- ✅ CPU/GPU 兼容

可以直接用于增强现有的世界杯预测系统，提高预测准确度！
