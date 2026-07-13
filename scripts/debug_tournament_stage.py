"""
debug_tournament_stage.py — 赛事阶段诊断脚本

输出：
1. 所有半决赛详情
2. 决赛详情（含占位判断）
3. stage_info 完整 JSON
4. 当前期望结果校验
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    from app.db.database import SessionLocal
    from app.models.agent_models import Fixture
    from app.services.tournament_state_service import (
        get_current_tournament_stage,
        is_placeholder_team,
        is_final_ready,
    )

    db = SessionLocal()
    try:
        # ── 1. 半决赛 ──
        print("=" * 60)
        print("1. 半决赛 (semi_finals)")
        print("=" * 60)
        semis = db.query(Fixture).filter(Fixture.stage == "semi_finals").all()
        for f in semis:
            is_fin = f.status in ("FT", "FINISHED", "AET", "PEN")
            print(f"  match_id  : {f.fixture_id}")
            print(f"  home_team : {f.home_team}")
            print(f"  away_team : {f.away_team}")
            print(f"  status    : {f.status}")
            print(f"  is_finished: {is_fin}")
            print()

        # ── 2. 决赛 ──
        print("=" * 60)
        print("2. 决赛 (final)")
        print("=" * 60)
        finals = db.query(Fixture).filter(Fixture.stage == "final").all()
        for f in finals:
            home_ph = is_placeholder_team(f.home_team)
            away_ph = is_placeholder_team(f.away_team)
            final_ready = is_final_ready(f, semis)
            print(f"  match_id        : {f.fixture_id}")
            print(f"  home_team       : {f.home_team}")
            print(f"  away_team       : {f.away_team}")
            print(f"  status          : {f.status}")
            print(f"  home_is_placeholder: {home_ph}")
            print(f"  away_is_placeholder: {away_ph}")
            print(f"  final_ready     : {final_ready}")
            print()

        if not finals:
            print("  (无决赛 fixture)")
            print()

        # ── 3. stage_info 完整 JSON ──
        print("=" * 60)
        print("3. stage_info 完整 JSON")
        print("=" * 60)
        stage_info = get_current_tournament_stage(db)
        print(json.dumps(stage_info, ensure_ascii=False, indent=2))
        print()

        # ── 4. 期望结果校验 ──
        print("=" * 60)
        print("4. 期望结果校验")
        print("=" * 60)

        checks = {
            "stage == semi_finals": stage_info["stage"] == "semi_finals",
            "sandbox_enabled == true": stage_info["sandbox_enabled"] is True,
            "pending_scenario_matches 数量 == 2": len(stage_info.get("pending_scenario_matches", [])) == 2,
            "surviving_count == 4": stage_info.get("surviving_count") == 4,
        }

        all_pass = True
        for name, ok in checks.items():
            status = "PASS" if ok else "FAIL"
            if not ok:
                all_pass = False
            print(f"  [{status}] {name}")

        print()
        if all_pass:
            print("  All checks passed!")
        else:
            print("  Some checks FAILED!")

        return 0 if all_pass else 1

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
