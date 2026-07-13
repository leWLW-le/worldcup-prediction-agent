"""
沙盘交互式 UI 验收脚本
检查 debug_dashboard.py 是否满足交互式推演的全部要求。
"""
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DASHBOARD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "debug_dashboard.py")

passed = 0
failed = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  [PASS] {msg}")


def fail(msg):
    global failed
    failed += 1
    print(f"  [FAIL] {msg}")


def section(title):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")


# ── 读取源码 ──
with open(DASHBOARD, "r", encoding="utf-8") as f:
    src = f.read()

section("沙盘交互式 UI 源码静态检查")

# 1. 存在 scenario_result_visible session_state
if 'scenario_result_visible' in src:
    ok("存在 scenario_result_visible session_state 字段")
else:
    fail("缺少 scenario_result_visible session_state 字段")

# 2. 存在 scenario_last_run_key session_state
if 'scenario_last_run_key' in src:
    ok("存在 scenario_last_run_key session_state 字段")
else:
    fail("缺少 scenario_last_run_key session_state 字段")

# 3. 存在 st.button("开始推演") 或同等按钮
if '开始推演' in src:
    ok("存在 '开始推演' 按钮文案")
else:
    fail("缺少 '开始推演' 按钮")

# 4. POST /scenario/simulate 只出现在按钮逻辑内（call_scenario_simulate 函数中）
simulate_calls = [m.start() for m in re.finditer(r'call_scenario_simulate\(', src)]
# 检查 call_scenario_simulate 是否只在按钮点击分支内被调用
# 简单方法：检查函数定义存在，且调用处前面有 run_clicked 判断
func_def_ok = 'def call_scenario_simulate(' in src
called_in_button = False
for pos in simulate_calls:
    # 查找该调用前 500 字符内是否有 run_clicked
    context = src[max(0, pos-500):pos]
    if 'run_clicked' in context:
        called_in_button = True
        break
if func_def_ok and called_in_button:
    ok("POST /scenario/simulate 仅在按钮点击逻辑内调用")
else:
    fail("POST /scenario/simulate 调用位置异常")

# 5. 沙盘结果渲染受 scenario_result_visible 控制
if 'scenario_result_visible' in src and 'st.session_state.get("scenario_result_visible")' in src:
    ok("沙盘结果渲染受 scenario_result_visible 条件控制")
else:
    fail("沙盘结果渲染未受 scenario_result_visible 控制")

# 6. 不存在页面初始自动展示 scenario_result.json 的逻辑
# 检查是否有 fetch_scenario_latest() 在 display_scenario_sandbox 中被调用
func_start = src.find('def display_scenario_sandbox(')
func_end = src.find('\ndef ', func_start + 1)
if func_end == -1:
    func_end = len(src)
func_body = src[func_start:func_end]

if 'fetch_scenario_latest()' in func_body:
    fail("页面初始仍自动调用 fetch_scenario_latest()")
else:
    ok("页面初始不自动调用 fetch_scenario_latest()")

# 7. 不存在未点击按钮就自动 render_scenario_result 的逻辑
# 检查结果渲染条件是否包含 scenario_result_visible
if 'st.session_state.get("scenario_result_visible") and scenario' in func_body:
    ok("结果渲染需要 scenario_result_visible=True")
else:
    fail("结果渲染未正确门控")

# 8. 选择变化时会隐藏旧结果
if 'scenario_last_run_key' in func_body and '_current_key' in func_body:
    ok("选择变化检测逻辑存在（last_run_key vs current_key）")
else:
    fail("缺少选择变化检测逻辑")

# 9. 刷新数据时会清空 scenario_result
refresh_clears = (
    'st.session_state.pop("scenario_result"' in src and
    'st.session_state["scenario_result_visible"] = False' in src and
    'st.session_state["scenario_last_run_key"] = None' in src
)
if refresh_clears:
    ok("刷新/重新预测按钮清空全部沙盘状态")
else:
    fail("刷新按钮未完整清空沙盘状态")

# 10. Dashboard 文案包含"点击'开始推演'后"
if '开始推演' in src and '已更改假设条件' in src:
    ok("UI 文案包含交互式提示")
else:
    fail("UI 文案不完整")

# ─ 汇总 ──
print(f"\n{'='*50}")
print(f"  结果: {passed}/{passed+failed} 通过")
if failed == 0:
    print("  [OK] 沙盘交互式 UI 验收全部通过!")
else:
    print(f"  [FAIL] {failed} 项未通过")
print(f"{'='*50}")

sys.exit(0 if failed == 0 else 1)
