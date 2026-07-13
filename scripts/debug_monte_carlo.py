"""
Monte Carlo 模拟诊断脚本

检查:
1. simulation_distribution.json 数据完整性
2. champion_counts 总和 == n_simulations
3. 概率总和 ≈ 1.0
4. final_agent_result.json 是否正确使用 Monte Carlo 概率
5. 单次模拟是否只产生一个冠军
6. Bracket 是否有重复晋级
"""
import sys
import os
import json
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        print(f"  [MISSING] {filename} not found")
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check_simulation_distribution():
    print("=" * 60)
    print("1. 检查 simulation_distribution.json")
    print("=" * 60)

    data = load_json("simulation_distribution.json")
    if not data:
        print("  FAIL: 文件不存在")
        return False

    n_sim = data.get("n_simulations")
    champion_counts = data.get("champion_counts", {})
    champion_probs = data.get("champion", {})

    sum_counts = sum(champion_counts.values())
    sum_probs = sum(champion_probs.values())

    print(f"  n_simulations: {n_sim}")
    print(f"  champion_counts 条目数: {len(champion_counts)}")
    print(f"  champion_counts 总和: {sum_counts}")
    print(f"  概率总和: {sum_probs:.6f}")
    print()

    ok = True

    # 检查 champion_counts 总和 == n_simulations
    if n_sim is not None and sum_counts != n_sim:
        print(f"  FAIL: champion_counts 总和 ({sum_counts}) != n_simulations ({n_sim})")
        print(f"        差值: {sum_counts - n_sim}")
        ok = False
    elif n_sim is None:
        print(f"  WARN: n_simulations 为 None，无法验证总和")
    else:
        print(f"  PASS: champion_counts 总和 ({sum_counts}) == n_simulations ({n_sim})")

    # 检查概率总和 ≈ 1.0
    if abs(sum_probs - 1.0) > 0.01:
        print(f"  FAIL: 概率总和 ({sum_probs:.6f}) 偏离 1.0")
        ok = False
    else:
        print(f"  PASS: 概率总和 ({sum_probs:.6f}) ≈ 1.0")

    # 打印 Top 10
    print()
    print("  Top 10 冠军概率:")
    sorted_probs = sorted(champion_probs.items(), key=lambda x: -x[1])
    for i, (team, prob) in enumerate(sorted_probs[:10]):
        count = champion_counts.get(team, 0)
        print(f"    {i+1}. {team}: {prob:.4f} ({prob*100:.2f}%) [count={count}]")

    return ok


def check_single_sim_one_champion():
    print()
    print("=" * 60)
    print("2. 检查单次模拟是否只产生一个冠军")
    print("=" * 60)

    data = load_json("simulation_distribution.json")
    if not data:
        print("  SKIP: simulation_distribution.json 不存在")
        return True

    n_sim = data.get("n_simulations", 10000)
    champion_counts = data.get("champion_counts", {})
    sum_counts = sum(champion_counts.values())

    if sum_counts == n_sim:
        print(f"  PASS: {n_sim} 次模拟产生 {sum_counts} 个冠军 (1:1)")
        return True
    else:
        print(f"  FAIL: {n_sim} 次模拟产生 {sum_counts} 个冠军")
        ratio = sum_counts / n_sim if n_sim > 0 else 0
        print(f"        比率: {ratio:.4f} (应为 1.0)")
        if ratio > 1.0:
            print(f"        说明: 单次模拟产生了多个冠军!")
        return False


def check_final_agent_result():
    print()
    print("=" * 60)
    print("3. 检查 final_agent_result.json 是否使用 Monte Carlo 概率")
    print("=" * 60)

    far = load_json("final_agent_result.json")
    sim = load_json("simulation_distribution.json")

    if not far:
        print("  FAIL: final_agent_result.json 不存在")
        return False
    if not sim:
        print("  SKIP: simulation_distribution.json 不存在")
        return True

    mc_champion = sim.get("champion", {})
    far_top5 = far.get("top5", [])
    far_champ_prob = far.get("champion_probability", 0)
    far_champ = far.get("champion", "")

    ok = True

    print(f"  final_agent_result 冠军: {far_champ}")
    print(f"  final_agent_result champion_probability: {far_champ_prob}")
    print()

    # 检查 top5 是否匹配 Monte Carlo
    print("  Top 5 对比:")
    print(f"  {'球队':<20} {'final_result':>12} {'Monte Carlo':>12} {'匹配':>6}")
    print(f"  {'-'*52}")

    mc_sorted = sorted(mc_champion.items(), key=lambda x: -x[1])[:5]
    for i, (mc_team, mc_prob) in enumerate(mc_sorted):
        far_match = None
        for t in far_top5:
            if t.get("team") == mc_team:
                far_match = t.get("probability", 0)
                break
        far_str = f"{far_match:.4f}" if far_match is not None else "N/A"
        match_str = "OK" if (far_match is not None and abs(far_match - mc_prob) < 0.001) else "MISMATCH"
        if match_str == "MISMATCH":
            ok = False
        print(f"  {mc_team:<20} {far_str:>12} {mc_prob:>12.4f} {match_str:>6}")

    # 检查 champion_probability 是否来自 Monte Carlo
    if far_champ in mc_champion:
        expected_prob = mc_champion[far_champ]
        if abs(far_champ_prob - expected_prob) < 0.001:
            print(f"\n  PASS: champion_probability ({far_champ_prob}) 匹配 Monte Carlo ({expected_prob})")
        else:
            print(f"\n  FAIL: champion_probability ({far_champ_prob}) 不匹配 Monte Carlo ({expected_prob})")
            ok = False
    else:
        print(f"\n  WARN: 冠军 {far_champ} 不在 Monte Carlo 数据中")

    # 检查 top5 概率总和
    top5_sum = sum(t.get("probability", 0) for t in far_top5)
    print(f"\n  top5 概率总和: {top5_sum:.4f}")
    if top5_sum > 1.01:
        print(f"  FAIL: top5 概率总和 > 1.0，可能存在重复累加")
        ok = False
    else:
        print(f"  PASS: top5 概率总和 <= 1.0")

    return ok


def check_bracket_duplicates():
    print()
    print("=" * 60)
    print("4. 检查 Bracket 是否有重复晋级")
    print("=" * 60)

    far = load_json("final_agent_result.json")
    if not far:
        print("  SKIP: final_agent_result.json 不存在")
        return True

    bp = far.get("bracket_payload", {})
    if not bp:
        print("  SKIP: bracket_payload 为空")
        return True

    rounds_config = {
        "round_of_32": 32,
        "round_of_16": 16,
        "quarter_finals": 8,
        "semi_finals": 4,
        "final": 2,
    }

    ok = True
    for round_name, expected_teams in rounds_config.items():
        matches = bp.get(round_name, [])
        teams = []
        for m in matches:
            h = m.get("home_team", "")
            a = m.get("away_team", "")
            if h:
                teams.append(h)
            if a:
                teams.append(a)

        seen = set()
        dupes = []
        for t in teams:
            if t in seen:
                dupes.append(t)
            seen.add(t)

        n = len(teams)
        if dupes:
            print(f"  FAIL: {round_name} 有重复球队: {dupes}")
            ok = False
        elif n != expected_teams:
            print(f"  WARN: {round_name} 球队数 {n} != 预期 {expected_teams}")
        else:
            print(f"  PASS: {round_name} {len(matches)} 场, {n} 支球队, 无重复")

    return ok


def check_probability_sum():
    print()
    print("=" * 60)
    print("5. 全局概率总和验证")
    print("=" * 60)

    sim = load_json("simulation_distribution.json")
    if not sim:
        print("  SKIP")
        return True

    champion_probs = sim.get("champion", {})
    total = sum(champion_probs.values())
    n = sim.get("n_simulations", 10000)

    print(f"  模拟次数: {n}")
    print(f"  冠军概率总和: {total:.6f}")
    print(f"  参赛球队数: {len(champion_probs)}")

    if abs(total - 1.0) < 0.01:
        print(f"  PASS: 概率总和 ≈ 1.0")
        return True
    else:
        print(f"  FAIL: 概率总和 ({total:.6f}) 偏离 1.0 超过 1%")
        return False


def main():
    print()
    print("Monte Carlo 模拟诊断报告")
    print("=" * 60)
    print()

    results = {}
    results["simulation_distribution"] = check_simulation_distribution()
    results["single_champion"] = check_single_sim_one_champion()
    results["final_agent_result"] = check_final_agent_result()
    results["bracket_duplicates"] = check_bracket_duplicates()
    results["probability_sum"] = check_probability_sum()

    print()
    print("=" * 60)
    print("诊断汇总")
    print("=" * 60)
    all_pass = True
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  {name}: {status}")

    print()
    if all_pass:
        print("所有检查通过!")
    else:
        print("存在失败项，请检查上方详情。")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
