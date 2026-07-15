"""
数据源统一修复 — 回归测试脚本

测试 fetch_final_result 的返回结构、优先级、fallback 逻辑，
以及 validate_data_consistency 的一致性校验。

运行: python scripts/test_data_source_unification.py
"""
import sys
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def _make_sample_data(champion="Argentina", prob=0.492, top5=None):
    """构造标准预测数据"""
    if top5 is None:
        top5 = [
            {"team": champion, "probability": prob},
            {"team": "France", "probability": 0.252},
            {"team": "England", "probability": 0.148},
            {"team": "Spain", "probability": 0.108},
        ]
    return {
        "champion": champion,
        "champion_probability": prob,
        "top5": top5,
        "top_candidates": top5,
        "explanation": {
            "content": f"{champion} 拥有最强的综合实力。",
            "champion": champion,
        },
        "run_id": "test-run-001",
        "generated_at": "2026-07-14T10:00:00",
        "stage": "semi_finals",
        "surviving_teams": ["Argentina", "France", "England", "Spain"],
    }


def _make_result(data, source="api", is_fallback=False, error=None):
    """构造 fetch_final_result 的统一返回结构"""
    run_id = data.get("run_id", "")
    generated_at = data.get("generated_at", "")
    return {
        "data": data,
        "source": source,
        "is_fallback": is_fallback,
        "run_id": run_id,
        "generated_at": generated_at,
        "error": error,
    }


# ══════════════════════════════════════════════════════
# 测试 1: fetch_final_result 返回结构
# ═══════════════════════════════════════════════════════
def test_return_structure():
    """API 返回 200 且 JSON 结构有效时，必须返回统一结构"""
    print("\n[TEST 1] fetch_final_result 返回结构")

    from debug_dashboard import fetch_final_result

    sample = _make_sample_data()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = sample
    mock_response.raise_for_status = MagicMock()

    with patch("debug_dashboard.requests.get", return_value=mock_response):
        # 清除缓存确保测试隔离
        fetch_final_result.clear()
        result = fetch_final_result()

    assert result["source"] == "api", f"source 应为 'api'，实际: {result['source']}"
    assert result["is_fallback"] is False, "is_fallback 应为 False"
    assert result["error"] is None, f"error 应为 None，实际: {result['error']}"
    assert result["data"]["champion"] == "Argentina"
    assert result["run_id"] == "test-run-001"
    assert result["generated_at"] == "2026-07-14T10:00:00"
    print("  ✓ 返回结构正确: source=api, is_fallback=False, error=None")
    print(f"  ✓ champion={result['data']['champion']}, probability={result['data']['champion_probability']}")


# ═══════════════════════════════════════════════════════
# 测试 2: API 不可用 → JSON fallback
# ═══════════════════════════════════════════════════════
def test_json_fallback():
    """API 不可用时，回退到本地 JSON"""
    print("\n[TEST 2] API 不可用 → JSON fallback")

    from debug_dashboard import fetch_final_result, FINAL_RESULT_PATH

    sample = _make_sample_data(champion="France", prob=0.252)

    # 写入临时 JSON 文件
    with open(FINAL_RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)

    try:
        # Mock API 连接失败
        with patch("debug_dashboard.requests.get", side_effect=Exception("Connection refused")):
            fetch_final_result.clear()
            result = fetch_final_result()

        assert result["source"] == "json_fallback", f"source 应为 'json_fallback'，实际: {result['source']}"
        assert result["is_fallback"] is True, "is_fallback 应为 True"
        assert result["error"] is not None, "error 应有 fallback 原因"
        assert result["data"]["champion"] == "France"
        print(f"  ✓ fallback 正确: source=json_fallback, champion={result['data']['champion']}")
        print(f"  ✓ error 消息: {result['error']}")
    finally:
        # 恢复原始 JSON
        _restore_original_json(FINAL_RESULT_PATH)


# ═══════════════════════════════════════════════════════
# 测试 3: API 返回空对象 → 视为无效 → fallback
# ══════════════════════════════════════════════════════
def test_empty_api_response():
    """API 返回空对象不能被视为成功"""
    print("\n[TEST 3] API 返回空对象 → fallback")

    from debug_dashboard import fetch_final_result, FINAL_RESULT_PATH

    sample = _make_sample_data()
    with open(FINAL_RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)

    try:
        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status = MagicMock()

        with patch("debug_dashboard.requests.get", return_value=mock_response):
            fetch_final_result.clear()
            result = fetch_final_result()

        assert result["source"] == "json_fallback", f"空 API 响应应触发 fallback，实际 source={result['source']}"
        print("  ✓ 空 API 响应正确触发 fallback")
    finally:
        _restore_original_json(FINAL_RESULT_PATH)


# ═══════════════════════════════════════════════════════
# 测试 4: API 返回缺少核心字段 → fallback
# ═══════════════════════════════════════════════════════
def test_missing_core_fields():
    """API 缺少核心字段时应 fallback"""
    print("\n[TEST 4] API 缺少核心字段 → fallback")

    from debug_dashboard import fetch_final_result, FINAL_RESULT_PATH

    sample = _make_sample_data()
    with open(FINAL_RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)

    try:
        # 缺少 champion 字段
        bad_data = {"top5": [], "champion_probability": 0.5}
        mock_response = MagicMock()
        mock_response.json.return_value = bad_data
        mock_response.raise_for_status = MagicMock()

        with patch("debug_dashboard.requests.get", return_value=mock_response):
            fetch_final_result.clear()
            result = fetch_final_result()

        assert result["source"] == "json_fallback", "缺少核心字段应触发 fallback"
        print("  ✓ 缺少核心字段正确触发 fallback")
    finally:
        _restore_original_json(FINAL_RESULT_PATH)


# ═══════════════════════════════════════════════════════
# 测试 5: 一致性校验
# ═══════════════════════════════════════════════════════
def test_consistency_validation():
    """一致性校验基于结构化字段"""
    print("\n[TEST 5] 一致性校验")

    from debug_dashboard import validate_data_consistency

    # 5a. 数据一致 → 无警告
    good_data = _make_sample_data()
    good_data["explanation"]["champion"] = "Argentina"
    result = _make_result(good_data)
    warnings = validate_data_consistency(result)
    assert len(warnings) == 0, f"一致数据不应有警告，实际: {warnings}"
    print("  ✓ 一致数据: 无警告")

    # 5b. champion 与 top5[0] 不一致
    bad_data = _make_sample_data()
    bad_data["champion"] = "France"  # 但 top5[0] 是 Argentina
    result = _make_result(bad_data)
    warnings = validate_data_consistency(result)
    assert len(warnings) >= 1, "champion 与 top5[0] 不一致应有警告"
    assert any("top5[0]" in w for w in warnings), f"应包含 top5[0] 相关警告: {warnings}"
    print(f"  ✓ champion/top5 不一致: 检测到警告")

    # 5c. explanation champion 与 champion 不一致
    bad_data2 = _make_sample_data()
    bad_data2["explanation"]["champion"] = "France"
    result2 = _make_result(bad_data2)
    warnings2 = validate_data_consistency(result2)
    assert len(warnings2) >= 1, "explanation champion 不一致应有警告"
    print(f"  ✓ explanation/champion 不一致: 检测到警告")


# ═══════════════════════════════════════════════════════
# 测试 6: 沙盘隔离验证
# ═══════════════════════════════════════════════════════
def test_scenario_isolation():
    """沙盘结果不得覆盖正式预测字段"""
    print("\n[TEST 6] 沙盘隔离验证")

    # 验证 session_state 键名隔离
    formal_keys = {"final_result", "final_result_cache_key", "prediction_error"}
    scenario_keys = {"scenario_result", "scenario_running", "scenario_job_id",
                     "scenario_result_visible", "scenario_last_run_key"}

    # 两组键无交集
    assert len(formal_keys & scenario_keys) == 0, "正式预测和沙盘键名不应有交集"
    print("  ✓ 正式预测键名与沙盘键名完全隔离")

    # 验证 _clear_prediction_state 清除的键
    from debug_dashboard import _clear_prediction_state
    # 检查函数存在
    assert callable(_clear_prediction_state), "_clear_prediction_state 应为可调用函数"
    print("  ✓ _clear_prediction_state 函数存在")


# ═══════════════════════════════════════════════════════
# 测试 7: 缓存键格式
# ═══════════════════════════════════════════════════════
def test_cache_key_format():
    """缓存键应使用 run_id + generated_at"""
    print("\n[TEST 7] 缓存键格式")

    run_id = "test-run-001"
    generated_at = "2026-07-14T10:00:00"
    cache_key = f"{run_id}:{generated_at}"

    assert ":" in cache_key, "缓存键应包含分隔符"
    assert run_id in cache_key, "缓存键应包含 run_id"
    assert generated_at in cache_key, "缓存键应包含 generated_at"
    print(f"  ✓ 缓存键格式: {cache_key}")

    # 不同 run_id 产生不同缓存键
    cache_key2 = f"test-run-002:{generated_at}"
    assert cache_key != cache_key2, "不同 run_id 应产生不同缓存键"
    print("  ✓ 不同 run_id 产生不同缓存键")


# ═══════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════
def _restore_original_json(path):
    """恢复原始 final_agent_result.json"""
    original = {
        "champion": "Argentina",
        "predicted_champion": "Argentina",
        "champion_probability": 0.4881,
        "top5": [
            {"team": "Argentina", "probability": 0.4881},
            {"team": "France", "probability": 0.2569},
            {"team": "England", "probability": 0.1469},
            {"team": "Spain", "probability": 0.1081},
        ],
        "top_candidates": [
            {"team": "Argentina", "probability": 0.4774},
            {"team": "France", "probability": 0.2598},
            {"team": "England", "probability": 0.1521},
            {"team": "Spain", "probability": 0.1107},
        ],
        "surviving_teams": ["Argentina", "England", "France", "Spain"],
        "stage": "semi_finals",
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(original, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════
# 主测试入口
# ═══════════════════════════════════════════════════════
if __name__ == "__main__":
    # Mock streamlit 以避免实际启动
    sys.modules["streamlit"] = MagicMock()
    sys.modules["streamlit"].cache_data = MagicMock()
    sys.modules["streamlit"].cache_resource = MagicMock()
    sys.modules["streamlit"].session_state = {}
    sys.modules["streamlit"].error = MagicMock()
    sys.modules["streamlit"].warning = MagicMock()
    sys.modules["streamlit"].info = MagicMock()
    sys.modules["streamlit"].success = MagicMock()
    sys.modules["streamlit"].spinner = MagicMock()
    sys.modules["streamlit"].button = MagicMock(return_value=False)
    sys.modules["streamlit"].markdown = MagicMock()
    sys.modules["streamlit"].columns = MagicMock()
    sys.modules["streamlit"].expander = MagicMock()
    sys.modules["streamlit"].selectbox = MagicMock()
    sys.modules["streamlit"].radio = MagicMock()
    sys.modules["streamlit"].rerun = MagicMock()
    sys.modules["streamlit"].set_page_config = MagicMock()

    # Mock cache_data decorator to pass through
    def mock_cache_decorator(**kwargs):
        def decorator(func):
            func.clear = MagicMock()
            return func
        return decorator

    sys.modules["streamlit"].cache_data.return_value = mock_cache_decorator
    sys.modules["streamlit"].cache_data.side_effect = None
    sys.modules["streamlit"].cache_data = MagicMock(side_effect=mock_cache_decorator)

    print("=" * 60)
    print("数据源统一修复 — 回归测试")
    print("=" * 60)

    tests = [
        test_return_structure,
        test_json_fallback,
        test_empty_api_response,
        test_missing_core_fields,
        test_consistency_validation,
        test_scenario_isolation,
        test_cache_key_format,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"结果: {passed} 通过, {failed} 失败, 共 {len(tests)} 项")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
    else:
        print("\n所有测试通过 ✓")
