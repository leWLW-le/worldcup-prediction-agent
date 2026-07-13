"""
check_sandbox_stage_detection.py — 沙盘阶段识别验收脚本

检查：
1. 当前有两场未结束半决赛
2. final fixture 如果是 TBD/Winner of 占位，不得触发 stage=final
3. get_current_tournament_stage().stage == "semi_finals"
4. sandbox_enabled == true
5. pending_scenario_matches 数量 == 2
6. pending_scenario_matches 包含 France vs Spain
7. pending_scenario_matches 包含 England vs Argentina
8. pending_scenario_matches 不包含 Final
9. pending_scenario_matches 不包含 3rd Place Playoff
10. Dashboard 中沙盘模块不会显示"沙盘推演已结束"（sandbox_enabled=true 时）
11. Dashboard 包含"队伍夺冠概率"
12. Dashboard 不再包含"四强夺冠概率"
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS_COUNT = 0
FAIL_COUNT = 0


def check(num: int, name: str, ok: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    if ok:
        PASS_COUNT += 1
        print(f"  [{num:2d}] PASS  {name}")
    else:
        FAIL_COUNT += 1
        msg = f"  [{num:2d}] FAIL  {name}"
        if detail:
            msg += f"  ({detail})"
        print(msg)


def main():
    global PASS_COUNT, FAIL_COUNT

    from app.db.database import SessionLocal
    from app.models.agent_models import Fixture
    from app.services.tournament_state_service import (
        get_current_tournament_stage,
        is_placeholder_team,
    )

    db = SessionLocal()
    try:
        # ── 数据准备 ──
        semis = db.query(Fixture).filter(Fixture.stage == "semi_finals").all()
        finals = db.query(Fixture).filter(Fixture.stage == "final").all()
        pending_semis = [m for m in semis if m.status not in ("FT", "FINISHED", "AET", "PEN")]
        stage_info = get_current_tournament_stage(db)
        pending_matches = stage_info.get("pending_scenario_matches", [])

        # ── 1. 当前有两场未结束半决赛 ──
        check(1, "当前有两场未结束半决赛",
              len(pending_semis) == 2,
              f"实际: {len(pending_semis)}")

        # ── 2. final fixture 占位不触发 stage=final ──
        final_has_placeholder = False
        if finals:
            f = finals[0]
            final_has_placeholder = is_placeholder_team(f.home_team) or is_placeholder_team(f.away_team)
        if final_has_placeholder:
            check(2, "final fixture 是占位时 stage != final",
                  stage_info["stage"] != "final",
                  f"stage={stage_info['stage']}")
        else:
            # 没有 final 或 final 不是占位 → 跳过此检查（给 PASS）
            check(2, "final fixture 是占位时 stage != final（无占位 final，自动通过）", True)

        # ── 3. stage == "semi_finals" ──
        check(3, "stage == 'semi_finals'",
              stage_info["stage"] == "semi_finals",
              f"实际: {stage_info['stage']}")

        # ── 4. sandbox_enabled == true ──
        check(4, "sandbox_enabled == true",
              stage_info.get("sandbox_enabled") is True,
              f"实际: {stage_info.get('sandbox_enabled')}")

        # ── 5. pending_scenario_matches 数量 == 2 ──
        check(5, "pending_scenario_matches 数量 == 2",
              len(pending_matches) == 2,
              f"实际: {len(pending_matches)}")

        # ── 6. 包含 France vs Spain ──
        has_fr_es = any(
            (m["home_team"] == "France" and m["away_team"] == "Spain") or
            (m["home_team"] == "Spain" and m["away_team"] == "France")
            for m in pending_matches
        )
        check(6, "pending_scenario_matches 包含 France vs Spain", has_fr_es)

        # ── 7. 包含 England vs Argentina ──
        has_en_ar = any(
            (m["home_team"] == "England" and m["away_team"] == "Argentina") or
            (m["home_team"] == "Argentina" and m["away_team"] == "England")
            for m in pending_matches
        )
        check(7, "pending_scenario_matches 包含 England vs Argentina", has_en_ar)

        # ── 8. 不包含 Final ──
        has_final = any(m.get("stage") == "final" for m in pending_matches)
        check(8, "pending_scenario_matches 不包含 Final", not has_final)

        # ── 9. 不包含 3rd Place Playoff ──
        has_third = any(m.get("stage") in ("third_place", "3rd_place") for m in pending_matches)
        check(9, "pending_scenario_matches 不包含 3rd Place Playoff", not has_third)

        # ── 10. Dashboard 沙盘模块不会硬编码"已结束" ──
        dashboard_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "debug_dashboard.py"
        )
        with open(dashboard_path, encoding="utf-8") as f:
            content = f.read()

        # 检查 display_scenario_sandbox 不会在 sandbox_enabled=true 时显示"已结束"
        # 正确逻辑：sandbox_enabled 由 API 返回，dashboard 根据它决定显示
        has_sandbox_enabled_check = bool(re.search(
            r'if not sandbox_enabled', content
        ))
        check(10, "Dashboard 沙盘模块根据 sandbox_enabled 条件显示",
              has_sandbox_enabled_check)

        # ── 11. Dashboard 包含"队伍夺冠概率" ──
        has_unified_title = "队伍夺冠概率" in content
        check(11, "Dashboard 包含'队伍夺冠概率'", has_unified_title)

        # ── 12. Dashboard 不再包含"四强夺冠概率" ──
        has_old_title = "四强夺冠概率" in content
        check(12, "Dashboard 不再包含'四强夺冠概率'", not has_old_title)

        # ── 输出总结 ──
        print()
        print("=" * 60)
        total = PASS_COUNT + FAIL_COUNT
        print(f"结果: {PASS_COUNT}/{total} 通过, {FAIL_COUNT}/{total} 失败")
        if FAIL_COUNT == 0:
            print("[OK] 沙盘阶段识别验收全部通过!")
        else:
            print("[FAIL] 有检查未通过，请检查上方 FAIL 项")
        print("=" * 60)

        return 0 if FAIL_COUNT == 0 else 1

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
