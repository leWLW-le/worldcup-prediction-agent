#!/usr/bin/env bash
# ============================================================
# predeploy.sh — 部署前一次性维护脚本
# 在 Render pre-deploy command 或手动部署时运行
# 幂等：重复执行不会插入重复数据或破坏现有数据
#
# 关键：任意步骤失败都会以非零退出码退出，阻止 Uvicorn 启动
# ============================================================
set -euo pipefail

echo "========================================"
echo "  Pre-deploy maintenance"
echo "========================================"

# 1. Alembic 数据库迁移（如果存在 alembic 配置）
if [ -f "alembic.ini" ]; then
    echo "[1/4] Running Alembic migrations..."
    alembic upgrade head
else
    echo "[1/4] No alembic.ini found, skipping Alembic migration"
fi

# 2. 添加 canonical_pair 索引（幂等）
echo "[2/4] Running migrate_add_canonical_pair..."
python scripts/migrate_add_canonical_pair.py --apply

# 3. 初始化数据库表结构（幂等，create_all 不会重复创建）
echo "[3/4] Initializing database..."
python scripts/init_database.py

# 4. 修复 final_agent_result.json 一致性（幂等）
if [ -f "scripts/fix_final_result_json.py" ]; then
    echo "[4/4] Fixing final_agent_result.json consistency..."
    python scripts/fix_final_result_json.py
fi

echo ""
echo "========================================"
echo "  Pre-deploy maintenance complete ✅"
echo "========================================"
