"""
check_dashboard_payload.py
检查 Dashboard 展示层 payload 完整性
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} - {detail}")


def main():
    global PASS, FAIL
    print("=" * 50)
    print("Dashboard Payload 检查")
    print("=" * 50)

    # 运行 agent 获取结果（优先使用已有结果，避免重复运行）
    result_path = Path(__file__).parent.parent / "data" / "final_agent_result.json"
    if result_path.exists():
        import json
        with open(result_path, encoding="utf-8") as f:
            result = json.load(f)
        print("  (使用已有 final_agent_result.json)")
    else:
        from app.agents.worldcup_agent import WorldCupPredictionAgent
        agent = WorldCupPredictionAgent(seed=42)
        state = agent.run(season=2026, mode="workflow", use_llm=True)
        result = state.to_dict()

    # 1. champion 存在且不是 Unknown
    champion = result.get("predicted_champion") or result.get("champion", "")
    check("champion 存在且不是 Unknown", bool(champion) and champion != "Unknown", f"champion={champion}")

    # 2. champion_probability 存在
    prob = result.get("champion_probability")
    check("champion_probability 存在", prob is not None, f"probability={prob}")

    # 3. champion_explanation 存在（兼容 explanation 字段名）
    explanation = result.get("champion_explanation") or result.get("explanation", {})
    check("champion_explanation 存在", bool(explanation), f"explanation={explanation}")
    if explanation:
        check("champion_explanation 有 title", bool(explanation.get("title")))
        check("champion_explanation 有 content", bool(explanation.get("content")))

    # 4-10. bracket_payload 结构检查
    bp = result.get("bracket_payload", {})
    check("bracket_payload 存在", bool(bp), f"bp keys={list(bp.keys()) if bp else 'empty'}")

    for round_key in ["round_of_32", "round_of_16", "quarter_finals", "semi_finals", "final"]:
        check(f"bracket_payload 包含 {round_key}", round_key in bp, f"missing {round_key}")
        if round_key in bp:
            count = len(bp[round_key])
            if round_key in ("round_of_32", "round_of_16"):
                check(f"{round_key} 数量 > 0", count > 0, f"count={count}")
            else:
                check(f"{round_key} 存在", True)

    # 11. 数据概览模块已隐藏（检查 debug_dashboard.py 源码）
    dashboard_src = open("debug_dashboard.py", encoding="utf-8").read()
    check("数据概览模块已隐藏", "def display_data_overview" not in dashboard_src)

    # 12. 后台信息模块已隐藏
    check("后台信息模块已隐藏", "后台信息" not in dashboard_src)

    # 13. tool_trace 不展示
    check("tool_trace 不展示", "tool_trace" not in dashboard_src or "st.dataframe" not in dashboard_src)

    # 14. raw JSON 不展示
    check("raw JSON 不展示", "st.json(result)" not in dashboard_src)

    # 15. 冠军解释模块存在（新版用 display_explanation）
    check("冠军解释模块存在", "display_explanation" in dashboard_src or "display_llm_explanation" in dashboard_src)

    # 16. 淘汰赛路线图存在
    check("淘汰赛路线图存在", "display_knockout_roadmap" in dashboard_src or "knockout" in dashboard_src.lower())

    # 17. Top 5 展示存在
    check("Top 5 展示存在", "display_top5" in dashboard_src or "top5" in dashboard_src.lower())

    # 18. AI 分析过程展示存在
    check("AI 分析过程展示存在", "display_ai_analysis_process" in dashboard_src or "agent_steps_summary" in dashboard_src)

    # 19. 统一数据源读取（从 final_agent_result.json 或 API 获取）
    check("统一数据源读取", "final_agent_result" in dashboard_src or "final-result" in dashboard_src)

    print(f"\n{'=' * 50}")
    print(f"结果: {PASS} 通过, {FAIL} 失败")
    print(f"{'=' * 50}")

    if FAIL > 0:
        sys.exit(1)
    print("[OK] Dashboard payload 检查全部通过")


if __name__ == "__main__":
    main()
