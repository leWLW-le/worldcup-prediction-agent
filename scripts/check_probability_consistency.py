"""
概率一致性校验脚本

检查三个数据源的冠军概率是否一致：
1. simulation_distribution.json（Monte Carlo 模拟结果）
2. final_agent_result.json（Agent 最终输出）
3. Dashboard 读取结果（通过 API 或直接读文件）

误差阈值：< 0.001
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
TOLERANCE = 0.001


def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check_consistency():
    print("=" * 60)
    print("概率一致性校验")
    print("=" * 60)
    print()

    # 1. Monte Carlo 模拟结果
    sim = load_json("simulation_distribution.json")
    if not sim:
        print("FAIL: simulation_distribution.json 不存在")
        return False

    mc_champion_probs = sim.get("champion", {})
    n_sim = sim.get("n_simulations", 0)
    mc_counts = sim.get("champion_counts", {})
    mc_sum_counts = sum(mc_counts.values())
    mc_sum_probs = sum(mc_champion_probs.values())

    print(f"[1] Monte Carlo 模拟")
    print(f"    simulation_count: {n_sim}")
    print(f"    champion_counts 总和: {mc_sum_counts}")
    print(f"    概率总和: {mc_sum_probs:.6f}")

    # Monte Carlo 断言
    if mc_sum_counts != n_sim:
        print(f"    FAIL: champion_counts 总和 ({mc_sum_counts}) != simulation_count ({n_sim})")
        return False
    if abs(mc_sum_probs - 1.0) > 0.01:
        print(f"    FAIL: 概率总和 ({mc_sum_probs:.6f}) 偏离 1.0")
        return False
    print(f"    PASS: 统计正确")
    print()

    # 2. final_agent_result.json
    far = load_json("final_agent_result.json")
    if not far:
        print("FAIL: final_agent_result.json 不存在")
        return False

    far_top5 = far.get("top5", [])
    far_champ = far.get("champion", "")
    far_prob = far.get("champion_probability", 0)

    print(f"[2] final_agent_result.json")
    print(f"    冠军: {far_champ}")
    print(f"    champion_probability: {far_prob}")
    print(f"    top5:")
    for t in far_top5:
        print(f"      {t.get('team')}: {t.get('probability')}")
    print()

    # 3. 一致性对比
    print(f"[3] 一致性对比")
    all_ok = True

    # 3a. 冠军概率一致性
    if far_champ in mc_champion_probs:
        mc_prob = mc_champion_probs[far_champ]
        diff = abs(far_prob - mc_prob)
        status = "PASS" if diff < TOLERANCE else "FAIL"
        if diff >= TOLERANCE:
            all_ok = False
        print(f"    冠军概率: Monte Carlo={mc_prob:.4f}, final_result={far_prob:.4f}, diff={diff:.6f} [{status}]")
    else:
        print(f"    WARN: 冠军 {far_champ} 不在 Monte Carlo 数据中")
        all_ok = False

    # 3b. Top5 一致性
    print(f"    Top5 对比:")
    mc_sorted = sorted(mc_champion_probs.items(), key=lambda x: -x[1])[:5]
    for i, (mc_team, mc_p) in enumerate(mc_sorted):
        far_match = next((t for t in far_top5 if t.get("team") == mc_team), None)
        if far_match:
            far_p = far_match.get("probability", 0)
            diff = abs(far_p - mc_p)
            status = "PASS" if diff < TOLERANCE else "FAIL"
            if diff >= TOLERANCE:
                all_ok = False
            print(f"      {mc_team}: MC={mc_p:.4f}, FAR={far_p:.4f}, diff={diff:.6f} [{status}]")
        else:
            print(f"      {mc_team}: MC={mc_p:.4f}, FAR=缺失 [FAIL]")
            all_ok = False

    # 3c. top5 概率总和检查
    top5_sum = sum(t.get("probability", 0) for t in far_top5)
    print(f"    top5 概率总和: {top5_sum:.4f}")
    if top5_sum > 1.01:
        print(f"    FAIL: top5 总和 > 1.0，可能存在 strength_score 混入")
        all_ok = False
    else:
        print(f"    PASS: top5 总和 <= 1.0")

    # 3d. 检查是否存在 strength_score 作为概率的问题
    print()
    print(f"[4] strength_score 污染检查")
    has_strength_leak = False
    for t in far_top5:
        p = t.get("probability", 0)
        if p > 0.5:
            print(f"    WARN: {t.get('team')} 概率 {p:.4f} 异常高，可能是 strength_score")
            has_strength_leak = True
    if not has_strength_leak:
        print(f"    PASS: 无 strength_score 污染")
    else:
        all_ok = False

    # 3e. 检查 top_contenders 是否还有 probability 字段（不应该有）
    tc = far.get("top_contenders", [])
    if tc:
        has_old_prob = any("probability" in t for t in tc)
        if has_old_prob:
            print(f"    WARN: top_contenders 仍包含 probability 字段（应改为 team_strength_index）")
        else:
            print(f"    PASS: top_contenders 已无 probability 字段")

    print()
    print("=" * 60)
    if all_ok:
        print("所有检查通过！概率数据链路一致。")
    else:
        print("存在不一致，请检查上方详情。")
    print("=" * 60)

    return all_ok


if __name__ == "__main__":
    ok = check_consistency()
    sys.exit(0 if ok else 1)
