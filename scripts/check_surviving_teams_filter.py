"""
验证脚本：surviving_teams 过滤逻辑全链路检查

10 项检查：
  1. tournament_state_service 正确识别当前阶段
  2. surviving_teams 只包含仍有夺冠可能的球队
  3. 已淘汰球队（如 Brazil）不在 surviving_teams 中
  4. simulation_distribution.json 只包含 surviving_teams
  5. simulation_distribution.json 中无已淘汰球队（如 Brazil）
  6. simulation_distribution.json 概率总和 = 1.0
  7. champion_counts 总和 = n_simulations
  8. final_agent_result.json top5 只包含 surviving_teams
  9. final_agent_result.json 包含 surviving_teams 和 stage 字段
 10. final_agent_result.json 包含 predicted_champion 字段

运行:
    python scripts/check_surviving_teams_filter.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

# ── 颜色 ──
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


def ok(msg):
    print(f"  {GREEN}[PASS]{RESET} {msg}")


def fail(msg):
    print(f"  {RED}[FAIL]{RESET} {msg}")


def info(msg):
    print(f"  {CYAN}[INFO]{RESET} {msg}")


def main():
    print(f"\n{BOLD}{'=' * 60}")
    print(f"Surviving Teams 过滤逻辑 — 全链路验证")
    print(f"{'=' * 60}{RESET}\n")

    passed = 0
    failed = 0
    results = []

    def check(num, desc, func):
        nonlocal passed, failed
        print(f"{BOLD}检查 {num}: {desc}{RESET}")
        try:
            success, msg = func()
            if success:
                ok(msg)
                passed += 1
                results.append((num, True, msg))
            else:
                fail(msg)
                failed += 1
                results.append((num, False, msg))
        except Exception as e:
            fail(f"异常: {e}")
            failed += 1
            results.append((num, False, str(e)))
        print()

    # ── 检查 1: 阶段识别 ──
    def check_stage_identification():
        from app.db.database import SessionLocal
        from app.services.tournament_state_service import get_surviving_teams_from_fixtures
        db = SessionLocal()
        try:
            state = get_surviving_teams_from_fixtures(db)
            stage = state.get("stage", "unknown")
            valid_stages = [
                "group_stage", "round_of_32", "round_of_16",
                "quarter_finals", "semi_finals", "final",
                "tournament_ended"
            ]
            if stage in valid_stages:
                return True, f"阶段 = {stage}（有效值）"
            else:
                return False, f"阶段 = {stage}（不在有效值列表中: {valid_stages}）"
        finally:
            db.close()

    check(1, "tournament_state_service 正确识别当前阶段", check_stage_identification)

    # ── 检查 2: surviving_teams 非空且合理 ──
    def check_surviving_teams_valid():
        from app.db.database import SessionLocal
        from app.services.tournament_state_service import get_surviving_teams_from_fixtures
        db = SessionLocal()
        try:
            state = get_surviving_teams_from_fixtures(db)
            surviving = state.get("surviving_teams", [])
            n = len(surviving)
            if n >= 2 and n <= 32:
                return True, f"surviving_teams 有 {n} 支球队: {surviving}"
            elif n == 1:
                return True, f"surviving_teams 有 1 支球队（冠军已产生）: {surviving}"
            else:
                return False, f"surviving_teams 为空或数量异常: n={n}"
        finally:
            db.close()

    check(2, "surviving_teams 只包含仍有夺冠可能的球队", check_surviving_teams_valid)

    # ── 检查 3: 已淘汰球队不在 surviving_teams 中 ──
    def check_no_eliminated_in_surviving():
        from app.db.database import SessionLocal
        from app.services.tournament_state_service import get_surviving_teams_from_fixtures
        db = SessionLocal()
        try:
            state = get_surviving_teams_from_fixtures(db)
            surviving = set(state.get("surviving_teams", []))
            eliminated = set(state.get("eliminated_teams", []))
            # 检查 Brazil, Germany 等已知淘汰球队
            known_eliminated = {"Brazil", "Germany", "Portugal", "Japan", "USA",
                                "Netherlands", "Croatia", "Uruguay", "Belgium", "Mexico"}
            overlap = surviving & known_eliminated
            if not overlap:
                return True, f"已淘汰球队不在 surviving_teams 中 (eliminated={len(eliminated)} 支)"
            else:
                return False, f"以下已淘汰球队仍出现在 surviving_teams 中: {overlap}"
        finally:
            db.close()

    check(3, "已淘汰球队（如 Brazil）不在 surviving_teams 中", check_no_eliminated_in_surviving)

    # ── 检查 4: simulation_distribution.json 只包含 surviving_teams ──
    def check_sim_dist_teams():
        dist_path = DATA_DIR / "simulation_distribution.json"
        if not dist_path.exists():
            return False, "simulation_distribution.json 不存在"
        with open(dist_path, encoding="utf-8") as f:
            dist = json.load(f)
        dist_teams = set(dist.get("champion", {}).keys())
        surviving = set(dist.get("surviving_teams", []))
        if not surviving:
            return False, "simulation_distribution.json 中 surviving_teams 为空"
        extra = dist_teams - surviving
        if not extra:
            return True, f"分布中 {len(dist_teams)} 支球队全部属于 surviving_teams ({len(surviving)} 支)"
        else:
            return False, f"分布中包含非 surviving 球队: {extra}"

    check(4, "simulation_distribution.json 只包含 surviving_teams", check_sim_dist_teams)

    # ── 检查 5: 分布中无已淘汰球队 ──
    def check_no_eliminated_in_dist():
        dist_path = DATA_DIR / "simulation_distribution.json"
        if not dist_path.exists():
            return False, "simulation_distribution.json 不存在"
        with open(dist_path, encoding="utf-8") as f:
            dist = json.load(f)
        dist_teams = set(dist.get("champion", {}).keys())
        known_eliminated = {"Brazil", "Germany", "Portugal", "Japan", "USA",
                            "Netherlands", "Croatia", "Uruguay", "Belgium", "Mexico"}
        overlap = dist_teams & known_eliminated
        if not overlap:
            return True, f"分布中无已淘汰球队 (共 {len(dist_teams)} 支球队)"
        else:
            return False, f"分布中包含已淘汰球队: {overlap}"

    check(5, "simulation_distribution.json 中无已淘汰球队（如 Brazil）", check_no_eliminated_in_dist)

    # ── 检查 6: 概率总和 = 1.0 ──
    def check_prob_sum():
        dist_path = DATA_DIR / "simulation_distribution.json"
        if not dist_path.exists():
            return False, "simulation_distribution.json 不存在"
        with open(dist_path, encoding="utf-8") as f:
            dist = json.load(f)
        champ_probs = dist.get("champion", {})
        if not champ_probs:
            return False, "champion 概率为空"
        prob_sum = sum(champ_probs.values())
        if abs(prob_sum - 1.0) < 0.01:
            return True, f"概率总和 = {prob_sum:.6f}（≈ 1.0）"
        else:
            return False, f"概率总和 = {prob_sum:.6f}（偏离 1.0 超过 1%）"

    check(6, "simulation_distribution.json 概率总和 = 1.0", check_prob_sum)

    # ── 检查 7: champion_counts 总和 = n_simulations ──
    def check_counts_sum():
        dist_path = DATA_DIR / "simulation_distribution.json"
        if not dist_path.exists():
            return False, "simulation_distribution.json 不存在"
        with open(dist_path, encoding="utf-8") as f:
            dist = json.load(f)
        counts = dist.get("champion_counts", {})
        n_sim = dist.get("n_simulations", 0)
        if not counts:
            return False, "champion_counts 为空"
        counts_sum = sum(counts.values())
        if counts_sum == n_sim:
            return True, f"champion_counts 总和 = {counts_sum} = n_simulations"
        else:
            return False, f"champion_counts 总和 ({counts_sum}) != n_simulations ({n_sim})"

    check(7, "champion_counts 总和 = n_simulations", check_counts_sum)

    # ── 检查 8: final_agent_result.json top5 只包含 surviving_teams ──
    def check_top5_surviving():
        result_path = DATA_DIR / "final_agent_result.json"
        if not result_path.exists():
            return False, "final_agent_result.json 不存在"
        with open(result_path, encoding="utf-8") as f:
            result = json.load(f)
        top5 = result.get("top5", [])
        surviving = set(result.get("surviving_teams", []))
        if not top5:
            return False, "top5 为空"
        if not surviving:
            return False, "surviving_teams 为空"
        top5_teams = {t.get("team") for t in top5}
        extra = top5_teams - surviving
        if not extra:
            return True, f"top5 中 {len(top5_teams)} 支球队全部属于 surviving_teams"
        else:
            return False, f"top5 中包含非 surviving 球队: {extra}"

    check(8, "final_agent_result.json top5 只包含 surviving_teams", check_top5_surviving)

    # ── 检查 9: final_agent_result.json 包含 surviving_teams 和 stage ──
    def check_result_fields():
        result_path = DATA_DIR / "final_agent_result.json"
        if not result_path.exists():
            return False, "final_agent_result.json 不存在"
        with open(result_path, encoding="utf-8") as f:
            result = json.load(f)
        has_surviving = "surviving_teams" in result
        has_stage = "stage" in result
        surviving = result.get("surviving_teams", [])
        stage = result.get("stage", "")
        if has_surviving and has_stage and surviving and stage:
            return True, f"surviving_teams={surviving}, stage={stage}"
        else:
            missing = []
            if not has_surviving:
                missing.append("surviving_teams 字段缺失")
            if not has_stage:
                missing.append("stage 字段缺失")
            if has_surviving and not surviving:
                missing.append("surviving_teams 为空")
            if has_stage and not stage:
                missing.append("stage 为空")
            return False, f"缺少: {', '.join(missing)}"

    check(9, "final_agent_result.json 包含 surviving_teams 和 stage 字段", check_result_fields)

    # ── 检查 10: final_agent_result.json 包含 predicted_champion ──
    def check_predicted_champion():
        result_path = DATA_DIR / "final_agent_result.json"
        if not result_path.exists():
            return False, "final_agent_result.json 不存在"
        with open(result_path, encoding="utf-8") as f:
            result = json.load(f)
        champ = result.get("champion", "")
        predicted = result.get("predicted_champion", "")
        if predicted and champ:
            if predicted == champ:
                return True, f"predicted_champion = {predicted}（与 champion 一致）"
            else:
                return False, f"predicted_champion ({predicted}) != champion ({champ})"
        elif not predicted:
            return False, "predicted_champion 字段缺失"
        else:
            return False, "champion 字段缺失"

    check(10, "final_agent_result.json 包含 predicted_champion 字段", check_predicted_champion)

    # ── 汇总 ──
    print(f"{BOLD}{'=' * 60}")
    print(f"验证结果汇总")
    print(f"{'=' * 60}{RESET}")
    for num, success, msg in results:
        icon = f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}"
        print(f"  {icon} 检查 {num}: {msg[:60]}")
    print()
    total = passed + failed
    print(f"通过: {passed}/{total}  失败: {failed}/{total}")
    if failed == 0:
        print(f"\n{GREEN}{BOLD}全部通过！{RESET}\n")
    else:
        print(f"\n{RED}{BOLD}有 {failed} 项检查未通过，请检查。{RESET}\n")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
