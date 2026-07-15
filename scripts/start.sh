#!/usr/bin/env bash
# ============================================================
# start.sh — Web 服务启动脚本
# 仅负责启动 Uvicorn，不执行迁移或数据修复
# 迁移和修复应在 predeploy.sh 或 Render pre-deploy command 中完成
# ============================================================
set -euo pipefail

PORT="${PORT:-10000}"

echo "🚀 Starting uvicorn on port ${PORT}..."

exec uvicorn main:app \
    --host 0.0.0.0 \
    --port "${PORT}"
