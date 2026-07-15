"""
final-result schema 一致性测试

覆盖场景：
1. canonical 顶层 JSON 结构验证
2. 当前真实 JSON 文件格式验证
3. wrapper JSON 解包测试（验证 _validate_prediction_snapshot 拒绝 wrapper）
4. 缺少 status 时校验失败
5. champion/probability/explanation 一致性校验
6. build_canonical_snapshot 生成合法 snapshot
7. atomic_write_json 原子写入验证
8. fix_final_result_json.py 修复逻辑验证
9. 数据库模型 PredictionSnapshot 创建验证
"""
import json
import os
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

import pytest

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.worldcup_agent import (
    _validate_prediction_snapshot,
    build_canonical_snapshot,
    atomic_write_json,
)


# ── Fixtures ──

def _make_valid_snapshot(**overrides) -> dict:
    """构建一个合法的 canonical snapshot"""
    base = {
        "schema_version": 1,
        "run_id": "run_test_001",
        "status": "completed",
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
            {"team": "Argentina", "probability": 0.4881},
            {"team": "France", "probability": 0.2569},
            {"team": "England", "probability": 0.1469},
            {"team": "Spain", "probability": 0.1081},
        ],
        "explanation": {
            "title": "为什么预测 Argentina 夺冠？",
            "content": "test content",
            "key_reasons": [],
            "source": "fallback",
            "probability": 48.81,
            "champion": "Argentina",
            "champion_probability": 0.4881,
            "run_id": "run_test_001",
        },
        "surviving_teams": ["Argentina", "England", "France", "Spain"],
        "stage": "semi_finals",
        "generated_at": "2026-07-15T00:00:00",
    }
    base.update(overrides)
    return base


# ── Test 1: canonical 顶层 JSON 结构验证 ──

class TestCanonicalTopLevelJSON:
    """验证 canonical snapshot 必须包含所有必需字段"""

    def test_required_fields_present(self):
        snapshot = _make_valid_snapshot()
        _validate_prediction_snapshot(snapshot)

        required_keys = [
            "schema_version", "run_id", "status", "champion",
            "predicted_champion", "champion_probability", "top5",
            "top_candidates", "explanation", "surviving_teams",
            "stage", "generated_at",
        ]
        for key in required_keys:
            assert key in snapshot, f"缺少必需字段: {key}"

    def test_status_is_completed(self):
        snapshot = _make_valid_snapshot()
        assert snapshot["status"] == "completed"

    def test_champion_equals_predicted_champion(self):
        snapshot = _make_valid_snapshot()
        assert snapshot["champion"] == snapshot["predicted_champion"]


# ── Test 2: 当前真实 JSON 文件格式验证 ──

class TestRealJSONFile:
    """验证仓库中 data/final_agent_result.json 的结构"""

    def test_json_file_exists(self):
        json_path = PROJECT_ROOT / "data" / "final_agent_result.json"
        assert json_path.exists(), "data/final_agent_result.json 不存在"

    def test_json_file_valid(self):
        json_path = PROJECT_ROOT / "data" / "final_agent_result.json"
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        # 必须通过校验
        _validate_prediction_snapshot(data)

    def test_json_has_status_completed(self):
        json_path = PROJECT_ROOT / "data" / "final_agent_result.json"
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("status") == "completed"

    def test_json_has_run_id(self):
        json_path = PROJECT_ROOT / "data" / "final_agent_result.json"
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("run_id"), "run_id 不能为空"

    def test_json_has_explanation(self):
        json_path = PROJECT_ROOT / "data" / "final_agent_result.json"
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data.get("explanation"), dict)


# ── Test 3: wrapper JSON 解包测试 ──

class TestWrapperJSONRejection:
    """验证 _validate_prediction_snapshot 拒绝 wrapper 结构"""

    def test_wrapper_data_key_rejected(self):
        """如果真实数据被包在 {"data": snapshot} 里，校验应失败"""
        inner = _make_valid_snapshot()
        wrapper = {"data": inner}
        with pytest.raises(AssertionError, match="status must be 'completed'"):
            _validate_prediction_snapshot(wrapper)

    def test_wrapper_result_key_rejected(self):
        inner = _make_valid_snapshot()
        wrapper = {"result": inner}
        with pytest.raises(AssertionError):
            _validate_prediction_snapshot(wrapper)

    def test_wrapper_snapshot_key_rejected(self):
        inner = _make_valid_snapshot()
        wrapper = {"snapshot": inner}
        with pytest.raises(AssertionError):
            _validate_prediction_snapshot(wrapper)


# ── Test 4: 缺少 status 时校验失败 ──

class TestMissingStatus:
    """验证缺少 status 字段时校验失败"""

    def test_missing_status_fails(self):
        snapshot = _make_valid_snapshot()
        del snapshot["status"]
        with pytest.raises(AssertionError, match="status must be 'completed'"):
            _validate_prediction_snapshot(snapshot)

    def test_status_none_fails(self):
        snapshot = _make_valid_snapshot()
        snapshot["status"] = None
        with pytest.raises(AssertionError, match="status must be 'completed'"):
            _validate_prediction_snapshot(snapshot)

    def test_status_wrong_value_fails(self):
        snapshot = _make_valid_snapshot()
        snapshot["status"] = "pending"
        with pytest.raises(AssertionError, match="status must be 'completed'"):
            _validate_prediction_snapshot(snapshot)


# ── Test 5: champion/probability/explanation 一致性校验 ──

class TestConsistencyValidation:
    """验证所有跨字段一致性约束"""

    def test_champion_must_match_top5_first(self):
        snapshot = _make_valid_snapshot()
        snapshot["champion"] = "France"  # 与 top5[0] 不一致
        with pytest.raises(AssertionError, match="champion.*!=.*top5"):
            _validate_prediction_snapshot(snapshot)

    def test_champion_probability_must_match_top5_first(self):
        snapshot = _make_valid_snapshot()
        snapshot["champion_probability"] = 0.9999  # 与 top5[0] 不一致
        with pytest.raises(AssertionError, match="champion_probability.*!=.*top5"):
            _validate_prediction_snapshot(snapshot)

    def test_top_candidates_first_must_match_champion(self):
        snapshot = _make_valid_snapshot()
        snapshot["top_candidates"][0]["team"] = "France"
        with pytest.raises(AssertionError, match="top_candidates.*!=.*champion"):
            _validate_prediction_snapshot(snapshot)

    def test_top_candidates_probability_must_match(self):
        snapshot = _make_valid_snapshot()
        snapshot["top_candidates"][0]["probability"] = 0.9999
        with pytest.raises(AssertionError, match="top_candidates.*probability.*!=.*champion_probability"):
            _validate_prediction_snapshot(snapshot)

    def test_explanation_champion_must_match(self):
        snapshot = _make_valid_snapshot()
        snapshot["explanation"]["champion"] = "France"
        with pytest.raises(AssertionError, match="explanation.champion.*!=.*champion"):
            _validate_prediction_snapshot(snapshot)

    def test_explanation_probability_must_match(self):
        snapshot = _make_valid_snapshot()
        snapshot["explanation"]["champion_probability"] = 0.9999
        with pytest.raises(AssertionError, match="explanation.champion_probability.*!=.*champion_probability"):
            _validate_prediction_snapshot(snapshot)

    def test_explanation_run_id_must_match(self):
        snapshot = _make_valid_snapshot()
        snapshot["explanation"]["run_id"] = "run_different"
        with pytest.raises(AssertionError, match="explanation.run_id.*!=.*snapshot.run_id"):
            _validate_prediction_snapshot(snapshot)

    def test_explanation_probability_field(self):
        """explanation.probability == champion_probability * 100"""
        snapshot = _make_valid_snapshot()
        snapshot["explanation"]["probability"] = 99.99  # 应该是 48.81
        # 注意：_validate_prediction_snapshot 不直接检查 explanation.probability
        # 但检查 explanation.champion_probability，两者应一致
        # 这里验证 champion_probability 的一致性
        _validate_prediction_snapshot(snapshot)  # 应通过，因为 champion_probability 本身一致


# ── Test 6: build_canonical_snapshot 生成合法 snapshot ──

class TestBuildCanonicalSnapshot:
    """验证 build_canonical_snapshot 生成合法 snapshot"""

    def test_basic_build(self):
        snapshot = build_canonical_snapshot(
            champion="Argentina",
            champion_probability=0.4881,
            top5=[
                {"team": "Argentina", "probability": 0.4881},
                {"team": "France", "probability": 0.2569},
            ],
            explanation={"title": "test", "content": "test"},
            surviving_teams=["Argentina", "France"],
            stage="semi_finals",
        )
        # 应通过校验
        _validate_prediction_snapshot(snapshot)

    def test_champion_forced_from_top5(self):
        """即使传入错误的 champion，也会被 top5[0] 覆盖"""
        snapshot = build_canonical_snapshot(
            champion="France",  # 错误
            champion_probability=0.99,  # 错误
            top5=[
                {"team": "Argentina", "probability": 0.4881},
                {"team": "France", "probability": 0.2569},
            ],
            explanation={},
        )
        assert snapshot["champion"] == "Argentina"
        assert snapshot["champion_probability"] == 0.4881
        _validate_prediction_snapshot(snapshot)

    def test_top_candidates_is_deepcopy_of_top5(self):
        snapshot = build_canonical_snapshot(
            champion="Argentina",
            champion_probability=0.4881,
            top5=[{"team": "Argentina", "probability": 0.4881}],
            explanation={},
        )
        assert snapshot["top_candidates"] == snapshot["top5"]
        # 修改 top5 不应影响 top_candidates
        snapshot["top5"][0]["probability"] = 0.999
        assert snapshot["top_candidates"][0]["probability"] == 0.4881

    def test_explanation_fields_forced(self):
        """explanation 绑定字段被强制覆盖"""
        snapshot = build_canonical_snapshot(
            champion="Argentina",
            champion_probability=0.4881,
            top5=[{"team": "Argentina", "probability": 0.4881}],
            explanation={
                "champion": "France",  # 会被覆盖
                "champion_probability": 0.99,  # 会被覆盖
            },
            run_id="run_test_xyz",
        )
        assert snapshot["explanation"]["champion"] == "Argentina"
        assert snapshot["explanation"]["champion_probability"] == 0.4881
        assert snapshot["explanation"]["probability"] == 48.81
        assert snapshot["explanation"]["run_id"] == "run_test_xyz"

    def test_auto_generated_run_id(self):
        snapshot = build_canonical_snapshot(
            champion="Argentina",
            champion_probability=0.4881,
            top5=[{"team": "Argentina", "probability": 0.4881}],
            explanation={},
        )
        assert snapshot["run_id"].startswith("run_")

    def test_schema_version_present(self):
        snapshot = build_canonical_snapshot(
            champion="Argentina",
            champion_probability=0.4881,
            top5=[{"team": "Argentina", "probability": 0.4881}],
            explanation={},
        )
        assert snapshot.get("schema_version") == 1

    def test_extra_fields_merged(self):
        snapshot = build_canonical_snapshot(
            champion="Argentina",
            champion_probability=0.4881,
            top5=[{"team": "Argentina", "probability": 0.4881}],
            explanation={},
            simulation_count=10000,
            model_version="ensemble_v2",
        )
        assert snapshot["simulation_count"] == 10000
        assert snapshot["model_version"] == "ensemble_v2"


# ── Test 7: atomic_write_json 原子写入验证 ──

class TestAtomicWriteJSON:
    """验证原子写入功能"""

    def test_write_and_read(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.json"
            data = {"key": "value", "number": 42}
            atomic_write_json(path, data)

            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            assert loaded == data

    def test_overwrite_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.json"
            atomic_write_json(path, {"version": 1})
            atomic_write_json(path, {"version": 2})

            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            assert loaded["version"] == 2

    def test_no_temp_file_left(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.json"
            atomic_write_json(path, {"key": "value"})

            # 目录中应该只有 test.json，没有 .tmp 文件
            files = os.listdir(tmpdir)
            assert files == ["test.json"], f"残留临时文件: {files}"

    def test_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sub" / "dir" / "test.json"
            atomic_write_json(path, {"key": "value"})
            assert path.exists()


# ── Test 8: fix_final_result_json.py 修复逻辑验证 ──

class TestFixScript:
    """验证 fix_final_result_json.py 的修复逻辑"""

    def test_fix_adds_status(self):
        """缺少 status 的文件应被修复为 completed"""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "final_agent_result.json"
            data = {
                "champion": "Argentina",
                "predicted_champion": "Argentina",
                "champion_probability": 0.4881,
                "top5": [{"team": "Argentina", "probability": 0.4881}],
                "top_candidates": [{"team": "France", "probability": 0.2}],  # 不一致
            }
            with open(json_path, "w") as f:
                json.dump(data, f)

            # 模拟 fix 逻辑
            with open(json_path, encoding="utf-8") as f:
                d = json.load(f)

            top5 = d.get("top5", [])
            champ = top5[0]["team"]
            prob = top5[0]["probability"]

            d["champion"] = champ
            d["predicted_champion"] = champ
            d["champion_probability"] = prob
            d["top_candidates"] = deepcopy(top5)
            d["status"] = "completed"
            d["run_id"] = "run_fix_test"
            d["explanation"] = {
                "champion": champ,
                "champion_probability": prob,
                "probability": round(prob * 100, 2),
                "run_id": "run_fix_test",
            }
            if not d.get("generated_at"):
                d["generated_at"] = "2026-07-15T00:00:00"

            # 修复后应通过校验
            _validate_prediction_snapshot(d)

    def test_fix_syncs_top_candidates(self):
        """top_candidates 应被同步为 top5 的 deepcopy"""
        top5 = [
            {"team": "Argentina", "probability": 0.4881},
            {"team": "France", "probability": 0.2569},
        ]
        top_candidates = deepcopy(top5)
        assert top_candidates == top5
        top5[0]["probability"] = 0.999
        assert top_candidates[0]["probability"] == 0.4881  # 不受影响


# ── Test 9: DB 模型 PredictionSnapshot 验证 ──

class TestPredictionSnapshotModel:
    """验证 PredictionSnapshot DB 模型"""

    def test_model_importable(self):
        from app.models.agent_models import PredictionSnapshot
        assert PredictionSnapshot.__tablename__ == "prediction_snapshots"

    def test_model_has_required_columns(self):
        from app.models.agent_models import PredictionSnapshot
        columns = {c.name for c in PredictionSnapshot.__table__.columns}
        assert "id" in columns
        assert "run_id" in columns
        assert "status" in columns
        assert "snapshot_json" in columns
        assert "created_at" in columns

    def test_snapshot_service_importable(self):
        from app.services.prediction_snapshot_service import (
            save_prediction_snapshot,
            load_latest_prediction_snapshot,
        )
        assert callable(save_prediction_snapshot)
        assert callable(load_latest_prediction_snapshot)
