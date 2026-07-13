"""
冠军展示一致性检查脚本
检查 Monte Carlo Top1、final_agent_result.json、Dashboard 逻辑的一致性。

检查项：
1. simulation_distribution.json 的 Monte Carlo Top1
2. final_agent_result.json 的 champion 字段
3. final_agent_result.json 的 top5[0] 与 champion 一致
4. final_agent_result.json 的 predicted_champion 与 champion 一致
5. explanation 标题包含 champion 名
6. debug_dashboard.py 不包含调试信息字符串
7. champion 不是 France（除非 Monte Carlo 确实预测 France）
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DASHBOARD_PATH = PROJECT_ROOT / "debug_dashboard.py"

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        msg = f"  [FAIL] {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)


def main():
    global PASS, FAIL

    print("=" * 60)
    print("  冠军展示一致性检查")
    print("=" * 60)

    # ── 1. Monte Carlo Top1 ──
    print("\n[1] Monte Carlo 模拟数据")
    sim_path = DATA_DIR / "simulation_distribution.json"
    if not sim_path.exists():
        check("simulation_distribution.json 存在", False, "文件不存在")
        print("\n无法继续，缺少 simulation_distribution.json")
        sys.exit(1)

    with open(sim_path, encoding="utf-8") as f:
        sim_data = json.load(f)

    mc_champion_dict = sim_data.get("champion", {})
    if not mc_champion_dict:
        check("Monte Carlo champion 数据非空", False)
    else:
        mc_top1_team = max(mc_champion_dict, key=mc_champion_dict.get)
        mc_top1_prob = mc_champion_dict[mc_top1_team]
        check("Monte Carlo Top1 球队", True, f"{mc_top1_team} ({mc_top1_prob*100:.2f}%)")
        print(f"       Monte Carlo Top1: {mc_top1_team} = {mc_top1_prob*100:.2f}%")

    # ── 2. final_agent_result.json ──
    print("\n[2] final_agent_result.json")
    result_path = DATA_DIR / "final_agent_result.json"
    if not result_path.exists():
        check("final_agent_result.json 存在", False, "文件不存在")
        print("\n无法继续，缺少 final_agent_result.json")
        sys.exit(1)

    with open(result_path, encoding="utf-8") as f:
        result = json.load(f)

    champion = result.get("champion", "")
    champion_prob = result.get("champion_probability", 0)
    predicted_champion = result.get("predicted_champion", "")
    top5 = result.get("top5", [])

    check("champion 字段非空", bool(champion), f"champion='{champion}'")
    check(
        "champion == Monte Carlo Top1",
        champion == mc_top1_team,
        f"champion='{champion}', MC Top1='{mc_top1_team}'",
    )

    # ── 3. top5[0] 与 champion 一致 ──
    print("\n[3] Top5 一致性")
    if top5:
        top1_team = top5[0].get("team", "")
        top1_prob = top5[0].get("probability", 0)
        check(
            "top5[0].team == champion",
            top1_team == champion,
            f"top5[0]='{top1_team}', champion='{champion}'",
        )
        prob_diff = abs(top1_prob - champion_prob)
        check(
            "top5[0].probability ≈ champion_probability",
            prob_diff < 0.01,
            f"top5[0].prob={top1_prob}, champion_prob={champion_prob}, diff={prob_diff:.4f}",
        )
        print(f"       Top5: {', '.join(f'{t.get('team','?')}={t.get('probability',0)*100:.1f}%' for t in top5[:5])}")
    else:
        check("top5 非空", False, "top5 为空列表")

    # ── 4. predicted_champion 与 champion 一致 ──
    print("\n[4] predicted_champion 一致性")
    check(
        "predicted_champion == champion",
        predicted_champion == champion,
        f"predicted_champion='{predicted_champion}', champion='{champion}'",
    )

    # ── 5. explanation 标题包含 champion 名 ──
    print("\n[5] Explanation 标题检查")
    explanation = result.get("explanation", {})
    if isinstance(explanation, dict):
        title = explanation.get("title", "")
        check(
            "explanation.title 包含 champion 名",
            champion in title,
            f"title='{title}', champion='{champion}'",
        )
        # 检查标题不包含非冠军球队作为夺冠主体
        if top5 and len(top5) > 1:
            for t in top5[1:]:
                other_team = t.get("team", "")
                if other_team and f"预测 {other_team} 夺冠" in title:
                    check(
                        f"标题不含非冠军球队 '{other_team}' 作为夺冠主体",
                        False,
                        f"title='{title}' 包含 '{other_team}'",
                    )
                    break
            else:
                check("标题不含非冠军球队作为夺冠主体", True)
    else:
        check("explanation 是 dict", False, f"explanation 类型={type(explanation).__name__}")

    # ── 6. debug_dashboard.py 不包含调试信息字符串 ──
    print("\n[6] Dashboard 调试信息清理检查")
    if not DASHBOARD_PATH.exists():
        check("debug_dashboard.py 存在", False, "文件不存在")
    else:
        with open(DASHBOARD_PATH, encoding="utf-8") as f:
            dashboard_code = f.read()

        forbidden_strings = [
            "数据来源调试信息",
            "source debug",
            "raw json",
            "_display_debug_info",
            "_get_file_debug_info",
            "_check_old_fields",
            "_record_data_source",
            "file_mtime",
            "BACKEND_URL：",  # 只检查展示用的标签，不检查变量名
        ]
        for s in forbidden_strings:
            check(
                f"dashboard 不含 '{s}'",
                s.lower() not in dashboard_code.lower(),
                f"发现 '{s}'" if s.lower() in dashboard_code.lower() else "",
            )

    # ── 7. champion 不是 France（除非 MC 确实预测 France）──
    print("\n[7] 冠军非 France 检查")
    if mc_top1_team == "France":
        check("Monte Carlo Top1 是 France（合法）", True, "MC 确实预测 France 夺冠")
    else:
        check(
            "champion 不是 France",
            champion != "France",
            f"champion='{champion}'",
        )

    # ── 总结 ──
    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"  结果: {PASS}/{total} 通过, {FAIL}/{total} 失败")
    if FAIL == 0:
        print("  ✅ 所有检查通过！冠军展示一致性验证成功。")
    else:
        print(f"  ❌ 有 {FAIL} 项检查失败，请修复后重新运行。")
    print("=" * 60)

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
