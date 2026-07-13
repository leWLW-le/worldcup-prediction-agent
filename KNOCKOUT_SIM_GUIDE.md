# 2026 世界杯淘汰赛模拟器使用指南

## 📋 概述

`simulate_knockout_stage` 函数实现了完整的 32 强淘汰赛推演逻辑，包括从 1/16 决赛到决赛的所有轮次。该函数接收小组赛结果，按照 2026 世界杯标准的固定落位对阵表进行模拟，并返回完整的嵌套字典结构。

---

## 🎯 核心特性

### 1. **固定落位对阵表**
- 严格按照 2026 世界杯标准设计
- 32 支球队根据小组排名自动落位
- 上下半区划分明确，避免强队过早相遇

### 2. **递归节点遍历**
- 每轮比赛的胜者自动进入下一轮
- 支持动态追踪比赛进程
- 便于前端渲染赛程树

### 3. **点球大战机制**
- 常规时间平局时自动触发点球大战
- 随机决定点球胜负（简化处理）
- 标记 `is_penalty_shootout` 字段

### 4. **完整数据结构**
- 返回嵌套字典，包含所有轮次的详细信息
- 每场比赛记录比分、胜者、是否点球等信息
- 最终输出冠军信息

---

## 📦 API 文档

### 函数签名

```python
def simulate_knockout_stage(
    group_results: list[GroupResult],
    third_places_ranking: list[dict],
    seed: int | None = None
) -> KnockoutStageResult:
    """
    模拟淘汰赛阶段
    
    Args:
        group_results: 小组赛结果列表（来自 simulate_group_stage）
        third_places_ranking: 第三名排名列表
        seed: 随机种子（可选，用于复现结果）
        
    Returns:
        KnockoutStageResult: 完整的淘汰赛结果
    """
```

### 输入参数

#### 1. `group_results` (必需)
来自 `simulate_group_stage()` 的 `group_results` 字段，包含 12 个小组的详细结果。

```python
{
    "group_name": "Group A",
    "standings": [
        {
            "rank": 1,
            "team_id": 1,
            "team_name": "Brazil",
            "elo_rating": 2100.0,
            ...
        },
        ...
    ],
    "qualified_teams": [1, 2],
    "third_place_team": 3
}
```

#### 2. `third_places_ranking` (必需)
来自 `simulate_group_stage()` 的 `third_places_ranking` 字段，包含 8 个最佳第三名的排名。

```python
[
    {
        "rank": 1,
        "team_id": 29,
        "team_name": "Switzerland",
        "group_name": "Group H",
        "points": 5,
        "goal_difference": 1,
        "goals_for": 2,
        "elo_rating": 1780.0
    },
    ...
]
```

#### 3. `seed` (可选)
随机种子，用于保证结果可复现。

---

### 返回数据结构

```python
KnockoutStageResult = {
    "round_of_32": KnockoutRound,      # 1/16决赛
    "round_of_16": KnockoutRound,      # 1/8决赛
    "quarter_finals": KnockoutRound,   # 1/4决赛
    "semi_finals": KnockoutRound,      # 半决赛
    "final": KnockoutRound,            # 决赛
    "champion": dict                   # 冠军信息
}

KnockoutRound = {
    "round_name": str,                 # 轮次名称
    "matches": list[KnockoutMatch]     # 比赛列表
}

KnockoutMatch = {
    "round_name": str,                 # 轮次名称
    "match_number": int,               # 比赛编号
    "team_a_id": int,                  # A队ID
    "team_a_name": str,                # A队名称
    "team_a_elo": float,               # A队Elo评分
    "team_b_id": int,                  # B队ID
    "team_b_name": str,                # B队名称
    "team_b_elo": float,               # B队Elo评分
    "score_a": int,                    # A队进球数
    "score_b": int,                    # B队进球数
    "winner_id": int,                  # 胜者ID
    "winner_name": str,                # 胜者名称
    "is_penalty_shootout": bool        # 是否点球大战
}
```

---

## 💻 使用示例

### 示例 1：基本用法

```python
from app.services.tournament_sim import simulate_group_stage, simulate_knockout_stage

# 定义 12 个小组（每组 4 支球队）
groups = [
    # Group A
    [
        (1, "Brazil", 2100.0),
        (2, "Germany", 1950.0),
        (3, "Japan", 1750.0),
        (4, "Cameroon", 1600.0)
    ],
    # ... 其他 11 个小组
]

# 模拟小组赛
group_result = simulate_group_stage(groups, seed=42)

# 模拟淘汰赛
knockout_result = simulate_knockout_stage(
    group_result["group_results"],
    group_result["third_places_ranking"],
    seed=42
)

# 查看冠军
print(f"冠军: {knockout_result['champion']['team_name']}")

# 查看决赛比分
final_match = knockout_result["final"]["matches"][0]
print(f"决赛: {final_match['team_a_name']} {final_match['score_a']}-{final_match['score_b']} {final_match['team_b_name']}")
```

### 示例 2：遍历所有比赛

```python
# 打印所有轮次的比赛结果
rounds = [
    ("1/16决赛", "round_of_32"),
    ("1/8决赛", "round_of_16"),
    ("1/4决赛", "quarter_finals"),
    ("半决赛", "semi_finals"),
    ("决赛", "final")
]

for round_name, round_key in rounds:
    print(f"\n【{round_name}】")
    print("-" * 50)
    
    for match in knockout_result[round_key]["matches"]:
        shootout_marker = " (点球)" if match["is_penalty_shootout"] else ""
        print(f"{match['team_a_name']} {match['score_a']}-{match['score_b']} {match['team_b_name']}{shootout_marker}")
        print(f"  → 胜者: {match['winner_name']}")
```

### 示例 3：生成赛程树数据（供前端使用）

```python
def build_bracket_tree(knockout_result: dict) -> dict:
    """
    构建适合前端渲染的赛程树结构
    """
    tree = {
        "round_of_32": [],
        "round_of_16": [],
        "quarter_finals": [],
        "semi_finals": [],
        "final": []
    }
    
    # 1/16决赛
    for match in knockout_result["round_of_32"]["matches"]:
        tree["round_of_32"].append({
            "id": f"R32_{match['match_number']}",
            "team_a": {
                "id": match["team_a_id"],
                "name": match["team_a_name"],
                "score": match["score_a"]
            },
            "team_b": {
                "id": match["team_b_id"],
                "name": match["team_b_name"],
                "score": match["score_b"]
            },
            "winner": {
                "id": match["winner_id"],
                "name": match["winner_name"]
            },
            "next_match": f"R16_{(match['match_number'] + 1) // 2}"
        })
    
    # 1/8决赛
    for match in knockout_result["round_of_16"]["matches"]:
        tree["round_of_16"].append({
            "id": f"R16_{match['match_number']}",
            "team_a": {
                "id": match["team_a_id"],
                "name": match["team_a_name"],
                "score": match["score_a"]
            },
            "team_b": {
                "id": match["team_b_id"],
                "name": match["team_b_name"],
                "score": match["score_b"]
            },
            "winner": {
                "id": match["winner_id"],
                "name": match["winner_name"]
            },
            "next_match": f"QF_{(match['match_number'] + 1) // 2}"
        })
    
    # ... 继续构建其他轮次
    
    return tree

bracket_tree = build_bracket_tree(knockout_result)
```

### 示例 4：蒙特卡洛模拟（多次运行统计胜率）

```python
import random
from collections import Counter

def monte_carlo_champion_prediction(groups: list, num_simulations: int = 1000):
    """
    蒙特卡洛模拟预测冠军概率
    """
    champion_counter = Counter()
    
    for i in range(num_simulations):
        # 每次使用不同的随机种子
        seed = random.randint(0, 1000000)
        
        # 模拟小组赛
        group_result = simulate_group_stage(groups, seed=seed)
        
        # 模拟淘汰赛
        knockout_result = simulate_knockout_stage(
            group_result["group_results"],
            group_result["third_places_ranking"],
            seed=seed
        )
        
        # 记录冠军
        champion_name = knockout_result["champion"]["team_name"]
        champion_counter[champion_name] += 1
        
        if (i + 1) % 100 == 0:
            print(f"已完成 {i + 1}/{num_simulations} 次模拟")
    
    # 计算胜率
    total = sum(champion_counter.values())
    win_rates = {
        team: count / total * 100
        for team, count in champion_counter.most_common(10)
    }
    
    return win_rates

# 使用示例
win_rates = monte_carlo_champion_prediction(groups, num_simulations=1000)
print("\n冠军概率排名（前10）:")
for team, rate in win_rates.items():
    print(f"{team}: {rate:.2f}%")
```

---

## 🏆 淘汰赛对阵规则

### 1/16 决赛对阵表

| 场次 | 对阵 | 说明 |
|------|------|------|
| 1 | A1 vs B2 | A组第一 vs B组第二 |
| 2 | C1 vs D2 | C组第一 vs D组第二 |
| 3 | E1 vs F2 | E组第一 vs F组第二 |
| 4 | G1 vs H2 | G组第一 vs H组第二 |
| 5 | I1 vs J2 | I组第一 vs J组第二 |
| 6 | K1 vs L2 | K组第一 vs L组第二 |
| 7 | B1 vs A2 | B组第一 vs A组第二 |
| 8 | D1 vs C2 | D组第一 vs C组第二 |
| 9 | F1 vs E2 | F组第一 vs E组第二 |
| 10 | H1 vs G2 | H组第一 vs G组第二 |
| 11 | J1 vs I2 | J组第一 vs I组第二 |
| 12 | L1 vs K2 | L组第一 vs K组第二 |
| 13 | 3rd_1 vs 3rd_8 | 第1名最佳第三 vs 第8名最佳第三 |
| 14 | 3rd_2 vs 3rd_7 | 第2名最佳第三 vs 第7名最佳第三 |
| 15 | 3rd_3 vs 3rd_6 | 第3名最佳第三 vs 第6名最佳第三 |
| 16 | 3rd_4 vs 3rd_5 | 第4名最佳第三 vs 第5名最佳第三 |

### 上下半区划分

**上半区**（场次 1-8 的胜者）：
- R32_1 胜者 vs R32_2 胜者 → R16_1
- R32_3 胜者 vs R32_4 胜者 → R16_2
- R32_5 胜者 vs R32_6 胜者 → R16_3
- R32_7 胜者 vs R32_8 胜者 → R16_4

**下半区**（场次 9-16 的胜者）：
- R32_9 胜者 vs R32_10 胜者 → R16_5
- R32_11 胜者 vs R32_12 胜者 → R16_6
- R32_13 胜者 vs R32_14 胜者 → R16_7
- R32_15 胜者 vs R32_16 胜者 → R16_8

### 后续轮次对阵

- **1/8 决赛**: R16_1 vs R16_2, R16_3 vs R16_4, ..., R16_7 vs R16_8
- **1/4 决赛**: QF_1 vs QF_2, QF_3 vs QF_4
- **半决赛**: SF_1 vs SF_2
- **决赛**: 最终对决

---

## 🔧 技术实现细节

### 1. 球队信息映射

```python
# 构建 32 强球队映射
qualified_teams_map = {
    "A1": (team_id, team_name, elo_rating),
    "A2": (team_id, team_name, elo_rating),
    "B1": (team_id, team_name, elo_rating),
    ...
    "3rd_1": (team_id, team_name, elo_rating),
    ...
}
```

### 2. 胜者传递机制

```python
# 存储每轮比赛的胜者
previous_round_winners = {
    "R32_1": (winner_id, winner_name, winner_elo),
    "R32_2": (winner_id, winner_name, winner_elo),
    ...
}

# 下一轮通过键名获取上一轮胜者
team_a = previous_round_winners.get("R32_1")
```

### 3. 点球大战逻辑

```python
# 如果常规时间平局
if goals_a == goals_b:
    is_penalty_shootout = True
    # 随机决定点球胜负（简化处理）
    if random.random() < 0.5:
        goals_a += 1  # A队点球获胜
    else:
        goals_b += 1  # B队点球获胜
```

---

## ⚠️ 注意事项

### 1. Elo 评分来源
当前实现中，淘汰赛球队的 Elo 评分从小组赛结果的 `standings` 中提取。如果 standings 中没有 `elo_rating` 字段，会使用默认值 1500.0。

**建议**：在 `simulate_group_stage` 中确保 standings 包含 `elo_rating` 字段。

### 2. 点球大战简化
当前点球大战采用简化的随机决定方式。如需更真实的模拟，可以：
- 实现详细的点球大战逻辑（5 轮 + 突然死亡）
- 考虑门将扑救率、球员罚球命中率等因素

### 3. 第三名对阵规则
2026 世界杯的具体第三名对阵规则可能因 FIFA 官方规定而异。当前实现采用固定的配对方式（3rd_1 vs 3rd_8, 3rd_2 vs 3rd_7 等）。

### 4. 随机性控制
务必设置 `seed` 参数以保证结果可复现，特别是在进行蒙特卡洛模拟时。

---

## 🚀 扩展建议

### 1. 添加三四名决赛

```python
# 在决赛之前添加三四名决赛
third_place_match = simulate_knockout_match(
    engine,
    semi_finals["matches"][0]["loser_id"],  # 需要修改以记录败者
    semi_finals["matches"][1]["loser_id"],
    ...
)
```

### 2. 更详细的比赛统计

```python
class DetailedKnockoutMatch(TypedDict):
    """增强的比赛信息"""
    ...
    possession_a: float  # A队控球率
    shots_a: int         # A队射门次数
    cards_yellow_a: int  # A队黄牌数
    cards_red_a: int     # A队红牌数
    ...
```

### 3. 主场优势

```python
# 根据比赛地点调整 Elo 评分
if match_location == "home":
    team_a_elo += 100  # 主场优势加分
elif match_location == "away":
    team_a_elo -= 100  # 客场劣势减分
```

### 4. 实时概率更新

```python
# 在比赛进行中根据实时比分更新胜率
def calculate_live_win_probability(
    score_a: int,
    score_b: int,
    time_minute: int,
    elo_a: float,
    elo_b: float
) -> float:
    """计算实时胜率"""
    ...
```

---

## 📊 与前端集成

### React 组件示例

```tsx
interface KnockoutMatch {
  roundName: string;
  matchNumber: number;
  teamA: { id: number; name: string; score: number };
  teamB: { id: number; name: string; score: number };
  winner: { id: number; name: string };
  isPenaltyShootout: boolean;
}

const MatchCard: React.FC<{ match: KnockoutMatch }> = ({ match }) => {
  return (
    <div className="match-card">
      <div className="team">
        <span>{match.teamA.name}</span>
        <span className="score">{match.teamA.score}</span>
      </div>
      <div className="vs">VS</div>
      <div className="team">
        <span className="score">{match.teamB.score}</span>
        <span>{match.teamB.name}</span>
      </div>
      {match.isPenaltyShootout && (
        <div className="penalty-marker">(点球)</div>
      )}
      <div className="winner">
        胜者: {match.winner.name}
      </div>
    </div>
  );
};
```

---

## 📝 总结

`simplify_knockout_stage` 函数提供了：
- ✅ 完整的 32 强淘汰赛模拟
- ✅ 固定落位对阵表
- ✅ 递归节点遍历逻辑
- ✅ 点球大战机制
- ✅ 清晰的嵌套字典结构
- ✅ 便于前端渲染的数据格式

可以直接与 `simulate_group_stage` 结合使用，实现从小组赛到决赛的完整世界杯模拟！
