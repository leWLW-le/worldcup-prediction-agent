# V2 发布候选：数据、模型与部署

## 数据与评估

- 来源：martj42/international_results，CC0，固定提交 394fe81893b062fbc2cf6257e988ac7cc4c039a1。
- 1990-01-23 至 2026-05-29，保留 14,366 场。非零比分要求完整进球事件且所有分钟在 1–90；比分为 0–0 时常规时间标签不因加时改变。原始文件和清洗结果均核对 SHA256。
- 事件缺失不是随机的；筛选存在样本偏差。来源经过回溯修订，因此不能视为历史时点严格可得的数据档案。
- 时间顺序训练/验证/校准/测试；最终测试 3,398 场，集成 Log Loss 0.864782。选定模型保留独立测试，不以测试集重新拟合。
- 三折扩展窗口 Log Loss：0.895368、0.872311、0.880454。完整报告 data/verified/walk-forward.json。
- 模型版本 v3-47ebf12d0c2242c2；Elo、Poisson、XGBoost、MLP 融合并温度校准。依赖和工件摘要由 manifest.json 锁定。

## 赛事规则与展示

完整 48 队、12 组、72 场小组赛，以及淘汰赛和季军赛。遵循 FIFA 2026 年五月规则的组内递归相互战绩、公平竞赛积分、当前及历史 FIFA 排名；Annex C 495 种分配表校验齐全。

未来比赛公平竞赛积分假定相同；加时/点球平局后各 50% 晋级。赛程日期的午夜时间是占位。附带结果截止 2026-06-01，2,000 次模拟、种子 42；德国 14.05% 是模型条件概率而非已知事实。单次代表路径与冠军概率分布分别展示。

保留原版 debug_dashboard.py 的 CSS、卡片和布局，由 dashboard/legacy_adapter.py 映射 V2 结果。API 失败不读取旧 JSON。网页通过服务端 BACKEND_API_KEY 鉴权，访客不手填密钥。首页显示赛前快照的冠军分布，淘汰赛路线独立展示真实接口赛程；API-Football 和备用源是否能形成完整预测输入取决于权限和数据完整性。LLM 解读成功后缓存，失败明确降级为模型摘要。

## 发布与回滚

后端 Python 3.12：pip install -r requirements.txt；uvicorn main:app --host 0.0.0.0 --port $PORT。
前端：pip install -r requirements-dashboard.txt；python -m streamlit run dashboard/app.py --server.address 0.0.0.0 --server.port $PORT。旧 debug_dashboard.py 启动路径也受支持。

配置 ENVIRONMENT=production、ALLOW_DEMO_DATA=false、实际 DATABASE_URL 和前端 BACKEND_URL。ADMIN_API_KEY 至少 24 字符，未配置则只读；ALLOWED_ORIGINS 为空或明确域名，不能为 *。LLM 凭据可选。设置 COMPUTE_TIMEOUT_SECONDS=600 支持完整赛事计算的时间预算。

部署前运行 Ruff 和 pytest。后端 /ready 必须报告数据库正常、trained 模式；读取 /api/v2/results 核对模型版本及截止日期。前端 /_stcore/health 返回 ok，并人工核验原版界面。Render 内存、PostgreSQL 及公网功能必须在线验证，配置文件不代表部署成功。

回滚使用 Render 前后端同一旧提交；新表以 v2_ 开头，保留旧数据，不删除已存运行。禁止为了上线绕过鉴权或模型摘要校验。
