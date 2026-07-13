"""
验收脚本：检查沙盘决赛对阵逻辑（任务 17）

检查内容：
 1. 当前 stage == semi_finals
 2. 半决赛数量 == 2
 3. 半决赛包含 France vs Spain
 4. 半决赛包含 England vs Argentina
 5. 假设 Spain 淘汰 France 后，final_matchup_distribution 只包含 Spain vs Argentina / Spain vs England
 6. final_matchup_distribution 不包含 France
 7. final_matchup_distribution 不包含 TBD
 8. final_matchup_distribution 不包含 3rd Place
 9. forced_loser France finalist_probability == 0
10. forced_loser France champion_probability == 0
11. Spain finalist_probability == 1
12. Argentina finalist_probability + England finalist_probability == 1
13. scenario_prediction.top_candidates 概率和 == 1
14. scenario_result 不覆盖 final_agent_result
15. Dashboard 显示的"可能决赛对阵"来自 final_matchup_distribution
"""
import sys
import json
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

PASS_COUNT = 0
FAIL_COUNT = 0


def check(num: int, desc: str, condition: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  [{num:2d}] PASS  {desc}")
    else:
        FAIL_COUNT += 1
        msg = f"  [{num:2d}] FAIL  {desc}"
        if detail:
            msg += f"  ({detail})"
        print(msg)


def main():
    global PASS_COUNT, FAIL_COUNT

    print("=" * 60)
    print("沙盘决赛对阵逻辑验证")
    print("=" * 60)

    from app.db.database import SessionLocal
    from app.models.agent_models import Fixture
    from app.services.tournament_state_service import get_current_tournament_stage
    from app.services.scenario_simulation_service import (
        get_semifinal_matches,
        run_scenario_simulation,
    )

    db = SessionLocal()
    try:
        # ── 1. 当前 stage == semi_finals ──
        stage_info = get_current_tournament_stage(db)
        current_stage = stage_info["stage"]
        check(1, "当前 stage == semi_finals", current_stage == "semi_finals",
              f"actual={current_stage}")

        # ── 2. 半决赛数量 == 2 ──
        all_fixtures = db.query(Fixture).all()
        semis = get_semifinal_matches(all_fixtures)
        check(2, "半决赛数量 == 2", len(semis) == 2, f"actual={len(semis)}")

        # ── 3. 半决赛包含 France vs Spain ──
        sf1_found = any(
            (s["home_team"] == "France" and s["away_team"] == "Spain") or
            (s["home_team"] == "Spain" and s["away_team"] == "France")
            for s in semis
        )
        check(3, "半决赛包含 France vs Spain", sf1_found)

        # ── 4. 半决赛包含 England vs Argentina ──
        sf2_found = any(
            (s["home_team"] == "England" and s["away_team"] == "Argentina") or
            (s["home_team"] == "Argentina" and s["away_team"] == "England")
            for s in semis
        )
        check(4, "半决赛包含 England vs Argentina", sf2_found)

        # ── 运行沙盘模拟：假设 Spain 淘汰 France ──
        # 找到 France vs Spain 的 fixture_id
        france_spain_match = None
        for s in semis:
            if (s["home_team"] == "France" and s["away_team"] == "Spain") or \
               (s["home_team"] == "Spain" and s["away_team"] == "France"):
                france_spain_match = s
                break

        if not france_spain_match:
            print("  ERROR: 找不到 France vs Spain 半决赛，无法继续验证")
            return

        result = run_scenario_simulation(
            match_id=france_spain_match["match_id"],
            forced_winner="Spain",
            simulation_count=2000,
        )

        if not result.get("success"):
            print(f"  ERROR: 沙盘模拟失败: {result.get('error', result.get('message', 'unknown'))}")
            return

        # ── 5. final_matchup_distribution 只包含 Spain vs Argentina / Spain vs England ──
        fmd = result.get("final_matchup_distribution", [])
        valid_matchups = {"Spain vs Argentina", "Spain vs England"}
        all_valid = all(fm["matchup"] in valid_matchups for fm in fmd)
        actual_matchups = {fm["matchup"] for fm in fmd}
        check(5, "final_matchup 只包含 Spain vs Argentina / Spain vs England",
              all_valid and len(fmd) > 0,
              f"actual={actual_matchups}")

        # ── 6. final_matchup_distribution 不包含 France ──
        has_france = any("France" in fm["matchup"] for fm in fmd)
        check(6, "final_matchup 不包含 France", not has_france)

        # ── 7. final_matchup_distribution 不包含 TBD ──
        has_tbd = any("TBD" in fm["matchup"] or "tbd" in fm["matchup"].lower() for fm in fmd)
        check(7, "final_matchup 不包含 TBD", not has_tbd)

        # ── 8. final_matchup_distribution 不包含 3rd Place ──
        has_3rd = any("3rd" in fm["matchup"] or "third" in fm["matchup"].lower() or "季军" in fm["matchup"] for fm in fmd)
        check(8, "final_matchup 不包含 3rd Place", not has_3rd)

        # ── 9. forced_loser France finalist_probability == 0 ──
        fd = result.get("finalist_distribution", [])
        france_fp = None
        for f in fd:
            if f["name"] == "France":
                france_fp = f.get("finalist_probability", -1)
                break
        check(9, "forced_loser France finalist_probability == 0",
              france_fp == 0.0 or france_fp == 0,
              f"actual={france_fp}")

        # ── 10. forced_loser France champion_probability == 0 ──
        sp = result.get("scenario_prediction", {})
        france_cp = None
        for tc in sp.get("top_candidates", []):
            if tc["name"] == "France":
                france_cp = tc.get("probability", -1)
                break
        check(10, "forced_loser France champion_probability == 0",
              france_cp == 0.0 or france_cp == 0,
              f"actual={france_cp}")

        # ── 11. Spain finalist_probability == 1 ──
        spain_fp = None
        for f in fd:
            if f["name"] == "Spain":
                spain_fp = f.get("finalist_probability", -1)
                break
        check(11, "Spain finalist_probability == 1",
              spain_fp == 1.0,
              f"actual={spain_fp}")

        # ── 12. Argentina + England finalist_probability == 1 ──
        arg_fp = eng_fp = None
        for f in fd:
            if f["name"] == "Argentina":
                arg_fp = f.get("finalist_probability", 0)
            if f["name"] == "England":
                eng_fp = f.get("finalist_probability", 0)
        if arg_fp is not None and eng_fp is not None:
            total_fp = arg_fp + eng_fp
            check(12, "Argentina + England finalist_probability == 1",
                  abs(total_fp - 1.0) < 0.01,
                  f"actual={total_fp} ({arg_fp} + {eng_fp})")
        else:
            check(12, "Argentina + England finalist_probability == 1",
                  False, f"Argentina={arg_fp}, England={eng_fp}")

        # ── 13. scenario_prediction.top_candidates 概率和 == 1 ──
        prob_sum = sum(tc.get("probability", 0) for tc in sp.get("top_candidates", []))
        check(13, "scenario_prediction 概率和 == 1",
              abs(prob_sum - 1.0) < 0.01,
              f"actual={prob_sum:.4f}")

        # ── 14. scenario_result 不覆盖 final_agent_result ──
        final_result_path = Path(__file__).parent.parent / "data" / "final_agent_result.json"
        scenario_result_path = Path(__file__).parent.parent / "data" / "scenario_result.json"

        if final_result_path.exists():
            with open(final_result_path, encoding="utf-8") as f:
                far = json.load(f)
            has_scenario_scope = "scenario_scope" in far
            check(14, "scenario_result 不覆盖 final_agent_result",
                  not has_scenario_scope,
                  "final_agent_result 包含 scenario_scope 字段" if has_scenario_scope else "")
        else:
            check(14, "scenario_result 不覆盖 final_agent_result", False, "final_agent_result.json 不存在")

        # ── 15. Dashboard 源码检查：可能决赛对阵来自 final_matchup_distribution ──
        dashboard_path = Path(__file__).parent.parent / "debug_dashboard.py"
        if dashboard_path.exists():
            with open(dashboard_path, encoding="utf-8") as f:
                dashboard_src = f.read()
            has_final_matchup_render = "final_matchup_distribution" in dashboard_src
            has_matchup_label = "可能决赛对阵" in dashboard_src
            check(15, "Dashboard 可能决赛对阵来自 final_matchup_distribution",
                  has_final_matchup_render and has_matchup_label)
        else:
            check(15, "Dashboard 可能决赛对阵来自 final_matchup_distribution",
                  False, "debug_dashboard.py 不存在")

    finally:
        db.close()

    # ── 输出总结 ──
    print()
    print("=" * 60)
    total = PASS_COUNT + FAIL_COUNT
    print(f"结果: {PASS_COUNT}/{total} 通过, {FAIL_COUNT} 失败")
    print("=" * 60)

    if FAIL_COUNT == 0:
        print("[OK] 沙盘决赛对阵逻辑验证全部通过")
    else:
        print("[FAIL] 存在不通过的检查项")
        sys.exit(1)


if __name__ == "__main__":
    main()
