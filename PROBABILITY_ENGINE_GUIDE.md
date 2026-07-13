# ProbabilityEngine 使用指南

## 概述

`ProbabilityEngine` 是一个独立的概率预测引擎，基于 Elo 评分系统和泊松分布模型进行足球比赛结果预测。该引擎不依赖大模型，专注于数学概率计算。

## 核心功能

### 1. Elo 评分更新

基于公式 `R_new = R_old + K × (W - W_e)` 更新球队积分。

#### 公式说明

- **期望胜率**: `W_e = 1 / (1 + 10^((R_B - R_A)/400))`
- **新评分**: `R_new = R_old + K × (W - W_e)`
- **K 因子**: 
  - 常规比赛: 30
  - 点球大战: 0（不改变评分）

#### 使用示例

```python
from app.services.probability_engine import ProbabilityEngine

engine = ProbabilityEngine()

# 场景 1: A 队获胜
old_a, old_b = 2000.0, 1800.0
new_a, new_b = engine.calculate_elo_update(old_a, old_b, 1.0)
print(f"A队新评分: {new_a:.2f}")  # 2007.21
print(f"B队新评分: {new_b:.2f}")  # 1792.79

# 场景 2: 平局
new_a, new_b = engine.calculate_elo_update(old_a, old_b, 0.5)
print(f"平局后A队评分: {new_a:.2f}")  # 1992.21
print(f"平局后B队评分: {new_b:.2f}")  # 1807.79

# 场景 3: 点球大战（不改变评分）
new_a, new_b = engine.calculate_elo_update(
    old_a, old_b, 1.0, is_penalty_shootout=True
)
print(f"点球大战后A队评分: {new_a:.2f}")  # 2000.00 (不变)
print(f"点球大战后B队评分: {new_b:.2f}")  # 1800.00 (不变)
```

### 2. 泊松比分预测

基于历史进球率和两队 Elo 分差计算预期进球数，使用泊松分布公式计算最可能的比分。

#### 公式说明

- **泊松概率**: `P(x) = (λ^x * e^-λ) / x!`
- **预期进球调整**: 
  - `λ_A = base_lambda_A × (1 + elo_weight × (Elo_A - Elo_B))`
  - `λ_B = base_lambda_B × (1 + elo_weight × (Elo_B - Elo_A))`

#### 使用示例

```python
from app.services.probability_engine import ProbabilityEngine

engine = ProbabilityEngine()

# 预测巴西 vs 德国的比分
brazil_elo = 2100.0
germany_elo = 2000.0

# 获取最可能的 3 种比分
top_scores = engine.predict_score_distribution(brazil_elo, germany_elo)

print("最可能的比分:")
for i, (goals_a, goals_b, prob) in enumerate(top_scores, 1):
    print(f"{i}. {goals_a}-{goals_b}: {prob*100:.2f}%")

# 输出示例:
# 1. 1-0: 16.23%
# 2. 2-0: 13.45%
# 3. 1-1: 11.87%
```

### 3. 比赛结果概率

计算胜、平、负三种结果的总体概率。

#### 使用示例

```python
from app.services.probability_engine import ProbabilityEngine

engine = ProbabilityEngine()

# 计算比赛结果概率
team_a_elo = 2000.0
team_b_elo = 1800.0

outcomes = engine.calculate_match_outcome_probabilities(team_a_elo, team_b_elo)

print(f"A队获胜: {outcomes['win_a']*100:.2f}%")
print(f"平局:     {outcomes['draw']*100:.2f}%")
print(f"B队获胜: {outcomes['win_b']*100:.2f}%")

# 输出示例:
# A队获胜: 63.67%
# 平局:     23.45%
# B队获胜: 12.89%
```

## 完整示例：模拟世界杯比赛

```python
from app.services.probability_engine import ProbabilityEngine
from app.db.database import get_db
from app import crud

def simulate_match(db, team_a_id: int, team_b_id: int):
    """
    模拟一场比赛并更新数据库
    
    Args:
        db: 数据库会话
        team_a_id: A队ID
        team_b_id: B队ID
    """
    engine = ProbabilityEngine()
    
    # 从数据库获取球队信息
    team_a = crud.get_team(db, team_a_id)
    team_b = crud.get_team(db, team_b_id)
    
    if not team_a or not team_b:
        raise ValueError("Teams not found")
    
    # 计算比赛结果概率
    outcomes = engine.calculate_match_outcome_probabilities(
        team_a.current_elo, 
        team_b.current_elo
    )
    
    # 根据概率随机决定比赛结果
    import random
    rand = random.random()
    
    if rand < outcomes['win_a']:
        result_a = 1.0  # A队获胜
        score_a, score_b = predict_score(engine, team_a.current_elo, team_b.current_elo)
    elif rand < outcomes['win_a'] + outcomes['draw']:
        result_a = 0.5  # 平局
        score_a = score_b = predict_draw_score(engine, team_a.current_elo, team_b.current_elo)
    else:
        result_a = 0.0  # B队获胜
        score_b, score_a = predict_score(engine, team_b.current_elo, team_a.current_elo)
    
    # 创建比赛记录
    match_data = MatchCreate(
        date=datetime.now(),
        team_a_id=team_a_id,
        team_b_id=team_b_id,
        score_a=score_a,
        score_b=score_b,
        is_knockout=True,
        tournament_type="World Cup 2026"
    )
    match = crud.create_match(db, match_data)
    
    # 更新球队 Elo 评分
    new_elo_a, new_elo_b = engine.calculate_elo_update(
        team_a.current_elo,
        team_b.current_elo,
        result_a,
        is_penalty_shootout=False
    )
    
    # 更新数据库中的 Elo 评分
    crud.update_team(db, team_a_id, TeamUpdate(current_elo=new_elo_a))
    crud.update_team(db, team_b_id, TeamUpdate(current_elo=new_elo_b))
    
    return {
        "match": match,
        "new_elo_a": new_elo_a,
        "new_elo_b": new_elo_b,
        "probabilities": outcomes
    }


def predict_score(engine, winner_elo, loser_elo):
    """预测获胜方的比分"""
    scores = engine.predict_score_distribution(winner_elo, loser_elo)
    # 选择第一个比分（最可能的）
    return scores[0][0], scores[0][1]


def predict_draw_score(engine, team_a_elo, team_b_elo):
    """预测平局比分"""
    scores = engine.predict_score_distribution(team_a_elo, team_b_elo)
    # 找到第一个平局比分
    for goals_a, goals_b, _ in scores:
        if goals_a == goals_b:
            return goals_a
    return 1  # 默认 1-1
```

## API 集成示例

```python
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.services.probability_engine import ProbabilityEngine
from app.models.pydantic_models import MatchPredictionResponse

app = FastAPI()

@app.get("/api/match/predict/{team_a_id}/{team_b_id}", response_model=MatchPredictionResponse)
def predict_match(
    team_a_id: int,
    team_b_id: int,
    db: Session = Depends(get_db)
):
    """
    预测两支球队之间的比赛结果
    
    Args:
        team_a_id: A队ID
        team_b_id: B队ID
        
    Returns:
        包含比分预测和胜平负概率的响应
    """
    engine = ProbabilityEngine()
    
    # 获取球队信息
    team_a = crud.get_team(db, team_a_id)
    team_b = crud.get_team(db, team_b_id)
    
    if not team_a or not team_b:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # 计算预测
    top_scores = engine.predict_score_distribution(
        team_a.current_elo, 
        team_b.current_elo
    )
    
    outcomes = engine.calculate_match_outcome_probabilities(
        team_a.current_elo,
        team_b.current_elo
    )
    
    return MatchPredictionResponse(
        team_a_name=team_a.name,
        team_b_name=team_b.name,
        team_a_elo=team_a.current_elo,
        team_b_elo=team_b.current_elo,
        predicted_scores=[
            {"score_a": a, "score_b": b, "probability": p}
            for a, b, p in top_scores
        ],
        win_probability_a=outcomes['win_a'],
        draw_probability=outcomes['draw'],
        win_probability_b=outcomes['win_b']
    )
```

## 参数调优建议

### Elo 更新参数

```python
class ProbabilityEngine:
    K_FACTOR = 30.0          # 标准比赛的 K 值
    PENALTY_K_FACTOR = 0.0   # 点球大战时使用的 K 因子
```

**调优建议**:
- **K_FACTOR**: 
  - 较大值（如 40）: 评分变化更快，适合短期赛事
  - 较小值（如 20）: 评分更稳定，适合长期排名
  - 推荐值: 30（FIFA 官方使用）

- **PENALTY_K_FACTOR**: 
  - 设为 0: 点球大战不影响 Elo（推荐）
  - 设为较小值（如 5）: 轻微影响 Elo

### 比分预测参数

```python
def predict_score_distribution(
    team_a_elo: float,
    team_b_elo: float,
    base_lambda_a: float = 1.2,      # A队基础预期进球率
    base_lambda_b: float = 1.0,      # B队基础预期进球率
    elo_weight: float = 0.002        # Elo分差影响权重
)
```

**调优建议**:
- **base_lambda_a/b**: 
  - 根据历史数据调整
  - 进攻型联赛可提高（如 1.5）
  - 防守型联赛可降低（如 0.8）

- **elo_weight**: 
  - 较大值（如 0.005）: Elo 分差影响更大
  - 较小值（如 0.001）: Elo 分差影响更小
  - 推荐值: 0.002

## 注意事项

1. **纯函数设计**: 所有方法都是纯函数，无副作用，可安全并发调用
2. **数值稳定性**: 使用对数计算避免阶乘溢出
3. **边界处理**: 自动处理 lambda=0、负数等边界情况
4. **类型注解**: 完整的 Python 3.10+ 类型注解
5. **Docstring**: 每个方法都有详细的文档字符串

## 性能优化

对于大规模蒙特卡洛模拟：

```python
import concurrent.futures
from app.services.probability_engine import ProbabilityEngine

def run_monte_carlo_simulation(num_simulations=10000):
    """运行蒙特卡洛模拟"""
    engine = ProbabilityEngine()
    
    # 并行化模拟
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(simulate_tournament, engine)
            for _ in range(num_simulations)
        ]
        
        results = [f.result() for f in futures]
    
    # 统计结果
    champion_counts = {}
    for result in results:
        champion = result['champion']
        champion_counts[champion] = champion_counts.get(champion, 0) + 1
    
    return champion_counts
```

## 测试

运行单元测试验证功能：

```bash
python test_probability_engine.py
```

预期输出：
```
======================================================================
运行 ProbabilityEngine 单元测试
======================================================================
test_consistency_between_methods ... ok
test_elo_expected_win_rate_calculation ... ok
...
----------------------------------------------------------------------
Ran 21 tests in 0.019s

OK
```

## 参考资料

- [Elo 评分系统](https://en.wikipedia.org/wiki/Elo_rating_system)
- [泊松分布](https://en.wikipedia.org/wiki/Poisson_distribution)
- [FIFA 世界排名算法](https://www.fifa.com/fifa-world-ranking/ranking-table/men/)
