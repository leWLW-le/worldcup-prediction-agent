# 2026 世界杯 48 队小组赛模拟器使用指南

## 概述

`tournament_sim.py` 实现了 2026 年世界杯 48 队赛制的小组赛模拟功能。该模块严格按照 FIFA 官方规则进行比赛模拟和排名计算。

## 核心功能

### 1. 小组赛模拟

- **12 个小组**，每组 4 支球队
- **单循环赛制**：每两队之间进行一场比赛
- **调用 ProbabilityEngine** 获取基于 Elo 评分的比赛结果

### 2. 积分规则

- **胜**: 3 分
- **平**: 1 分
- **负**: 0 分

### 3. 排名规则（优先级从高到低）

1. **积分** (Points)
2. **净胜球** (Goal Difference = 进球数 - 失球数)
3. **总进球数** (Goals For)
4. **相互交锋战绩** (Head-to-Head Record)
   - 交锋积分
   - 交锋净胜球
   - 交锋进球数

### 4. 晋级规则

- **前两名直接晋级**：每个小组的前 2 名球队（共 24 支）
- **最佳第三名**：从 12 个小组的第三名中选出成绩最好的 8 支
- **总计 32 支球队**晋级淘汰赛阶段

## API 使用

### 基本用法

```python
from app.services.tournament_sim import simulate_group_stage

# 定义 12 个小组的数据
# 格式：[(team_id, team_name, elo_rating), ...]
groups = [
    # Group A
    [
        (1, "Brazil", 2100.0),
        (2, "Germany", 2000.0),
        (3, "Japan", 1800.0),
        (4, "Cameroon", 1600.0)
    ],
    # Group B
    [
        (5, "Argentina", 2050.0),
        (6, "Spain", 1950.0),
        (7, "Mexico", 1750.0),
        (8, "Egypt", 1550.0)
    ],
    # ... 其他 10 个小组
]

# 运行模拟
result = simulate_group_stage(groups, seed=42)

# 获取晋级 32 强的球队 ID 列表
qualified_teams = result["qualified_32"]
print(f"晋级球队数量: {len(qualified_teams)}")  # 输出: 32
```

### 返回数据结构

```python
{
    "qualified_32": [1, 2, 5, 6, ...],  # 32 支晋级球队的 ID 列表
    
    "group_results": [
        {
            "group_name": "Group A",
            "standings": [
                {
                    "rank": 1,
                    "team_id": 1,
                    "team_name": "Brazil",
                    "played": 3,
                    "wins": 2,
                    "draws": 1,
                    "losses": 0,
                    "goals_for": 5,
                    "goals_against": 2,
                    "goal_difference": 3,
                    "points": 7
                },
                # ... 其他排名
            ],
            "qualified_teams": [1, 2],  # 晋级的两支球队 ID
            "third_place_team": 3       # 第三名球队 ID
        },
        # ... 其他 11 个小组
    ],
    
    "third_places_ranking": [
        {
            "rank": 1,
            "team_id": 29,
            "team_name": "Switzerland",
            "group_name": "Group H",
            "points": 5,
            "goal_difference": 1,
            "goals_for": 2
        },
        # ... 其他 7 个最佳第三名
    ]
}
```

## 完整示例

### 示例 1：基本模拟

```python
from app.services.tournament_sim import simulate_group_stage

# 创建 12 个小组
sample_groups = [
    [(1, "Brazil", 2100.0), (2, "Germany", 2000.0), 
     (3, "Japan", 1800.0), (4, "Cameroon", 1600.0)],
    [(5, "Argentina", 2050.0), (6, "Spain", 1950.0),
     (7, "Mexico", 1750.0), (8, "Egypt", 1550.0)],
    # ... 其他 10 个小组
]

# 运行模拟（使用固定种子保证可复现）
result = simulate_group_stage(sample_groups, seed=42)

# 查看各小组排名
for group_result in result["group_results"]:
    print(f"\n{group_result['group_name']}:")
    for standing in group_result["standings"]:
        print(f"  {standing['rank']}. {standing['team_name']} - "
              f"{standing['points']} pts, GD: {standing['goal_difference']}")
    
    qualified_names = [s["team_name"] for s in group_result["standings"][:2]]
    print(f"  晋级: {', '.join(qualified_names)}")

# 查看最佳第三名
print("\n8个最佳小组第三名:")
for ranking in result["third_places_ranking"]:
    print(f"  {ranking['rank']}. {ranking['team_name']} ({ranking['group_name']}) - "
          f"{ranking['points']} pts, GD: {ranking['goal_difference']}")
```

### 示例 2：与数据库集成

```python
from sqlalchemy.orm import Session
from app.db.database import get_db
from app import crud
from app.services.tournament_sim import simulate_group_stage

def run_world_cup_simulation(db: Session):
    """
    从数据库读取球队数据，运行世界杯小组赛模拟
    """
    # 从数据库获取所有球队
    all_teams = crud.get_teams(db, skip=0, limit=48)
    
    if len(all_teams) < 48:
        raise ValueError("需要至少 48 支球队")
    
    # 将球队分配到 12 个小组（这里简单按顺序分配）
    groups = []
    for i in range(12):
        group_start = i * 4
        group_end = group_start + 4
        group_teams = all_teams[group_start:group_end]
        
        # 转换为模拟器需要的格式
        groups.append([
            (team.id, team.name, team.current_elo)
            for team in group_teams
        ])
    
    # 运行模拟
    result = simulate_group_stage(groups)
    
    # 保存模拟结果到数据库
    simulation_log = {
        "qualified_32": result["qualified_32"],
        "group_results": result["group_results"],
        "third_places_ranking": result["third_places_ranking"]
    }
    
    # 假设第一个晋级的球队是冠军（简化处理）
    champion_team_id = result["qualified_32"][0]
    
    from app.models.pydantic_models import SimulationRecordCreate
    sim_record = SimulationRecordCreate(
        version="v1.0-group-stage",
        champion_team_id=champion_team_id,
        simulation_log=simulation_log
    )
    
    crud.create_simulation_record(db, sim_record)
    
    return result
```

### 示例 3：多次模拟统计

```python
from collections import Counter
from app.services.tournament_sim import simulate_group_stage

def monte_carlo_simulation(groups, num_simulations=1000):
    """
    运行蒙特卡洛模拟，统计各球队晋级概率
    
    Args:
        groups: 12 个小组的数据
        num_simulations: 模拟次数
        
    Returns:
        各球队的晋级统计
    """
    qualification_counts = Counter()
    
    for i in range(num_simulations):
        # 每次使用不同的随机种子
        result = simulate_group_stage(groups, seed=i)
        
        # 统计晋级球队
        for team_id in result["qualified_32"]:
            qualification_counts[team_id] += 1
    
    # 计算晋级概率
    qualification_probs = {
        team_id: count / num_simulations
        for team_id, count in qualification_counts.items()
    }
    
    return qualification_probs

# 使用示例
groups = [...]  # 定义小组数据
probs = monte_carlo_simulation(groups, num_simulations=1000)

# 打印晋级概率最高的 10 支球队
sorted_teams = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:10]
print("晋级概率最高的 10 支球队:")
for team_id, prob in sorted_teams:
    print(f"  球队 {team_id}: {prob*100:.2f}%")
```

## 排名算法详解

### 相互交锋战绩打破平局

当多支球队积分、净胜球、进球数完全相同时，使用相互交锋战绩作为 tiebreaker：

```python
# 假设有 3 支球队 A、B、C 积分相同
# 计算它们在彼此之间的交锋表现：

# A vs B: 2-1 (A 胜)
# A vs C: 1-1 (平)
# B vs C: 0-2 (C 胜)

# A 的交锋统计：
# - 交锋积分: 3 (胜) + 1 (平) = 4
# - 交锋净胜球: (2-1) + (1-1) = 1
# - 交锋进球: 2 + 1 = 3

# B 的交锋统计：
# - 交锋积分: 0 (负) + 0 (负) = 0
# - 交锋净胜球: (1-2) + (0-2) = -3
# - 交锋进球: 1 + 0 = 1

# C 的交锋统计：
# - 交锋积分: 1 (平) + 3 (胜) = 4
# - 交锋净胜球: (1-1) + (2-0) = 2
# - 交锋进球: 1 + 2 = 3

# 排名：A 和 C 并列（都是 4 分），但 C 净胜球更多，所以 C > A > B
```

### 最佳第三名选择

从 12 个小组的第三名中选出 8 个成绩最好的：

```python
# 排序规则（与小组排名相同）：
# 1. 积分（降序）
# 2. 净胜球（降序）
# 3. 总进球数（降序）

# 示例：
# Group A 第三名: 4 pts, GD: 0, GF: 3
# Group B 第三名: 3 pts, GD: -1, GF: 2
# Group C 第三名: 4 pts, GD: 1, GF: 4
# ...

# 排序后：
# 1. Group C 第三名 (4 pts, GD: 1, GF: 4)
# 2. Group A 第三名 (4 pts, GD: 0, GF: 3)
# 3. ... (继续排序)
# ...
# 8. Group X 第三名 (3 pts, GD: -1, GF: 2)

# 取前 8 名晋级
```

## 注意事项

1. **随机性**: 比赛结果基于概率引擎的随机采样，每次运行结果可能不同
   - 使用 `seed` 参数可以保证结果可复现
   
2. **Elo 评分**: 球队实力由 Elo 评分决定，评分越高获胜概率越大
   - 建议 Elo 范围: 1400-2200
   - 典型值: 巴西 2100, 德国 2000, 日本 1800, 喀麦隆 1600

3. **性能**: 单次模拟非常快（< 1 秒），适合蒙特卡洛模拟
   - 1000 次模拟约需 1-2 秒

4. **数据格式**: 输入必须是 12 个小组，每组恰好 4 支球队
   - 每支球队用元组表示: `(team_id, team_name, elo_rating)`

## 测试

运行内置测试：

```bash
python app/services/tournament_sim.py
```

预期输出：
```
======================================================================
2026 世界杯 48 队小组赛模拟器测试
======================================================================

开始模拟 12 个小组的比赛...
----------------------------------------------------------------------

各小组排名:
======================================================================

Group A:
----------------------------------------------------------------------
排名     球队                   场次     胜    平    负    进球     失球     净胜     积分
----------------------------------------------------------------------
1      Brazil               3      2    1    0    5      2      3      7
2      Germany              3      2    0    1    4      3      1      6
3      Japan                3      1    1    1    3      3      0      4
4      Cameroon             3      0    0    3    1      5      -4     0

晋级球队: ['Brazil', 'Germany']

... (其他小组)

8个最佳小组第三名:
======================================================================
排名     球队                   小组         积分     净胜球      进球
----------------------------------------------------------------------
1      Switzerland          Group H    5      1        2
2      Ukraine              Group I    4      1        3
...

晋级 32 强的球队名单:
======================================================================
共 32 支球队
----------------------------------------------------------------------
Group A: Brazil, Germany
Group B: Argentina, Spain
...

8个最佳第三名:
Switzerland (Group H), Ukraine (Group I), ...

======================================================================
模拟完成！
======================================================================
```

## 依赖

- `ProbabilityEngine`: 概率预测引擎（已实现）
- Python 3.10+
- 标准库：`random`, `typing`, `dataclasses`

## 扩展建议

1. **添加主场优势**: 在 `simulate_group_match` 中加入主场因素
2. **红黄牌影响**: 记录纪律处罚并在 tiebreaker 中使用
3. **公平竞赛积分**: 作为额外的 tiebreaker 规则
4. **实时 Elo 更新**: 在小组赛过程中动态更新 Elo 评分
5. **可视化**: 生成小组排名图表和晋级路线图

## 参考资料

- [FIFA 世界杯规则](https://www.fifa.com/who-we-are/news/fifa-world-cup-2026-format)
- [Elo 评分系统](https://en.wikipedia.org/wiki/Elo_rating_system)
- [足球比赛排名规则](https://en.wikipedia.org/wiki/Tiebreaker#Association_football)
