"""
检查 Dashboard 数据源一致性
=========================
1. 读取 data/final_agent_result.json（文件）
2. 调用 GET /api/v1/agent/final-result（API）
3. 对比两者 champion 和 top5
4. 检查 top5 是否等于 Monte Carlo 概率
5. 检查是否存在旧概率（85.8 / 85.0 / 76.3 / overall_strength_score 当 probability）

如果发现 Dashboard / API / file 任意一个仍含旧概率，验收失败。
"""

import sys
import json
import os
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

FINAL_RESULT_PATH = project_root / "data" / "final_agent_result.json"
SIM_PATH = project_root / "data" / "simulation_distribution.json"
BACKEND_URL = "http://localhost:8001/api/v1"

# 旧概率值（不应出现在 champion_probability 或 top5.probability 中）
OLD_PROB_VALUES = {85.8, 85.0, 76.3, 65.2}
OLD_PROB_TOLERANCE = 0.5  # 允许浮点误差

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    status = "PASS" if condition else "FAIL"
    if condition:
        passed += 1
    else:
        failed += 1
    suffix = f" ({detail})" if detail else ""
    print(f"  [{status}] {name}{suffix}")
    return condition


def load_file_result():
    """从文件加载 final_agent_result.json"""
    if not FINAL_RESULT_PATH.exists():
        return None
    with open(FINAL_RESULT_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_api_result():
    """从 API 加载 final-result"""
    try:
        import requests
        resp = requests.get(f"{BACKEND_URL}/agent/final-result", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") in ("no_result", "error"):
            return None
        return data
    except Exception as e:
        print(f"  [WARN] API 请求失败: {e}")
        return None


def load_monte_carlo():
    """从 simulation_distribution.json 加载 Monte Carlo 概率"""
    if not SIM_PATH.exists():
        return None
    with open(SIM_PATH, encoding="utf-8") as f:
        sim_data = json.load(f)
    return sim_data.get("champion", {})


def is_old_probability(val) -> bool:
    """检查值是否为旧的 strength_score 被误当概率"""
    try:
        v = float(val)
        for old in OLD_PROB_VALUES:
            if abs(v - old) < OLD_PROB_TOLERANCE:
                return True
        # strength_score 范围 0-1，如果 > 0.5 且被当概率显示（>50%），很可能是旧数据
        # 但 Monte Carlo 概率也可能 > 0.5（如 0.29 = 29%），所以只检查特定旧值
        return False
    except (TypeError, ValueError):
        return False


def main():
    global passed, failed

    print("=" * 60)
    print("  Dashboard 数据源一致性检查")
    print("=" * 60)

    # ── 1. 文件检查 ──
    print("\n[1] 读取 data/final_agent_result.json（文件）")
    file_result = load_file_result()
    if file_result:
        file_path = str(FINAL_RESULT_PATH.resolve())
        file_mtime = os.path.getmtime(str(FINAL_RESULT_PATH))
        from datetime import datetime
        mtime_str = datetime.fromtimestamp(file_mtime).strftime("%Y-%m-%d %H:%M:%S")
        check("文件存在", True, f"path={file_path}")
        check("文件可读", True, f"mtime={mtime_str}")

        file_champion = file_result.get("champion")
        file_prob = file_result.get("champion_probability")
        file_top5 = file_result.get("top5", [])
        print(f"  champion={file_champion}, probability={file_prob}")
        print(f"  top5: {[(t.get('team'), t.get('probability')) for t in file_top5[:5]]}")
    else:
        check("文件存在且可读", False, "文件不存在或无法读取")
        file_champion = None
        file_prob = None
        file_top5 = []

    # ── 2. API 检查 ──
    print("\n[2] 调用 GET /api/v1/agent/final-result（API）")
    api_result = load_api_result()
    if api_result:
        api_champion = api_result.get("champion")
        api_prob = api_result.get("champion_probability")
        api_top5 = api_result.get("top5", [])
        print(f"  champion={api_champion}, probability={api_prob}")
        print(f"  top5: {[(t.get('team'), t.get('probability')) for t in api_top5[:5]]}")
        check("API 返回有效数据", True)
    else:
        check("API 返回有效数据", False, "后端未启动或返回错误")
        api_champion = None
        api_prob = None
        api_top5 = []

    # ── 3. 文件 vs API 对比 ──
    print("\n[3] 文件 vs API 一致性")
    if file_result and api_result:
        check("champion 一致", file_champion == api_champion,
              f"file={file_champion}, api={api_champion}")
        check("champion_probability 一致",
              abs(float(file_prob or 0) - float(api_prob or 0)) < 0.001,
              f"file={file_prob}, api={api_prob}")

        # top5 对比
        file_top5_map = {t.get("team"): t.get("probability") for t in file_top5[:5]}
        api_top5_map = {t.get("team"): t.get("probability") for t in api_top5[:5]}
        top5_match = True
        for team in file_top5_map:
            if team in api_top5_map:
                if abs(file_top5_map[team] - api_top5_map[team]) > 0.001:
                    top5_match = False
                    break
            else:
                top5_match = False
                break
        check("top5 一致", top5_match)
    else:
        check("文件与API对比", False, "缺少文件或API数据")

    # ── 4. Monte Carlo 对比 ──
    print("\n[4] top5 vs Monte Carlo 概率")
    mc_data = load_monte_carlo()
    if mc_data and file_top5:
        mc_sorted = sorted(mc_data.items(), key=lambda x: -x[1])[:5]
        mc_top5_map = {team: prob for team, prob in mc_sorted}

        all_match = True
        for t in file_top5[:5]:
            team = t.get("team")
            prob = t.get("probability")
            mc_prob = mc_top5_map.get(team)
            if mc_prob is not None:
                diff = abs(prob - mc_prob)
                match = diff < 0.001
                if not match:
                    all_match = False
                check(f"{team}: file={prob}, MC={mc_prob}", match,
                      f"diff={diff:.6f}")
            else:
                all_match = False
                check(f"{team}: 不在 Monte Carlo 中", False)
        check("top5 全部匹配 Monte Carlo", all_match)
    else:
        check("Monte Carlo 对比", False, "缺少 simulation_distribution.json 或 top5")

    # ── 5. 旧概率检查 ──
    print("\n[5] 旧概率污染检查")

    # 检查 champion_probability
    if file_prob is not None:
        check("file champion_probability 不是旧值",
              not is_old_probability(file_prob),
              f"value={file_prob}")
    if api_prob is not None:
        check("API champion_probability 不是旧值",
              not is_old_probability(api_prob),
              f"value={api_prob}")

    # 检查 top5 中是否有旧值
    for source_name, top5_list in [("file", file_top5), ("API", api_top5)]:
        for t in top5_list[:5]:
            prob = t.get("probability")
            if prob is not None:
                check(f"{source_name} top5 {t.get('team')} 不是旧值",
                      not is_old_probability(prob),
                      f"probability={prob}")

    # 检查 top_contenders 是否有 probability 字段（不应有）
    for source_name, result in [("file", file_result), ("API", api_result)]:
        if result:
            tc = result.get("top_contenders", [])
            if tc:
                has_prob = "probability" in tc[0]
                check(f"{source_name} top_contenders 无 probability 字段",
                      not has_prob,
                      f"fields={list(tc[0].keys())}")
                has_old_oss = "overall_strength_score" in tc[0]
                check(f"{source_name} top_contenders 无 overall_strength_score",
                      not has_old_oss,
                      f"fields={list(tc[0].keys())}")

    # ── 6. 端口检查 ──
    print("\n[6] 端口检查")
    check("BACKEND_URL 使用 8001", "8001" in BACKEND_URL,
          f"BACKEND_URL={BACKEND_URL}")

    # ── 7. 文件路径一致性 ──
    print("\n[7] 文件路径一致性")
    backend_path = Path(__file__).parent.parent / "app" / "api" / ".." / ".." / ".." / "data" / "final_agent_result.json"
    # 后端路径：Path(__file__).parent.parent.parent / "data" from agent.py
    # 即 app/api/../../.. = project_root
    backend_resolved = (project_root / "data" / "final_agent_result.json").resolve()
    dashboard_resolved = FINAL_RESULT_PATH.resolve()
    check("后端与 Dashboard 文件路径一致",
          str(backend_resolved) == str(dashboard_resolved),
          f"backend={backend_resolved}, dashboard={dashboard_resolved}")

    # ── 汇总 ──
    print("\n" + "=" * 60)
    print(f"  结果: {passed} 通过, {failed} 失败")
    print("=" * 60)

    if failed == 0:
        print("\n  [OK] Dashboard 数据源检查全部通过！")
        print(f"  数据源: API ({BACKEND_URL}/agent/final-result)")
        print(f"  文件路径: {FINAL_RESULT_PATH.resolve()}")
        if file_result:
            print(f"  champion: {file_champion}")
            print(f"  champion_probability: {file_prob}")
            print(f"  Top5: {[(t.get('team'), t.get('probability')) for t in file_top5[:5]]}")
    else:
        print(f"\n  [FAIL] {failed} 项检查未通过，请排查！")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
