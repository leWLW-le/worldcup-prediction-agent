## Render 部署前置检查报告

**日期**: 2026-07-14
**状态**: 代码侧检查完成，两项待人工确认

---

### 1. PostgreSQL Region

**状态: 待确认**

当前 `render.yaml` 中写的是 `region: oregon`。此值未经验证，不得 push。等你提供现有后端实际 region 后再更新。

---

### 2. Blueprint 服务名关联

**状态: 待 Dashboard 预览确认**

`render.yaml` 中的服务名与线上域名 slug 的对应关系：

| render.yaml name | 线上域名 | 域名 slug |
|---|---|---|
| `worldcup-backend` | worldcup-backend-k2sn.onrender.com | worldcup-backend |
| `worldcup-frontend` | worldcup-frontend-rpnj.onrender.com | worldcup-frontend |
| `worldcup-postgres` (database) | 新建 | N/A |

Render Blueprint 按 `name` 字段匹配已有服务。如果已有服务是通过非 Blueprint 方式手动创建的，Sync 时 Render 的行为需要在 Dashboard 预览中确认。

**要求**: 在 Render Dashboard 中预览 Blueprint Sync，确认预览显示为：
- 更新现有前端（非新建）
- 更新现有后端（非新建）
- 仅创建一个新 PostgreSQL

如果预览显示"新建"而非"更新"，**不要 Sync**，需要先确认关联方式。

---

### 3. autoDeployTrigger

**状态: 已设置**

两个 web service 中均已设置 `autoDeployTrigger: off`（render.yaml 第 12 行和第 41 行）。此改动尚未 commit。

---

### 4. 初始化命令测试

**状态: 通过**

从仓库根目录执行：

```
$ python scripts/init_database.py
==================================================
World Cup DB Init (idempotent)
==================================================
Database backend: sqlite
Creating tables if missing...
Tables OK
Teams already exist, skipped
Seed fixtures already exist, skipped
==================================================
Init complete
==================================================
```

`python scripts/init_database.py` 直接可用，无需改用 `python -m scripts.init_database`。脚本内部通过 `Path(__file__).resolve().parent.parent` 自行设置 `sys.path`。

render.yaml 中的 startCommand 保持不变：
```
python scripts/init_database.py && uvicorn main:app --host 0.0.0.0 --port $PORT
```

---

### 5. PostgreSQL 本地测试

**状态: 全部通过 (19/19)**

由于 Docker 未安装，使用便携版 PostgreSQL 16.9 代替（等效测试）。测试环境：

- PostgreSQL 16.9 (Windows x64 portable)
- 端口 54329
- 数据库: worldcup
- 用户: postgres
- psycopg2-binary 2.9.12

#### 5.1 初始化脚本幂等性

| 执行次数 | 结果 |
|---|---|
| 第 1 次 | Tables OK, Created 4 team(s), Inserted 2 seed fixture(s) |
| 第 2 次 | Tables OK, Teams already exist skipped, Seed fixtures already exist skipped |

幂等性验证通过。

#### 5.2 check_db_connection

```
Backend: postgresql
check_db_connection: True
PASS
```

#### 5.3 FastAPI 服务器端点测试

| 端点 | 结果 |
|---|---|
| `GET /health` | 200, database=connected, backend=postgresql |
| `GET /api/v1/scenario/pending-matches` | 200, 返回比赛数据 |
| `GET /api/v1/agent/final-result` | 200, 返回完整预测结果 |
| `GET /api/v1/teams/` | 200, 返回 >= 4 支球队 |
| `GET /api/v1/scenario/stage-info` | 200 |

#### 5.4 数据写入和重新读取

| 操作 | 结果 |
|---|---|
| 写入 Team 记录到 PostgreSQL | PASS |
| 重新读取验证 name 和 elo | PASS |
| 删除并验证已删除 | PASS |

#### 5.5 清理

测试容器/进程已停止，临时文件已全部删除。

---

### 6. LLM 环境变量

**状态: 已确认**

代码实际读取的环境变量名（仅报告变量名，不输出密钥值）：

| 变量名 | 用途 | 使用位置 |
|---|---|---|
| `OPENAI_API_KEY` | LLM API 密钥（实际用于 ZhipuAI） | config.py, main.py, llm_planner_agent.py, llm_explainer.py, explanation_tool.py, llm_csv_assistant_tool.py, champion_explanation_service.py, bootstrap_service.py |
| `OPENAI_BASE_URL` | API 端点地址 | config.py, llm_planner_agent.py, render.yaml (值: `https://open.bigmodel.cn/api/paas/v4`) |
| `OPENAI_MODEL` | 模型名称 | config.py, main.py, llm_planner_agent.py, llm_csv_assistant_tool.py, champion_explanation_service.py, render.yaml (值: `glm-4-flash`) |

**注意**: 代码使用 `zhipuai` SDK（智谱 AI 原生 SDK），但环境变量名沿用 `OPENAI_*` 命名。没有使用 `ZHIPU_API_KEY` 或 `BIGMODEL` 等变量名。`bootstrap_service.py` 中有一条日志消息提到 "ZHIPU_API_KEY 未配置"，但实际检查的是 `settings.OPENAI_API_KEY`，日志消息有误导性但不影响功能。

render.yaml 中的 LLM 环境变量配置正确，与代码一致。

---

### 7. /health 数据库超时

**状态: 已确认安全**

`check_db_connection()` 函数（`app/db/database.py`）使用 `threading.Thread` + `join(timeout)` 实现超时保护：

- 默认超时: **5.0 秒**
- 机制: 在 daemon 线程中执行 `SELECT 1`，主线程 `join(timeout)` 等待结果
- 如果超时，返回 `False`（health 状态变为 `degraded`），不会阻塞数十秒

`/health` 端点调用 `check_db_connection()` 时未传自定义超时，使用默认 5 秒。Render 健康检查超时为 30 秒，5 秒的数据库检查远在 Render 超时之前完成。

---

### 8. 未 commit 的改动

当前工作区有两处未 commit 的改动：

1. **`render.yaml`**: 两个 web service 添加 `autoDeployTrigger: off`
2. **`app/db/database.py`**: `check_db_connection()` 添加 5 秒超时保护（使用 threading）

这两处改动是本次检查的代码修复，需要在确认 region 和 Blueprint 关联后一起 commit。

---

### 阻塞项汇总

| 编号 | 阻塞项 | 需要谁处理 |
|---|---|---|
| 1 | PostgreSQL region 未确认（当前写的 `oregon`，可能不正确） | 你提供实际 region |
| 2 | Blueprint Sync 预览未确认（是否更新现有服务 vs 新建） | 你在 Render Dashboard 预览确认 |

**在以上两项确认之前，不会 push 任何代码。**
