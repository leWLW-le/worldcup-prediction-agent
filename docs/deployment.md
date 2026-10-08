# 运行与部署

## 本地合并模式（推荐）
在根目录使用 Python 3.12 安装 requirements.txt，复制 .env.example 为 .env。
设置 COMBINED_SERVICE=true，ADMIN_API_KEY 与 BACKEND_API_KEY 为相同的私人随机值；配置模型目录及外部 API 密钥。
运行 `python -m streamlit run debug_dashboard.py`。也支持 `dashboard/app.py`。
API 监听 127.0.0.1:8765，外部仅访问 Streamlit。

## 分离模式
设置 COMBINED_SERVICE=false，BACKEND_URL=http://127.0.0.1:8001。
分别运行：
```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8001
python -m streamlit run dashboard/app.py
```
API 与 dashboard 的服务端密钥必须匹配。访客不手填密钥。

## Streamlit Community Cloud
仓库 leWLW-le/worldcup-prediction-agent，分支 master，入口 debug_dashboard.py。
在创建应用的 Advanced settings 中明确选择 Python 3.12。
Secrets 使用顶层字符串值，不要增加包裹表：
```toml
COMBINED_SERVICE = "true"
ENVIRONMENT = "production"
ADMIN_API_KEY = "replace-with-private-random-value-at-least-24-characters"
BACKEND_API_KEY = "replace-with-the-same-private-random-value"
DATABASE_URL = "sqlite:///./worldcup-combined.db"
MODEL_BUNDLE_DIR = "models/production-v2"
SEED_RELEASE = "true"
ALLOW_DEMO_DATA = "false"
AUTO_REFRESH_DATA = "true"
COMPUTE_TIMEOUT_SECONDS = "600"
OMP_NUM_THREADS = "1"
OPENBLAS_NUM_THREADS = "1"
MKL_NUM_THREADS = "1"
```
再填写 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL、API_FOOTBALL 和 FOOTBALL_DATA_API 的实际值。不要把 Secrets 上传到仓库。

平台配置以实际控制台为准，更新代码不保证部署成功。已有 Python 版本错误的应用需要按平台支持的方式重建，先保存配置。
平台文档：https://docs.streamlit.io/deploy/streamlit-community-cloud

## 上线验收
- Streamlit /_stcore/health 可达；分离 API 的 /health 和 /ready 正常。
- 原 UI 能打开；冠军卡片明确为赛前回放。
- 解读标注 LLM 来源；失败时显示降级，而不是伪称调用成功。
- 真实赛程显示来源与更新时间；缺失时检查数据状态。
- 完成一次预测与一次情景操作，核对结果 run_id、快照与模型版本。
- 不把 HTTP 200 健康检查当作以上业务验收的替代。

## 存储和回滚
合并部署的 SQLite 与 data/cache/explanations 不保证持久化。重建可重新载入发布结果，但不能保证保留用户历史任务。需持久化时另行配置数据库及缓存存储。
回滚应恢复已知可用提交和对应配置，保留数据库，勿删除结果掩盖问题。

Render 历史合并模式参考 combined-deployment.md；计费暂停要在平台侧解决。Docker/Render 模板不等于当前 Streamlit 的部署配置。
