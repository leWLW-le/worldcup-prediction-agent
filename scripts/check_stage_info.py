"""
stage_info 动态阶段识别验证脚本

12 项检查：
1. tournament_state_service.py 存在 get_current_tournament_stage 方法
2. get_current_tournament_stage 返回正确的 stage_info 结构
3. stage_info 包含 stage 字段
4. stage_info 包含 stage_label 字段
5. stage_info 包含 surviving_teams 字段
6. stage_info 包含 surviving_count 字段
7. stage_info 包含 sandbox_enabled 字段
8. stage_info 包含 pending_scenario_matches 字段
9. stage_info 包含 sandbox_message 字段
10. worldcup_agent.py 写入 stage_info 到 final_agent_result.json（静态检查）
11. debug_dashboard.py 使用 fetch_stage_info()
12. scenario_simulation_service.py 检查 sandbox_enabled
"""
import sys
import os
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
FINAL_PATH = DATA_DIR / "final_agent_result.json"

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
    print("stage_info 动态阶段识别验证")
    print("=" * 60)

    # ── 1. tournament_state_service.py 存在 get_current_tournament_stage 方法 ──
    print("\n-- 静态检查 --")
    tss_path = PROJECT_ROOT / "app" / "services" / "tournament_state_service.py"
    tss_content = ""
    if tss_path.exists():
        tss_content = tss_path.read_text(encoding="utf-8")

    has_method = "def get_current_tournament_stage" in tss_content
    check(1, "tournament_state_service.py 存在 get_current_tournament_stage", has_method)

    # ── 2-9. 调用 get_current_tournament_stage 检查返回结构 ──
    print("\n-- 动态检查 --")
    stage_info = None
    try:
        from app.db.database import SessionLocal
        from app.services.tournament_state_service import get_current_tournament_stage
        db = SessionLocal()
        try:
            stage_info = get_current_tournament_stage(db)
        finally:
            db.close()
        call_ok = True
    except Exception as e:
        call_ok = False
        print(f"  (调用 get_current_tournament_stage 失败: {e})")

    check(2, "get_current_tournament_stage 可调用", call_ok,
          "" if call_ok else "调用异常")

    required_fields = {
        3: ("stage", "stage"),
        4: ("stage_label", "stage_label"),
        5: ("surviving_teams", "surviving_teams"),
        6: ("surviving_count", "surviving_count"),
        7: ("sandbox_enabled", "sandbox_enabled"),
        8: ("pending_scenario_matches", "pending_scenario_matches"),
        9: ("sandbox_message", "sandbox_message"),
    }

    for num, (field, label) in required_fields.items():
        if stage_info:
            has_field = field in stage_info
            detail = "" if has_field else f"缺少字段 '{field}'"
            check(num, f"stage_info 包含 {label} 字段", has_field, detail)
        else:
            check(num, f"stage_info 包含 {label} 字段", False, "stage_info 为空")

    # ── 10. worldcup_agent.py 写入 stage_info（静态检查）──
    print("\n-- 源码检查 --")
    agent_path = PROJECT_ROOT / "app" / "agents" / "worldcup_agent.py"
    agent_content = ""
    if agent_path.exists():
        agent_content = agent_path.read_text(encoding="utf-8")

    writes_stage_info = '"stage_info"' in agent_content or "'stage_info'" in agent_content
    check(10, "worldcup_agent.py 写入 stage_info 到 result", writes_stage_info,
          "" if writes_stage_info else "未找到 stage_info 写入逻辑")

    # ── 11. debug_dashboard.py 使用 fetch_stage_info() ──
    dashboard_path = PROJECT_ROOT / "debug_dashboard.py"
    dashboard_content = ""
    if dashboard_path.exists():
        dashboard_content = dashboard_path.read_text(encoding="utf-8")

    uses_fetch_stage = "fetch_stage_info" in dashboard_content
    check(11, "debug_dashboard.py 使用 fetch_stage_info()", uses_fetch_stage,
          "" if uses_fetch_stage else "未找到 fetch_stage_info 调用")

    # ── 12. scenario_simulation_service.py 检查 sandbox_enabled ──
    scenario_svc_path = PROJECT_ROOT / "app" / "services" / "scenario_simulation_service.py"
    scenario_svc_content = ""
    if scenario_svc_path.exists():
        scenario_svc_content = scenario_svc_path.read_text(encoding="utf-8")

    checks_sandbox = "sandbox_enabled" in scenario_svc_content
    check(12, "scenario_simulation_service.py 检查 sandbox_enabled", checks_sandbox,
          "" if checks_sandbox else "未找到 sandbox_enabled 检查")

    # ── 补充：stage 值合理性检查 ──
    if stage_info:
        valid_stages = {"round_of_32", "round_of_16", "quarter_finals",
                        "semi_finals", "final", "completed", "tournament_ended", "unknown"}
        stage_val = stage_info.get("stage", "")
        stage_valid = stage_val in valid_stages
        print(f"\n  [INFO] 当前 stage = '{stage_val}' (合法={stage_valid})")
        print(f"  [INFO] stage_label = '{stage_info.get('stage_label', '')}'")
        print(f"  [INFO] surviving_count = {stage_info.get('surviving_count', 0)}")
        print(f"  [INFO] sandbox_enabled = {stage_info.get('sandbox_enabled', '')}")
        print(f"  [INFO] pending_scenario_matches = {len(stage_info.get('pending_scenario_matches', []))} 场")

    # ── 总结 ──
    print(f"\n{'=' * 60}")
    print(f"结果: {passed}/{passed + failed} 通过")
    if failed == 0:
        print("stage_info 动态阶段识别验证全部通过")
    else:
        print(f"{failed} 项未通过")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
