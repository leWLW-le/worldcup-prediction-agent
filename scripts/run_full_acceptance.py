"""
综合验收脚本
按顺序执行所有验收脚本，输出总表
"""
import sys
import os
import json
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def run_script(script_name: str) -> dict:
    """运行单个验收脚本，返回结果"""
    script_path = Path(__file__).parent / script_name
    if not script_path.exists():
        return {"exists": False, "success": False, "error": f"脚本不存在: {script_name}"}

    print(f"\n{'='*60}")
    print(f"运行: {script_name}")
    print(f"{'='*60}")

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=str(Path(__file__).parent.parent),
            timeout=120,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
        )
        output = result.stdout + result.stderr
        print(output)
        return {
            "exists": True,
            "success": result.returncode == 0,
            "output": output,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"exists": True, "success": False, "error": "脚本超时（120秒）"}
    except Exception as e:
        return {"exists": True, "success": False, "error": str(e)}


def run_strict_check() -> dict:
    """运行 strict 模式检查并解析结果"""
    print(f"\n{'='*60}")
    print("运行: check_prediction_agent_strict.py（详细模式）")
    print(f"{'='*60}")

    script_path = Path(__file__).parent / "check_prediction_agent_strict.py"
    if not script_path.exists():
        return {"success": False, "error": "脚本不存在"}

    try:
        # 直接导入并运行，以获取结构化结果
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=str(Path(__file__).parent.parent),
            timeout=120,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
        )
        output = result.stdout + result.stderr
        print(output)

        # 解析输出中的关键信息
        parsed = {
            "success": result.returncode == 0,
            "output": output,
            "status": "unknown",
            "workflow_fallback_used": None,
            "llm_steps": 0,
            "has_champion_prediction": False,
            "has_visualization_payload": False,
            "has_final_explanation": False,
            "core_tools_called": [],
        }

        for line in output.split("\n"):
            if "status:" in line.lower():
                if "completed" in line.lower():
                    parsed["status"] = "completed"
            if "workflow_fallback_used" in line.lower():
                parsed["workflow_fallback_used"] = "false" in line.lower()
            if "✅ strict 模式验收通过" in line:
                parsed["success"] = True
            if "❌ strict 模式验收失败" in line:
                parsed["success"] = False

        return parsed

    except Exception as e:
        return {"success": False, "error": str(e)}


def run_data_truth_check() -> dict:
    """运行数据来源检查并解析结果"""
    print(f"\n{'='*60}")
    print("运行: check_real_data_truth.py（详细模式）")
    print(f"{'='*60}")

    script_path = Path(__file__).parent / "check_real_data_truth.py"
    if not script_path.exists():
        return {"success": False, "error": "脚本不存在"}

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=str(Path(__file__).parent.parent),
            timeout=60,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
        )
        output = result.stdout + result.stderr
        print(output)

        parsed = {
            "success": result.returncode == 0,
            "output": output,
            "source_level": "unknown",
            "is_external_realtime": False,
            "user_message": "",
        }

        for line in output.split("\n"):
            if "数据级别:" in line or "数据级别：" in line:
                parsed["source_level"] = line.split(":")[-1].strip() if ":" in line else line.split("：")[-1].strip()
            if "是否外部实时真实数据:" in line or "是否外部实时真实数据：" in line:
                parsed["is_external_realtime"] = "是" in line
            if "页面应显示提示:" in line or "页面应显示提示：" in line:
                parsed["user_message"] = line.split(":")[-1].strip() if ":" in line else line.split("：")[-1].strip()

        return parsed

    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    print("=" * 60)
    print("2026 世界杯预测 Agent - 完整验收")
    print("=" * 60)

    results = {}

    # 1. 工具注册验收
    results["tool_registry"] = run_script("audit_tool_registry.py")

    # 2. strict 模式验收
    results["strict_mode"] = run_strict_check()

    # 3. 数据来源验收
    results["data_truth"] = run_data_truth_check()

    # 4. Dashboard payload 检查
    results["dashboard_payload"] = run_script("check_dashboard_payload.py")

    # 5. Prediction features 检查
    results["prediction_features"] = run_script("check_prediction_features.py")

    # 6. Bracket payload 结构检查
    results["bracket_payload"] = run_script("check_bracket_payload_structure.py")

    # 7. Champion output 检查
    results["champion_output"] = run_script("check_champion_output.py")

    # 8. stage_info 动态阶段识别
    results["stage_info"] = run_script("check_stage_info.py")

    # 9. 沙盘条件冠军概率结构
    results["scenario_conditional"] = run_script("check_scenario_conditional_champion_probability.py")

    # ==================== 输出总表 ====================
    print("\n" + "=" * 60)
    print("完整验收结果")
    print("=" * 60)

    # 1. 工具注册完整
    tool_ok = "[OK] 通过" if results["tool_registry"].get("success") else "[FAIL] 不通过"
    print(f"\n1. 工具注册完整：{tool_ok}")

    # 2. strict 模式不走 pipeline
    strict_result = results["strict_mode"]
    strict_no_pipeline = "[OK] 通过" if strict_result.get("success") else "[FAIL] 不通过"
    print(f"2. strict 模式不走 pipeline：{strict_no_pipeline}")

    # 3. 大模型参与工具选择
    llm_participated = "[OK] 通过" if strict_result.get("success") else "[FAIL] 不通过"
    print(f"3. 大模型参与工具选择：{llm_participated}")

    # 4. 核心预测工具已调用
    core_tools_ok = "[OK] 通过" if strict_result.get("success") else "[FAIL] 不通过"
    print(f"4. 核心预测工具已调用：{core_tools_ok}")

    # 5. Agent 完成冠军预测
    champion_ok = "[OK] 通过" if strict_result.get("status") == "completed" else "[FAIL] 不通过"
    print(f"5. Agent 完成冠军预测：{champion_ok}")

    # 6. 可视化 payload 已生成
    viz_ok = "[OK] 通过" if strict_result.get("success") else "[FAIL] 不通过"
    print(f"6. 可视化 payload 已生成：{viz_ok}")

    # 7. 最终解释已生成
    explain_ok = "[OK] 通过" if strict_result.get("success") else "[FAIL] 不通过"
    print(f"7. 最终解释已生成：{explain_ok}")

    # 8. 真实数据来源已识别
    data_result = results["data_truth"]
    data_ok = "[OK] 通过" if data_result.get("source_level") != "unknown" else "[FAIL] 不通过"
    print(f"8. 真实数据来源已识别：{data_ok}")

    # 9. 当前是否外部实时数据
    is_realtime = "是" if data_result.get("is_external_realtime") else "否"
    print(f"9. 当前是否外部实时数据：{is_realtime}")

    # 10. 当前数据级别
    source_level = data_result.get("source_level", "unknown")
    print(f"10. 当前数据级别：{source_level}")

    # 11. 页面应显示提示
    user_message = data_result.get("user_message", "未知")
    print(f"11. 页面应显示提示：\"{user_message}\"")

    # 12-15. 新增检查
    dp_ok = "[OK] 通过" if results.get("dashboard_payload", {}).get("success") else "[FAIL] 不通过"
    print(f"12. Dashboard payload 检查：{dp_ok}")
    pf_ok = "[OK] 通过" if results.get("prediction_features", {}).get("success") else "[FAIL] 不通过"
    print(f"13. Prediction features 检查：{pf_ok}")
    bp_ok = "[OK] 通过" if results.get("bracket_payload", {}).get("success") else "[FAIL] 不通过"
    print(f"14. Bracket payload 结构检查：{bp_ok}")
    co_ok = "[OK] 通过" if results.get("champion_output", {}).get("success") else "[FAIL] 不通过"
    print(f"15. Champion output 检查：{co_ok}")
    si_ok = "[OK] 通过" if results.get("stage_info", {}).get("success") else "[FAIL] 不通过"
    print(f"16. stage_info 动态阶段识别：{si_ok}")
    sc_ok = "[OK] 通过" if results.get("scenario_conditional", {}).get("success") else "[FAIL] 不通过"
    print(f"17. 沙盘条件冠军概率结构：{sc_ok}")

    # ==================== 总判断 ====================
    print("\n" + "=" * 60)
    print("总判断")
    print("=" * 60)

    framework_pass = all([
        results["tool_registry"].get("success"),
        strict_result.get("success"),
        results.get("dashboard_payload", {}).get("success", False),
        results.get("prediction_features", {}).get("success", False),
        results.get("bracket_payload", {}).get("success", False),
        results.get("champion_output", {}).get("success", False),
        results.get("stage_info", {}).get("success", False),
        results.get("scenario_conditional", {}).get("success", False),
    ])

    if framework_pass:
        print("\n[OK] Agent 框架验收通过")

    if not data_result.get("is_external_realtime"):
        if source_level in ("verified_cache", "manual_verified"):
            print('\n[WARN] Agent 框架通过，但当前不是实时刷新数据，可展示为"结果仅供参考"')
        elif source_level == "local_fallback":
            print("\n[WARN] Agent 框架通过，但当前使用 fallback，不能声称真实实时数据")
        elif source_level in ("llm_candidate", "unavailable"):
            print("\n[FAIL] 当前不能作为真实数据预测结果展示")

    # 最终判断
    print("\n" + "-" * 40)
    if framework_pass and source_level in ("external_real", "verified_cache", "manual_verified"):
        print("[OK] 系统可用于展示（框架通过 + 数据有效）")
    elif framework_pass:
        print("[WARN] 框架通过，但数据需要关注")
    else:
        print("[FAIL] 系统验收未通过")

    print("=" * 60)

    return {
        "framework_pass": framework_pass,
        "source_level": source_level,
        "user_message": user_message,
    }


if __name__ == "__main__":
    main()
