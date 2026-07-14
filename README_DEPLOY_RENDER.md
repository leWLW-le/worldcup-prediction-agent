# Render 部署指南

本文档说明如何将本项目部署到 [Render](https://render.com)，通过 GitHub 仓库实现自动化构建和运行。

---

## 前置条件

- GitHub 账号，项目已推送到 GitHub 仓库
- Render 账号（可使用 GitHub 登录）
- 以下 API Key 至少持有一个：
  - **ZhipuAI (GLM)** — `OPENAI_API_KEY`（必填，用于 AI 解释生成）
  - **football-data.org** — `FOOTBALL_DATA_API`（可选，用于实时比赛数据同步）
  - **API-Football** — `API_FOOTBALL`（可选，备用数据源）

---

## 第一步：上传项目到 GitHub

如果项目尚未推送到 GitHub，先在本地执行：

```bash
git remote add origin https://github.com/<你的用户名>/worldcup-prediction-agent.git
git push -u origin master
```

确保 `.env` 不会被推送（已在 `.gitignore` 中排除）。

---

## 第二步：在 Render 创建 Backend 服务

1. 登录 [Render Dashboard](https://dashboard.render.com)
2. 点击 **New +** → **Web Service**
3. 选择 **Build and deploy from a Git repository** → 连接你的 GitHub 仓库
4. 配置如下：

| 字段 | 值 |
|---|---|
| Name | `worldcup-backend` |
| Region | 选择离你最近的区域 |
| Branch | `master` |
| Runtime | `Python 3` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Instance Type | `Free` |

5. 在 **Environment Variables** 中添加以下变量：

| Key | Value | 说明 |
|---|---|---|
| `OPENAI_API_KEY` | `你的ZhipuAI密钥` | **必填**，在 Render 界面手动输入 |
| `OPENAI_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4` | ZhipuAI API 地址 |
| `OPENAI_MODEL` | `glm-4-flash` | 模型名称 |
| `ALLOWED_ORIGINS` | `*` | CORS 允许的来源 |
| `ENV` | `production` | 运行环境 |
| `DATABASE_URL` | `sqlite:///./data/worldcup.db` | 数据库路径 |
| `FOOTBALL_DATA_API` | `你的football-data密钥` | 可选，手动输入 |
| `API_FOOTBALL` | `你的API-Football密钥` | 可选，手动输入 |

> **注意：** 标记为 `sync: false` 的变量（`OPENAI_API_KEY`、`FOOTBALL_DATA_API`、`API_FOOTBALL`）不会从 render.yaml 自动填充，必须在 Render Dashboard 中手动填写真实值。

6. 点击 **Create Web Service**，等待构建完成。

---

## 第三步：验证 Backend

构建完成后，打开 Backend 的 URL：

```
https://worldcup-backend-k2sn.onrender.com/docs
```

如果看到 Swagger UI 页面（FastAPI 自动生成的 API 文档），说明 Backend 部署成功。

记下 Backend 的 URL，下一步需要用到。

---

## 第四步：创建 Frontend 服务

1. 回到 Render Dashboard，点击 **New +** → **Web Service**
2. 同样连接你的 GitHub 仓库
3. 配置如下：

| 字段 | 值 |
|---|---|
| Name | `worldcup-frontend` |
| Region | 与 Backend 相同 |
| Branch | `master` |
| Runtime | `Python 3` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `streamlit run debug_dashboard.py --server.address 0.0.0.0 --server.port $PORT` |
| Instance Type | `Free` |

4. 在 **Environment Variables** 中添加：

| Key | Value | 说明 |
|---|---|---|
| `BACKEND_URL` | `https://worldcup-backend-k2sn.onrender.com` | 替换为你的 Backend 实际 URL |

> **重要：** `BACKEND_URL` 必须指向你在第三步记下的 Backend 实际 URL。如果 Render 分配的域名不同（例如 `worldcup-backend-abc1.onrender.com`），请相应修改。

5. 点击 **Create Web Service**，等待构建完成。

---

## 第五步：验证 Frontend

构建完成后，打开 Frontend 的 URL：

```
https://worldcup-frontend.onrender.com
```

你应该能看到 Streamlit 世界杯预测仪表盘。检查：

- 页面能正常加载
- 冠军预测卡片显示
- 淘汰赛路线图显示
- AI 解释文字显示

---

## 使用 Blueprint 一键部署（可选）

如果你更喜欢一键部署，可以使用 render.yaml Blueprint：

1. 确保 `render.yaml` 已推送到仓库根目录
2. 在 Render Dashboard 点击 **New +** → **Blueprint**
3. 连接 GitHub 仓库，Render 会自动读取 `render.yaml`
4. 在环境变量页面，手动填入 `OPENAI_API_KEY`、`FOOTBALL_DATA_API`、`API_FOOTBALL` 的真实值
5. 点击 **Apply**，Render 会同时创建 Backend 和 Frontend 两个服务

部署完成后，仍需检查 Frontend 的 `BACKEND_URL` 是否指向正确的 Backend 地址。

---

## 常见问题

**Q: Free 实例会休眠吗？**
A: 是的。Render Free 实例在 15 分钟无请求后会休眠，首次访问需要等待 30-60 秒冷启动。

**Q: 数据库数据会丢失吗？**
A: Render Free 实例使用临时磁盘，服务重新部署后 SQLite 数据库会重置为仓库中的初始数据。如需持久化数据，需升级到付费实例或使用外部数据库。

**Q: 如何更新部署？**
A: 推送代码到 GitHub 后，Render 会自动触发重新构建和部署。

**Q: Backend URL 变了怎么办？**
A: 在 Render Dashboard 中修改 Frontend 服务的 `BACKEND_URL` 环境变量，然后手动触发重新部署。
