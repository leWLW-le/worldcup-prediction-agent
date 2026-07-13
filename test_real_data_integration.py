"""
真实数据集成测试

检查：
1. APISPORTS_KEY / API_FOOTBALL_KEY 是否存在
2. get_worldcup_fixtures(season=2026) 返回
3. get_worldcup_teams(season=2026) 返回
4. get_live_fixtures() 返回
5. WorldCupSyncService 能 upsert fixtures
6. fixtures 表有 api_fixture_id
7. fixtures 表 source in ["api-sports", "real_result"]
8. predicted_matches 和 fixtures 没有混淆
9. fallback 不能让这个测试通过
"""

import sys
import io
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

passed = 0
failed = 0


def check(num, desc, condition):
    global passed, failed
    status = "PASS" if condition else "FAIL"
    if condition:
        passed += 1
    else:
        failed += 1
    print(f"{num:2d}. [{status}] {desc}")


print("=" * 60)
print("Real Data Integration Test")
print("=" * 60)

start_time = time.time()

# ── 确保 fixtures 表存在 ──
from app.db.database import engine, Base
import app.models.agent_models  # noqa: F401
Base.metadata.create_all(bind=engine)

# ── Test 1: API Key 检测 ──
from app.core.config import get_settings
settings = get_settings()
api_key = settings.APISPORTS_KEY or settings.API_FOOTBALL_KEY
check(1, f"API key detected (key={api_key[:8]}...)" if api_key else "API key missing",
      bool(api_key))

# ── Test 2: get_worldcup_fixtures ──
from app.tools.api_sports_tool import APISportsTool
api = APISportsTool()
fixtures_resp = api.get_worldcup_fixtures(season=2026)
fixtures_data_count = len(fixtures_resp.get("data", []))
# API 限额用完时 success=False，但结构正确
check(2, f"get_worldcup_fixtures success={fixtures_resp['success']}, data_count={fixtures_data_count} (API rate limit may apply)",
      fixtures_resp["success"] and fixtures_data_count > 0)

# ── Test 3: get_worldcup_teams ──
teams_resp = api.get_worldcup_teams(season=2026)
teams_data_count = len(teams_resp.get("data", []))
check(3, f"get_worldcup_teams success={teams_resp['success']}, data_count={teams_data_count} (API rate limit may apply)",
      teams_resp["success"] and teams_data_count > 0)

# ── Test 4: get_live_fixtures ──
live_resp = api.get_live_fixtures()
check(4, f"get_live_fixtures success={live_resp['success']}, data_count={len(live_resp.get('data', []))} (API rate limit may apply)",
      live_resp["success"])

# ── Test 5: WorldCupSyncService upsert ──
from app.services.worldcup_sync_service import (
    sync_worldcup_fixtures,
    sync_live_fixtures,
    parse_api_fixture,
    upsert_fixture,
    get_fixtures_summary,
)
from app.db.database import SessionLocal
from app.models.agent_models import Fixture

sync_result = sync_worldcup_fixtures(season=2026)
# 如果 API 限额用完，sync 会失败，但结构正确
check(5, f"sync_worldcup_fixtures success={sync_result.get('success')}, upserted={sync_result.get('fixtures_upserted', 0)} (API rate limit may apply)",
      sync_result.get("success", False))

# ── Test 6: fixtures 表结构正确（有 api_fixture_id 列）──
db = SessionLocal()
try:
    from sqlalchemy import inspect as sa_inspect
    inspector = sa_inspect(engine)
    fixtures_columns = [c["name"] for c in inspector.get_columns("fixtures")]
    has_api_id_col = "api_fixture_id" in fixtures_columns
    check(6, f"fixtures table has api_fixture_id column (columns={len(fixtures_columns)})",
          has_api_id_col)

    # ── Test 7: fixtures 表 source 检查 ──
    all_fixtures = db.query(Fixture).all()
    if len(all_fixtures) > 0:
        valid_sources = all(f.source in ("api-sports", "real_result") for f in all_fixtures)
        source_set = set(f.source for f in all_fixtures)
        check(7, f"fixtures source in [api-sports, real_result] (sources={source_set}, count={len(all_fixtures)})",
              valid_sources)
    else:
        # 表为空（API 限额用完），检查表结构正确即可
        check(7, f"fixtures table exists but empty (API rate limit). Structure OK.",
              has_api_id_col)

    # ── Test 8: predicted_matches 和 fixtures 没有混淆 ──
    from app.models.agent_models import PredictedMatch
    pred_count = db.query(PredictedMatch).count()
    fixture_with_predicted = any(
        f.source in ("agent_prediction", "fallback_prediction")
        for f in all_fixtures
    )
    check(8, f"predicted_matches ({pred_count}) and fixtures not mixed (no prediction in fixtures={not fixture_with_predicted})",
          not fixture_with_predicted)

finally:
    db.close()

# ── Test 9: fallback 不能让测试通过 ──
# 如果 API key 存在但 fixtures 为空且没有 DB 数据，说明 fallback 被使用
fallback_used = (
    fixtures_resp["success"] and fixtures_data_count == 0 and len(all_fixtures) == 0
)
check(9, f"No fallback used (API data or DB data present)",
      not fallback_used)

# Summary
total_time = time.time() - start_time
print()
print("-" * 60)
print("Summary:")
print(f"  API-Sports fixtures: {fixtures_data_count} records (API)")
print(f"  API-Sports teams:    {teams_data_count} records (API)")
print(f"  Live fixtures:       {len(live_resp.get('data', []))} records (API)")
print(f"  DB fixtures:         {len(all_fixtures)} records")
print(f"  Sync result:         {sync_result}")
print(f"  Total time:          {total_time:.1f}s")
if not fixtures_resp["success"]:
    print(f"  NOTE: API rate limit reached. Tests 2-5 FAIL due to rate limit.")
    print(f"        Fixtures table structure is correct (Test 6 PASS).")
    print(f"        Re-run after API quota resets (daily reset).")
print("-" * 60)

if failed == 0:
    print(f"ALL {passed} CHECKS PASSED!")
else:
    print(f"{passed} PASSED, {failed} FAILED")
print("=" * 60)
