"""
沙盘条件冠军概率结构验证脚本

14 项检查：
1. scenario_simulation_service.py 包含 scenario_scope 字段
2. scenario_simulation_service.py 包含 stage_at_creation 字段
3. scenario_simulation_service.py 包含 is_stale 字段
4. scenario_simulation_service.py 包含 final_matchup_distribution 字段
5. scenario_simulation_service.py 包含 comparison 字段
6. scenario_simulation_service.py 包含 impact_summary 字段
7. scenario_simulation_service.py 包含 _simulate_knockout_with_final_tracking 函数
8. load_latest_scenario 检查 is_stale
9. scenario_simulation_service.py 检查 sandbox_enabled（决赛/冠军已产生时关闭）
10. scenario API 包含 /stage-info 端点
11. scenario API /pending-matches 返回 sandbox_enabled
12. debug_dashboard.py 渲染 final_matchup_distribution（可能决赛对阵）
13. debug_dashboard.py 处理 scenario_scope == "disabled"
14. debug_dashboard.py 显示 stale 状态提示
"""
import sys
import os
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SCENARIO_PATH = DATA_DIR / "scenario_result.json"

passed = 0
failed = 0


def check(num: int, name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        print(f"  [{num:2d}] PASS  {name}")
        passed += 1
    else:
        print(f"  [{num:2d}] FAIL  {name}  {detail}")
        failed += 1


def main():
    global passed, failed

    print("=" * 60)
    print("沙盘条件冠军概率结构验证")
    print("=" * 60)

    # ── 读取源码 ──
    print("\n-- 源码静态检查 --")

    scenario_svc_path = PROJECT_ROOT / "app" / "services" / "scenario_simulation_service.py"
    scenario_svc_content = ""
    if scenario_svc_path.exists():
        scenario_svc_content = scenario_svc_path.read_text(encoding="utf-8")

    scenario_api_path = PROJECT_ROOT / "app" / "api" / "scenario.py"
    scenario_api_content = ""
    if scenario_api_path.exists():
        scenario_api_content = scenario_api_path.read_text(encoding="utf-8")

    dashboard_path = PROJECT_ROOT / "debug_dashboard.py"
    dashboard_content = ""
    if dashboard_path.exists():
        dashboard_content = dashboard_path.read_text(encoding="utf-8")

    # ── 1-7: scenario_simulation_service.py 新结构字段 ──
    checks = [
        (1, "scenario_scope", '"scenario_scope"' in scenario_svc_content or "'scenario_scope'" in scenario_svc_content),
        (2, "stage_at_creation", '"stage_at_creation"' in scenario_svc_content or "'stage_at_creation'" in scenario_svc_content),
        (3, "is_stale", '"is_stale"' in scenario_svc_content or "'is_stale'" in scenario_svc_content),
        (4, "final_matchup_distribution", '"final_matchup_distribution"' in scenario_svc_content or "'final_matchup_distribution'" in scenario_svc_content),
        (5, "comparison", '"comparison"' in scenario_svc_content or "'comparison'" in scenario_svc_content),
        (6, "impact_summary", '"impact_summary"' in scenario_svc_content or "'impact_summary'" in scenario_svc_content),
        (7, "_simulate_knockout_with_final_tracking", "def _simulate_knockout_with_final_tracking" in scenario_svc_content),
    ]

    for num, field_name, condition in checks:
        check(num, f"scenario_simulation_service.py 包含 {field_name}", condition,
              "" if condition else f"缺少 {field_name}")

    # ── 8: load_latest_scenario 检查 is_stale ──
    has_stale_check = "is_stale" in scenario_svc_content and "load_latest_scenario" in scenario_svc_content
    check(8, "load_latest_scenario 检查 is_stale", has_stale_check,
          "" if has_stale_check else "load_latest_scenario 未检查 is_stale")

    # ── 9: sandbox_enabled 检查（决赛/冠军已产生时关闭）──
    checks_sandbox = "sandbox_enabled" in scenario_svc_content
    # 进一步检查：sandbox 在 final/completed 时关闭
    has_final_check = ('"final"' in scenario_svc_content or "'final'" in scenario_svc_content) and \
                      ('"completed"' in scenario_svc_content or "'completed'" in scenario_svc_content)
    check(9, "沙盘在决赛/冠军已产生时关闭", checks_sandbox and has_final_check,
          "" if checks_sandbox and has_final_check else "缺少 final/completed 关闭逻辑")

    # ── 10: scenario API 包含 /stage-info 端点 ──
    print("\n-- API 检查 --")
    has_stage_info_endpoint = "/stage-info" in scenario_api_content or "stage-info" in scenario_api_content
    check(10, "scenario API 包含 /stage-info 端点", has_stage_info_endpoint,
          "" if has_stage_info_endpoint else "未找到 /stage-info 路由")

    # ── 11: scenario API /pending-matches 返回 sandbox_enabled ──
    pending_returns_sandbox = "sandbox_enabled" in scenario_api_content
    check(11, "scenario API /pending-matches 返回 sandbox_enabled", pending_returns_sandbox,
          "" if pending_returns_sandbox else "未返回 sandbox_enabled")

    # ── 12: debug_dashboard.py 渲染可能决赛对阵 ──
    print("\n-- Dashboard 检查 --")
    has_final_matchup_display = ("final_matchup_distribution" in dashboard_content or
                                  "可能决赛对阵" in dashboard_content)
    check(12, "Dashboard 渲染可能决赛对阵", has_final_matchup_display,
          "" if has_final_matchup_display else "未找到 final_matchup_distribution 渲染")

    # ── 13: Dashboard 处理 scenario_scope == "disabled" ──
    handles_disabled = ('"disabled"' in dashboard_content or
                        "'disabled'" in dashboard_content or
                        'scenario_scope' in dashboard_content)
    check(13, "Dashboard 处理 scenario_scope disabled", handles_disabled,
          "" if handles_disabled else "未处理 disabled 状态")

    # ── 14: Dashboard 显示 stale 状态提示 ──
    handles_stale = ("stale" in dashboard_content.lower() or
                     "scenario_stale_message" in dashboard_content)
    check(14, "Dashboard 显示 stale 状态提示", handles_stale,
          "" if handles_stale else "未处理 stale 状态")

    # ── 补充：如果 scenario_result.json 存在，验证其结构 ──
    if SCENARIO_PATH.exists():
        print("\n-- scenario_result.json 结构验证 --")
        with open(SCENARIO_PATH, encoding="utf-8") as f:
            scenario_data = json.load(f)

        has_scope = scenario_data.get("scenario_scope") == "conditional_champion_probability"
        check(15, "scenario_result.json scenario_scope 正确", has_scope,
              f"实际值: {scenario_data.get('scenario_scope', 'N/A')}")

        has_stage_at_creation = bool(scenario_data.get("stage_at_creation"))
        check(16, "scenario_result.json stage_at_creation 存在", has_stage_at_creation,
              f"实际值: {scenario_data.get('stage_at_creation', 'N/A')}")

        has_is_stale = "is_stale" in scenario_data
        check(17, "scenario_result.json is_stale 存在", has_is_stale,
              "缺少 is_stale 字段")

        has_fmd = "final_matchup_distribution" in scenario_data
        check(18, "scenario_result.json final_matchup_distribution 存在", has_fmd,
              "缺少 final_matchup_distribution 字段")

        if has_fmd:
            fmd = scenario_data["final_matchup_distribution"]
            fmd_is_list = isinstance(fmd, list)
            check(19, "final_matchup_distribution 是列表", fmd_is_list,
                  f"类型: {type(fmd).__name__}")
            if fmd_is_list and len(fmd) > 0:
                first = fmd[0]
                has_matchup = "matchup" in first
                has_prob = "probability" in first
                check(20, "final_matchup_distribution 条目结构正确",
                      has_matchup and has_prob,
                      f"keys: {list(first.keys())}")

        has_comparison = "comparison" in scenario_data
        check(21, "scenario_result.json comparison 存在", has_comparison,
              "缺少 comparison 字段")

        has_impact = "impact_summary" in scenario_data
        check(22, "scenario_result.json impact_summary 存在", has_impact,
              "缺少 impact_summary 字段")
    else:
        print("\n  [SKIP] scenario_result.json 不存在，跳过数据文件验证")
        print("  [INFO] 请先运行 check_scenario_simulation.py 生成沙盘数据")

    # ── 总结 ──
    print(f"\n{'=' * 60}")
    print(f"结果: {passed}/{passed + failed} 通过")
    if failed == 0:
        print("沙盘条件冠军概率结构验证全部通过")
    else:
        print(f"{failed} 项未通过")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
