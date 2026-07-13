"""
Dashboard UI 美化验收脚本
检查 debug_dashboard.py 是否满足 UI 优化要求
"""

import sys
import os
import re
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
dashboard_path = project_root / "debug_dashboard.py"

passed = 0
failed = 0
results = []


def check(num, desc, condition):
    global passed, failed
    if condition:
        passed += 1
        status = "PASS"
    else:
        failed += 1
        status = "FAIL"
    results.append(f"  [{status}] 检查{num}: {desc}")
    print(f"  [{status}] 检查{num}: {desc}")


def main():
    global passed, failed

    print("=" * 60)
    print("Dashboard UI 美化验收检查")
    print("=" * 60)

    if not dashboard_path.exists():
        print(f"  [FAIL] 找不到 {dashboard_path}")
        sys.exit(1)

    with open(dashboard_path, encoding="utf-8") as f:
        content = f.read()

    # 1. 不包含"数据来源调试信息"
    check(1, '不包含"数据来源调试信息"',
          "数据来源调试信息" not in content)

    # 2. 不包含"raw json"（作为显示文本）
    # 检查是否有将 "raw json" 渲染到页面的代码
    has_raw_json_display = bool(re.search(r'st\.markdown.*raw\s+json', content, re.IGNORECASE))
    check(2, '不显示"raw json"',
          not has_raw_json_display)

    # 3. 不包含"backend url"（作为显示文本）
    has_backend_url_display = bool(re.search(r'st\.markdown.*backend\s*url', content, re.IGNORECASE))
    check(3, '不显示"backend url"',
          not has_backend_url_display)

    # 4. 不包含"tool_trace"（作为显示文本）
    has_tool_trace_display = bool(re.search(r'st\.markdown.*tool_trace', content, re.IGNORECASE))
    check(4, '不显示"tool_trace"',
          not has_tool_trace_display)

    # 5. 包含"正式冠军预测"
    check(5, '包含"正式冠军预测"',
          "正式冠军预测" in content)

    # 6. 包含"AI 冠军解读"
    check(6, '包含"AI 冠军解读"',
          "AI 冠军解读" in content)

    # 7. 包含"冠军路径沙盘"
    check(7, '包含"冠军路径沙盘"',
          "冠军路径沙盘" in content)

    # 8. 包含"假设推演"
    check(8, '包含"假设推演"',
          "假设推演" in content)

    # 9. 包含"该模块不会修改真实赛果"
    check(9, '包含"该模块不会修改真实赛果"',
          "该模块不会修改真实赛果" in content)

    # 10. 包含"section-card"
    check(10, '包含"section-card" CSS类',
          "section-card" in content)

    # 11. 包含"ai-card"
    check(11, '包含"ai-card" CSS类',
          "ai-card" in content)

    # 12. 包含"sandbox-card"
    check(12, '包含"sandbox-card" CSS类',
          "sandbox-card" in content)

    # 13. 不重复渲染"为什么预测"
    # 检查 st.markdown 中 "为什么预测" 出现次数（应该只有1次渲染）
    render_matches = re.findall(r'st\.markdown\([^)]*为什么预测', content)
    # clean_explanation_text 中的匹配不算（它们在函数定义中）
    # display_explanation 中只有1次渲染
    explanation_render_count = len(re.findall(
        r'<h3[^>]*>为什么预测', content
    ))
    check(13, '"为什么预测"标题只渲染一次',
          explanation_render_count == 1)

    # 14. AI分析过程默认折叠
    has_expander_collapsed = bool(re.search(
        r'st\.expander\([^)]*AI\s*分析过程[^)]*expanded\s*=\s*False', content
    ))
    check(14, 'AI分析过程默认折叠',
          has_expander_collapsed)

    # 15. 正式预测和沙盘结果分别独立展示
    has_official_card = "official-card" in content
    has_sandbox_visual = "sandbox-card" in content or "sandbox-wrapper" in content
    champion_in_section = bool(re.search(
        r'def display_champion_card.*?section-card', content, re.DOTALL
    ))
    sandbox_in_function = bool(re.search(
        r'def display_scenario_sandbox.*?(sandbox-card|sandbox-wrapper|sandbox-container-marker)', content, re.DOTALL
    ))
    check(15, '正式预测和沙盘结果分别独立展示',
          has_official_card and has_sandbox_visual and champion_in_section and sandbox_in_function)

    # ── 第二轮 UI 优化新增检查 ──

    # 16. 包含 sandbox-wrapper
    check(16, '包含"sandbox-wrapper" CSS类',
          "sandbox-wrapper" in content)

    # 17. 包含 form-panel
    check(17, '包含"form-panel" CSS类',
          "form-panel" in content)

    # 18. 包含 result-panel
    check(18, '包含"result-panel" CSS类',
          "result-panel" in content)

    # 19. 包含 bracket-wrapper
    check(19, '包含"bracket-wrapper" CSS类',
          "bracket-wrapper" in content)

    # 20. 包含 Streamlit 表单 label 颜色覆盖 (stWidgetLabel)
    check(20, '包含 stWidgetLabel 颜色覆盖',
          "stWidgetLabel" in content)

    # 21. 包含 radiogroup 颜色覆盖
    check(21, '包含 radiogroup 颜色覆盖',
          "radiogroup" in content)

    # 22. 包含 data-baseweb="select" 颜色覆盖
    check(22, '包含 select 下拉框颜色覆盖',
          'data-baseweb="select"' in content or "data-baseweb" in content)

    # 23. 包含 section-subtitle
    check(23, '包含"section-subtitle" CSS类',
          "section-subtitle" in content)

    # 24. 包含 compare-table
    check(24, '包含"compare-table" CSS类',
          "compare-table" in content)

    # 25. display_scenario_sandbox 使用 sandbox-wrapper 或 sandbox-container-marker
    sandbox_uses_wrapper = bool(re.search(
        r'def display_scenario_sandbox.*?(sandbox-wrapper|sandbox-container-marker)', content, re.DOTALL
    ))
    check(25, 'display_scenario_sandbox 使用 sandbox-wrapper/marker',
          sandbox_uses_wrapper)

    # 26. display_knockout_roadmap 不使用 bracket-wrapper（第三轮合并为整体模块）
    bracket_no_wrapper = not bool(re.search(
        r'def display_knockout_roadmap.*?bracket-wrapper', content, re.DOTALL
    ))
    check(26, 'display_knockout_roadmap 不使用 bracket-wrapper（已合并为整体）',
          bracket_no_wrapper)

    # 27. display_knockout_roadmap 使用 bracket-section
    bracket_has_section = bool(re.search(
        r'def display_knockout_roadmap.*?bracket-section', content, re.DOTALL
    ))
    check(27, 'display_knockout_roadmap 使用 bracket-section',
          bracket_has_section)

    # 28. 淘汰赛模块包含 section-subtitle 说明文字
    bracket_has_subtitle = bool(re.search(
        r'def display_knockout_roadmap.*?section-subtitle', content, re.DOTALL
    ))
    check(28, '淘汰赛模块包含 section-subtitle',
          bracket_has_subtitle)

    # ── 第三轮 UI 优化新增检查 ──

    # 29. 包含装饰动画 CSS 类
    check(29, '包含 decor-bounce 装饰动画',
          "decor-bounce" in content)
    check(30, '包含 decor-float 装饰动画',
          "decor-float" in content)

    # 31. 包含 AI 解释层次化 CSS 类
    check(31, '包含 expl-section-title 样式',
          "expl-section-title" in content)
    check(32, '包含 expl-list-item 样式',
          "expl-list-item" in content)
    check(33, '包含 expl-highlight 样式',
          "expl-highlight" in content)

    # 34. 包含 render_explanation_html 函数
    check(34, '包含 render_explanation_html 函数',
          "def render_explanation_html" in content)

    # 35. form-panel 设为透明（合并沙盘模块）
    form_panel_transparent = bool(re.search(
        r'\.form-panel\s*\{[^}]*background:\s*transparent', content
    ))
    check(35, 'form-panel 背景透明',
          form_panel_transparent)

    # 36. result-panel 设为透明
    result_panel_transparent = bool(re.search(
        r'\.result-panel\s*\{[^}]*background:\s*transparent', content
    ))
    check(36, 'result-panel 背景透明',
          result_panel_transparent)

    # 汇总
    print()
    print("=" * 60)
    total = passed + failed
    print(f"总计: {total} 项检查, {passed} 通过, {failed} 失败")

    if failed > 0:
        print("\n失败项:")
        for r in results:
            if "FAIL" in r:
                print(r)
        print("=" * 60)
        sys.exit(1)
    else:
        print("[OK] Dashboard UI 美化验收全部通过!")
        print("=" * 60)


if __name__ == "__main__":
    main()
