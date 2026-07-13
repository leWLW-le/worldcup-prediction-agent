# 数据库模型与 CRUD 使用指南

## 📋 概述

本文档详细介绍世界杯预测项目的三张核心数据表及其 CRUD 操作函数。

---

## 🗄️ 数据库表结构

### 1. Team（球队表）

存储参赛球队的基本信息和 ELO 评分。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer (PK) | 主键，自增 |
| name | String(100) | 球队名称（唯一） |
| confederation | String(50) | 洲际足联（如 UEFA, CONMEBOL） |
| current_elo | Float | 当前 ELO 评分（默认 1500.0） |

**示例数据：**
```python
{
    "id": 1,
    "name": "Brazil",
    "confederation": "CONMEBOL",
    "current_elo": 2050.5
}
```

---

### 2. Match（比赛表）

存储比赛信息和结果。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer (PK) | 主键，自增 |
| date | DateTime | 比赛日期 |
| team_a_id | Integer (FK) | A队ID → teams.id |
| team_b_id | Integer (FK) | B队ID → teams.id |
| score_a | Integer | A队得分 |
| score_b | Integer | B队得分 |
| is_knockout | Boolean | 是否为淘汰赛 |
| tournament_type | String(50) | 赛事类型（如 World Cup 2026） |

**示例数据：**
```python
{
    "id": 1,
    "date": "2026-07-15T20:00:00",
    "team_a_id": 1,
    "team_b_id": 2,
    "score_a": 2,
    "score_b": 1,
    "is_knockout": true,
    "tournament_type": "World Cup 2026"
}
```

---

### 3. SimulationRecord（模拟记录表）

存储 Monte Carlo 模拟结果。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer (PK) | 主键，自增 |
| version | String(50) | 模拟版本标识 |
| champion_team_id | Integer (FK) | 冠军队伍ID → teams.id |
| simulation_log | Text | JSON 格式的模拟日志 |
| created_at | DateTime | 创建时间 |

**示例数据：**
```python
{
    "id": 1,
    "version": "v1.0-monte-carlo",
    "champion_team_id": 1,
    "simulation_log": "{\"total_simulations\": 10000, \"method\": \"Monte Carlo\"}",
    "created_at": "2026-07-07T12:00:00"
}
```

---

## 🔧 CRUD 函数使用

### Team CRUD

#### 创建球队

```python
from app import crud
from app.models.pydantic_models import TeamCreate

team_data = TeamCreate(
    name="Argentina",
    confederation="CONMEBOL",
    current_elo=2100.0
)
team = crud.create_team(db, team_data)
print(f"Created: {team.name} (ELO: {team.current_elo})")
```

#### 查询球队

```python
# 根据 ID 查询
team = crud.get_team(db, team_id=1)

# 根据名称查询
team = crud.get_team_by_name(db, name="Brazil")

# 获取所有球队
teams = crud.get_teams(db, skip=0, limit=100)

# 按洲际足联筛选
uefa_teams = crud.get_teams(db, confederation="UEFA")

# 按 ELO 范围查询
strong_teams = crud.get_teams_by_elo_range(db, min_elo=2000, max_elo=2100)
```

#### 更新球队

```python
from app.models.pydantic_models import TeamUpdate

update_data = TeamUpdate(
    current_elo=2120.0,
    confederation="CONMEBOL"
)
updated_team = crud.update_team(db, team_id=1, team_update=update_data)
```

#### 删除球队

```python
success = crud.delete_team(db, team_id=1)
if success:
    print("Team deleted")
```

---

### Match CRUD

#### 创建比赛

```python
from datetime import datetime
from app.models.pydantic_models import MatchCreate

match_data = MatchCreate(
    date=datetime(2026, 7, 15, 20, 0),
    team_a_id=1,
    team_b_id=2,
    is_knockout=True,
    tournament_type="World Cup 2026"
)
match = crud.create_match(db, match_data)
```

#### 查询比赛

```python
# 根据 ID 查询
match = crud.get_match(db, match_id=1)

# 获取所有比赛
matches = crud.get_matches(db, skip=0, limit=100)

# 按队伍筛选
team_matches = crud.get_matches(db, team_id=1)

# 按淘汰赛筛选
knockout_matches = crud.get_matches(db, is_knockout=True)

# 按赛事类型筛选
wc_matches = crud.get_matches(db, tournament_type="World Cup 2026")

# 获取指定赛事的所有比赛
all_wc_matches = crud.get_matches_by_tournament(db, "World Cup 2026")
```

#### 更新比赛结果

```python
from app.models.pydantic_models import MatchUpdate

update_data = MatchUpdate(
    score_a=2,
    score_b=1
)
updated_match = crud.update_match(db, match_id=1, match_update=update_data)
```

#### 删除比赛

```python
success = crud.delete_match(db, match_id=1)
```

---

### SimulationRecord CRUD

#### 创建模拟记录

```python
import json
from app.models.pydantic_models import SimulationRecordCreate

simulation_log = {
    "total_simulations": 10000,
    "method": "Monte Carlo",
    "iterations": 10000,
    "top_4": ["Spain", "Brazil", "Argentina", "France"]
}

record_data = SimulationRecordCreate(
    version="v1.0-monte-carlo",
    champion_team_id=1,
    simulation_log=json.dumps(simulation_log, ensure_ascii=False)
)
record = crud.create_simulation_record(db, record_data)
```

#### 查询模拟记录

```python
# 根据 ID 查询
record = crud.get_simulation_record(db, record_id=1)

# 获取所有记录
records = crud.get_simulation_records(db, skip=0, limit=100)

# 按版本查询
version_records = crud.get_simulation_records(db, version="v1.0-monte-carlo")

# 按冠军队伍查询
champion_records = crud.get_simulation_records(db, champion_team_id=1)

# 获取最新版本记录
latest = crud.get_simulation_record_by_version(db, version="v1.0-monte-carlo")
```

#### 解析 JSON 日志

```python
log_data = crud.parse_simulation_log(record)
if log_data:
    print(f"Total simulations: {log_data['total_simulations']}")
```

#### 获取统计数据

```python
stats = crud.get_simulation_stats(db, version="v1.0-monte-carlo")
print(f"Total: {stats['total_simulations']}")
print(f"Champion distribution: {stats['champion_distribution']}")
```

#### 删除模拟记录

```python
success = crud.delete_simulation_record(db, record_id=1)
```

---

## 🧪 运行测试

执行完整的 CRUD 功能测试：

```bash
python test_crud.py
```

预期输出：
```
🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀
开始 CRUD 功能测试
🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀

============================================================
测试球队 CRUD
============================================================
...
✅ 所有 CRUD 测试通过！
```

---

## 📊 关系图

```
┌─────────────┐         ┌──────────────┐
│   Team      │         │    Match     │
├─────────────┤         ├──────────────┤
│ id (PK)     │◄────────│ team_a_id(FK)│
│ name        │◄────────│ team_b_id(FK)│
│ confed.     │         │ date         │
│ current_elo │         │ score_a      │
└──────┬──────┘         │ score_b      │
       │                │ is_knockout  │
       │                │ tournament   │
       │                └──────────────┘
       │
       │         ┌──────────────────┐
       └────────►│Simulatio Record  │
                 ├──────────────────┤
                 │ id (PK)          │
                 │ version          │
                 │ champion_team(FK)│
                 │ simulation_log   │
                 │ created_at       │
                 └──────────────────┘
```

---

## ⚠️ 注意事项

### 数据验证

1. **创建比赛时**：
   - 参赛队伍必须存在
   - team_a 和 team_b 不能相同

2. **创建模拟记录时**：
   - 冠军队伍必须存在
   - simulation_log 可以是 JSON 字符串或字典（自动转换）

### 性能优化

1. **批量查询**：使用 `skip` 和 `limit` 进行分页
2. **索引字段**：所有外键和常用查询字段已建立索引
3. **统计查询**：使用 `get_simulation_stats()` 而非手动聚合

### 错误处理

所有 CRUD 函数在遇到错误时会：
- 返回 `None`（查询不存在）
- 返回 `False`（删除失败）
- 抛出 `ValueError`（数据验证失败）

建议在使用时添加异常处理：

```python
try:
    team = crud.create_team(db, team_data)
except ValueError as e:
    print(f"Validation error: {e}")
```

---

## 🔗 相关文件

- **数据库模型**: `app/models/schemas.py`
- **Pydantic 模型**: `app/models/pydantic_models.py`
- **CRUD 函数**: `app/crud.py`
- **测试脚本**: `test_crud.py`

---

**最后更新**: 2026-07-07  
**版本**: 1.0.0
