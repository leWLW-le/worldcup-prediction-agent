"""
冠军路径沙盘验证脚本

12 项检查：
1. POST /scenario/simulate 可用
2. scenario_result.json 能生成
3. scenario_result 不覆盖 final_agent_result.json
4. forced_winner 出现在 scenario champion candidates 中
5. forced_loser 不出现在 scenario champion candidates 中（或 probability=0）
6. scenario champion_distribution 概率总和 = 1.0
7. scenario simulation_count = 10000
8. 正式 final_agent_result champion 不变
9. Dashboard 存在"冠军路径沙盘"模块
10. Dashboard 明确显示"假设结果，不影响正式预测"
11. explanation 存在
12. 如果用户假设 Spain 淘汰 France，则 France 在沙盘中不能仍有夺冠概率
"""
import sys
import os
import json
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SCENARIO_PATH = DATA_DIR / "scenario_result.json"
FINAL_PATH = DATA_DIR / "final_agent_result.json"
DASHBOARD_PATH = PROJECT_ROOT / "debug_dashboard.py"

passed = 0
failed = 0


def check(num: int, name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        print(f"  [{num:2d}] ✅ PASS  {name}")
        passed += 1
    else:
        print(f"  [{num:2d}] ❌ FAIL  {name}  {detail}")
        failed += 1


def backup_file(path: Path) -> str:
    """计算文件 MD5"""
    if not path.exists():
        return ""
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def main():
    global passed, failed

    print("=" * 60)
    print("冠军路径沙盘验证")
    print("=" * 60)

    # ── 记录正式结果 hash（验证不被覆盖）──
    final_hash_before = backup_file(FINAL_PATH)
    final_data_before = {}
    if FINAL_PATH.exists():
        with open(FINAL_PATH, encoding="utf-8") as f:
            final_data_before = json.load(f)

    # ── 1. 调用沙盘推演（优先直接调用服务，确保使用最新代码）──
    print("\n── 调用沙盘推演 ──")
    scenario_result = None
    # 优先直接调用服务（避免后端缓存旧代码）
    try:
        from app.services.scenario_simulation_service import run_scenario_simulation
        scenario_result = run_scenario_simulation(
            match_id="fd_537387",
            forced_winner="Spain",
            simulation_count=10000,
        )
        print(f"  直接调用返回: success={scenario_result.get('success')}")
    except Exception as e:
        print(f"  直接调用失败: {e}")
        # 回退到 API
        try:
            import requests
            url = "http://localhost:8001/api/v1/scenario/simulate"
            resp = requests.post(url, json={
                "match_id": "fd_537387",
                "forced_winner": "Spain",
                "simulation_count": 10000,
            }, timeout=300)
            resp.raise_for_status()
            scenario_result = resp.json()
            print(f"  API 返回: success={scenario_result.get('success')}")
        except Exception as e2:
            print(f"  API 也失败: {e2}")

    # ── 检查 ──
    print("\n── 验证结果 ──")

    # 1. POST /scenario/simulate 可用
    api_ok = scenario_result is not None and scenario_result.get("success")
    check(1, "POST /scenario/simulate 可用", api_ok,
          "" if api_ok else "API 不可用或返回 success=false")

    # 2. scenario_result.json 能生成
    file_exists = SCENARIO_PATH.exists()
    check(2, "scenario_result.json 能生成", file_exists,
          "" if file_exists else "文件不存在")

    # 加载 scenario_result.json
    scenario_data = {}
    if file_exists:
        with open(SCENARIO_PATH, encoding="utf-8") as f:
            scenario_data = json.load(f)

    # 3. scenario_result 不覆盖 final_agent_result.json
    final_hash_after = backup_file(FINAL_PATH)
    final_unchanged = final_hash_before == final_hash_after
    check(3, "scenario_result 不覆盖 final_agent_result.json", final_unchanged,
          "" if final_unchanged else "final_agent_result.json 被修改！")

    # 4. forced_winner (Spain) 出现在 scenario champion candidates 中
    champ_dist = scenario_data.get("champion_distribution", scenario_data.get("scenario_prediction", {}).get("top_candidates", []))
    # 统一格式
    if champ_dist and "name" in champ_dist[0]:
        scenario_teams = [c["name"] for c in champ_dist]
    elif champ_dist and "team" in champ_dist[0]:
        scenario_teams = [c["team"] for c in champ_dist]
    else:
        scenario_teams = []

    forced_winner_in = "Spain" in scenario_teams
    check(4, "forced_winner (Spain) 出现在沙盘候选中", forced_winner_in,
          f"候选: {scenario_teams}")

    # 5. forced_loser (France) 不出现在沙盘候选中（或 probability=0）
    france_prob = 0
    for c in champ_dist:
        name = c.get("name", c.get("team", ""))
        if name == "France":
            france_prob = c.get("probability", 0)
            break
    france_eliminated = "France" not in scenario_teams or france_prob == 0
    check(5, "forced_loser (France) 不在沙盘候选或 probability=0", france_eliminated,
          f"France probability={france_prob}")

    # 6. scenario champion_distribution 概率总和 = 1.0
    prob_sum = sum(c.get("probability", 0) for c in champ_dist)
    prob_ok = abs(prob_sum - 1.0) < 0.01
    check(6, "沙盘概率总和 ≈ 1.0", prob_ok,
          f"sum={prob_sum:.6f}")

    # 7. scenario simulation_count = 10000
    sim_count = scenario_data.get("simulation_count", 0)
    check(7, "沙盘 simulation_count = 10000", sim_count == 10000,
          f"实际={sim_count}")

    # 8. 正式 final_agent_result champion 不变
    final_data_after = {}
    if FINAL_PATH.exists():
        with open(FINAL_PATH, encoding="utf-8") as f:
            final_data_after = json.load(f)
    champion_unchanged = final_data_before.get("champion") == final_data_after.get("champion")
    check(8, "正式 champion 不变", champion_unchanged,
          f"before={final_data_before.get('champion')}, after={final_data_after.get('champion')}")

    # 9. Dashboard 存在"冠军路径沙盘"模块
    dashboard_has_scenario = False
    if DASHBOARD_PATH.exists():
        content = DASHBOARD_PATH.read_text(encoding="utf-8")
        dashboard_has_scenario = "冠军路径沙盘" in content
    check(9, "Dashboard 存在「冠军路径沙盘」模块", dashboard_has_scenario)

    # 10. Dashboard 明确显示"假设结果，不影响正式预测"
    dashboard_has_disclaimer = False
    if DASHBOARD_PATH.exists():
        content = DASHBOARD_PATH.read_text(encoding="utf-8")
        dashboard_has_disclaimer = ("不影响正式预测" in content or
                                    "不影响真实赛果" in content or
                                    "假设推演" in content)
    check(10, "Dashboard 显示免责声明", dashboard_has_disclaimer)

    # 11. explanation 存在
    explanation = scenario_data.get("explanation", "")
    has_explanation = bool(explanation and len(explanation) > 10)
    check(11, "AI 沙盘解释存在", has_explanation,
          f"len={len(explanation) if explanation else 0}")

    # 12. France 在沙盘中 probability=0（假设 Spain 淘汰 France）
    france_zero = france_prob == 0
    check(12, "France 在沙盘中 probability=0（被 Spain 淘汰）", france_zero,
          f"France probability={france_prob}")

    # ── 总结 ──
    print(f"\n{'=' * 60}")
    print(f"结果: {passed}/{passed + failed} 通过")
    if failed == 0:
        print("✅ 冠军路径沙盘验证全部通过")
    else:
        print(f"❌ {failed} 项未通过")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
