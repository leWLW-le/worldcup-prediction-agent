"""
世界杯真实数据同步脚本

用法:
    cd J:\project\worldcup
    .venv\Scripts\python.exe scripts\sync_live_worldcup.py --season 2026
    .venv\Scripts\python.exe scripts\sync_live_worldcup.py --live-only
    .venv\Scripts\python.exe scripts\sync_live_worldcup.py --fixtures-only
"""

import argparse
import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.services.worldcup_sync_service import (
    sync_worldcup_fixtures,
    sync_live_fixtures,
    get_fixtures_summary,
)


def main():
    parser = argparse.ArgumentParser(description="Sync World Cup fixtures from API-Sports")
    parser.add_argument("--season", type=int, default=2026, help="World Cup season (default: 2026)")
    parser.add_argument("--live-only", action="store_true", help="Only sync live fixtures")
    parser.add_argument("--fixtures-only", action="store_true", help="Only sync scheduled fixtures")
    args = parser.parse_args()

    result = {
        "success": True,
        "fixtures_fetched": 0,
        "fixtures_upserted": 0,
        "live_fixtures_fetched": 0,
        "live_fixtures_upserted": 0,
        "finished_matches": 0,
        "live_matches": 0,
        "errors": [],
    }

    # Sync scheduled fixtures
    if not args.live_only:
        print(f"[sync] Fetching season={args.season} fixtures ...")
        fx = sync_worldcup_fixtures(season=args.season)
        if fx.get("success"):
            result["fixtures_fetched"] = fx.get("fixtures_fetched", 0)
            result["fixtures_upserted"] = fx.get("fixtures_upserted", 0)
            print(f"[sync] fixtures: fetched={result['fixtures_fetched']}, upserted={result['fixtures_upserted']}")
        else:
            result["success"] = False
            result["errors"].append(f"fixtures: {fx.get('error')}")
            print(f"[sync] fixtures FAILED: {fx.get('error')}")

    # Sync live fixtures
    if not args.fixtures_only:
        print("[sync] Fetching live fixtures ...")
        lv = sync_live_fixtures()
        if lv.get("success"):
            result["live_fixtures_fetched"] = lv.get("live_fetched", 0)
            result["live_fixtures_upserted"] = lv.get("live_upserted", 0)
            print(f"[sync] live: fetched={result['live_fixtures_fetched']}, upserted={result['live_fixtures_upserted']}")
        else:
            result["success"] = False
            result["errors"].append(f"live: {lv.get('error')}")
            print(f"[sync] live FAILED: {lv.get('error')}")

    # Summary
    summary = get_fixtures_summary()
    result["finished_matches"] = summary.get("finished_matches", 0)
    result["live_matches"] = summary.get("live_matches", 0)

    print("\n" + json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
