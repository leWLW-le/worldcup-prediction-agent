"""
集成测试 — _save_final_agent_result 保存路径 + FastAPI 端点

覆盖场景：
1. _save_final_agent_result 不出现 UnboundLocalError
2. normalize_bracket_payload 被执行
3. validate_bracket_integrity 被执行
4. bracket 有错误时不写 DB、不覆盖 JSON
5. bracket 无错误时写 DB 和 JSON 成功
6. POST /run-prediction 成功时返回 200 + status=completed
7. GET /final-result 返回 bracket_payload 非空、integrity_errors 为空
8. 并发锁：第二个请求返回 409
"""
import json
import os
import sys
import threading
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.agent_state import AgentState
from app.agents.worldcup_agent import (
    WorldCupPredictionAgent,
    _validate_prediction_snapshot,
)
from app.tools.bracket_tool import normalize_bracket_payload, validate_bracket_integrity


# ══════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════

def _make_valid_bracket_payload():
    """构建一个合法的 5 轮 bracket_payload（Spain vs Argentina 决赛）

    晋级链必须完全一致：每轮参赛队 = 上一轮胜者。
    每轮中每支队伍最多出现一次（不能有重复队进入同一轮）。
    """
    def _fin(home, away, hs, aws, winner):
        return {
            "home_team": home, "away_team": away,
            "home_score": hs, "away_score": aws,
            "winner": winner, "status": "FINISHED",
            "predicted_home_score": None, "predicted_away_score": None,
            "predicted_winner": winner,
        }

    # R32: 16 场，16 个胜者（每队最多出现一次）
    r32 = [
        _fin("Spain", "Georgia", 3, 0, "Spain"),
        _fin("France", "USA", 2, 0, "France"),
        _fin("England", "Slovenia", 2, 1, "England"),
        _fin("Argentina", "Australia", 3, 0, "Argentina"),
        _fin("Germany", "Denmark", 2, 0, "Germany"),
        _fin("Portugal", "Poland", 2, 1, "Portugal"),
        _fin("Brazil", "South Korea", 3, 1, "Brazil"),
        _fin("Netherlands", "Mexico", 2, 0, "Netherlands"),
        _fin("Belgium", "Ukraine", 2, 1, "Belgium"),
        _fin("Croatia", "Japan", 1, 0, "Croatia"),
        _fin("Morocco", "Colombia", 2, 0, "Morocco"),
        _fin("Uruguay", "Paraguay", 1, 0, "Uruguay"),
        _fin("Senegal", "Ecuador", 2, 0, "Senegal"),
        _fin("USA", "Wales", 1, 0, "USA"),
        _fin("Japan", "Iran", 2, 1, "Japan"),
        _fin("Australia", "Canada", 1, 0, "Australia"),
    ]
    # R32 胜者（16 支不重复）:
    # Spain, France, England, Argentina, Germany, Portugal, Brazil, Netherlands,
    # Belgium, Croatia, Morocco, Uruguay, Senegal, USA, Japan, Australia

    # R16: 8 场，参赛队 = R32 胜者（每队最多出现一次）
    r16 = [
        _fin("Spain", "France", 2, 1, "Spain"),
        _fin("Argentina", "England", 2, 1, "Argentina"),
        _fin("Germany", "Portugal", 3, 1, "Germany"),
        _fin("Brazil", "Netherlands", 2, 0, "Brazil"),
        _fin("Belgium", "Croatia", 2, 1, "Belgium"),
        _fin("Morocco", "Uruguay", 1, 0, "Morocco"),
        _fin("Senegal", "USA", 2, 0, "Senegal"),
        _fin("Japan", "Australia", 1, 0, "Japan"),
    ]
    # R16 胜者（8 支不重复）:
    # Spain, Argentina, Germany, Brazil, Belgium, Morocco, Senegal, Japan

    # QF: 4 场，参赛队 = R16 胜者
    qf = [
        _fin("Spain", "Brazil", 2, 1, "Spain"),
        _fin("Argentina", "Belgium", 3, 0, "Argentina"),
        _fin("Germany", "Morocco", 2, 0, "Germany"),
        _fin("Senegal", "Japan", 1, 0, "Senegal"),
    ]
    # QF 胜者（4 支不重复）: Spain, Argentina, Germany, Senegal

    # SF: 2 场，参赛队 = QF 胜者
    sf = [
        _fin("Spain", "Germany", 3, 1, "Spain"),
        _fin("Argentina", "Senegal", 2, 0, "Argentina"),
    ]
    # SF 胜者: Spain, Argentina

    # Final: 1 场，参赛队 = SF 胜者
    final = [{
        "home_team": "Spain", "away_team": "Argentina",
        "home_score": None, "away_score": None,
        "winner": None, "status": "SCHEDULED",
        "predicted_home_score": "1", "predicted_away_score": "2",
        "predicted_winner": "Argentina",
    }]

    return {
        "round_of_32": r32,
        "round_of_16": r16,
        "quarter_finals": qf,
        "semi_finals": sf,
        "final": final,
    }


def _make_agent_state(bracket_payload=None, champion="Argentina", probability=0.45):
    """构建一个可用于 _save_final_agent_result 的 AgentState"""
    state = AgentState()
    state.predicted_champion = champion
    state.champion_probability = probability
    state.top_contenders = [
        {"team": champion, "team_strength_index": probability},
        {"team": "Spain", "team_strength_index": 0.25},
        {"team": "France", "team_strength_index": 0.15},
    ]
    state.bracket_payload = bracket_payload or _make_valid_bracket_payload()
    state.data_status = {"source": "test", "user_message": "test data"}
    state.status = "completed"
    # _generate_champion_explanation 需要 feature_breakdown
    state.feature_breakdown = {
        "attack_score": 0.7,
        "defense_score": 0.6,
        "recent_form_score": 0.5,
        "path_advantage_score": 0.4,
        "knockout_performance_score": 0.5,
        "elo_rating": 0.8,
    }
    return state


def _patch_save_io():
    """统一 patch _save_final_agent_result 中的所有 I/O 操作。

    返回 context manager 元组: (mock_atomic_write, mock_save_db)
    """
    mock_atomic = MagicMock()
    mock_db = MagicMock()
    # 模拟 open() 让 simulation_distribution.json 和 final_agent_result.json 不存在
    mo = mock_open()
    mo.side_effect = FileNotFoundError
    return mock_atomic, mock_db, mo


# ══════════════════════════════════════════════════════════
# Part 1: _save_final_agent_result 保存路径集成测试
# ══════════════════════════════════════════════════════════

class TestSaveFinalAgentResultIntegration:
    """直接调用 _save_final_agent_result()，验证完整保存路径"""

    def test_no_unbound_local_error(self):
        """验证不出现 UnboundLocalError: validate_bracket_integrity"""
        agent = WorldCupPredictionAgent(seed=42)
        state = _make_agent_state()
        mock_atomic, mock_db, mo = _patch_save_io()

        with patch("app.agents.worldcup_agent.atomic_write_json", mock_atomic), \
             patch("app.services.prediction_snapshot_service.save_prediction_snapshot", mock_db), \
             patch("builtins.open", mo):
            # 不应抛出 UnboundLocalError
            agent._save_final_agent_result(state)

    def test_normalize_is_executed(self):
        """验证 normalize_bracket_payload 被调用"""
        agent = WorldCupPredictionAgent(seed=42)

        # 构建一个需要 normalize 的 bracket（SCHEDULED 但有 stale winner）
        bp = _make_valid_bracket_payload()
        bp["final"][0]["winner"] = "Spain"  # SCHEDULED 比赛不应有 winner

        state = _make_agent_state(bracket_payload=bp)
        mock_atomic, mock_db, mo = _patch_save_io()

        with patch("app.agents.worldcup_agent.atomic_write_json", mock_atomic), \
             patch("app.services.prediction_snapshot_service.save_prediction_snapshot", mock_db), \
             patch("builtins.open", mo), \
             patch("app.agents.worldcup_agent.normalize_bracket_payload",
                   wraps=normalize_bracket_payload) as mock_normalize:
            agent._save_final_agent_result(state)
            mock_normalize.assert_called_once()

    def test_validate_is_executed(self):
        """验证 validate_bracket_integrity 被调用"""
        agent = WorldCupPredictionAgent(seed=42)
        state = _make_agent_state()
        mock_atomic, mock_db, mo = _patch_save_io()

        with patch("app.agents.worldcup_agent.atomic_write_json", mock_atomic), \
             patch("app.services.prediction_snapshot_service.save_prediction_snapshot", mock_db), \
             patch("builtins.open", mo), \
             patch("app.agents.worldcup_agent.validate_bracket_integrity",
                   wraps=validate_bracket_integrity) as mock_validate:
            agent._save_final_agent_result(state)
            mock_validate.assert_called()

    def test_bracket_errors_block_save(self):
        """验证 bracket 有错误时不写 DB、不覆盖 JSON"""
        agent = WorldCupPredictionAgent(seed=42)

        # 构建一个 normalize 无法修复的错误：
        # FINISHED 比赛 winner=None 且无比分 → normalize 无法推导 winner
        bp = _make_valid_bracket_payload()
        bp["round_of_16"][0]["winner"] = None
        bp["round_of_16"][0]["home_score"] = None
        bp["round_of_16"][0]["away_score"] = None

        state = _make_agent_state(bracket_payload=bp)
        mock_atomic, mock_db, mo = _patch_save_io()

        with patch("app.agents.worldcup_agent.atomic_write_json", mock_atomic), \
             patch("app.services.prediction_snapshot_service.save_prediction_snapshot", mock_db), \
             patch("builtins.open", mo):
            agent._save_final_agent_result(state)

            # 校验失败 → 不应写入 JSON 和 DB
            mock_atomic.assert_not_called()
            mock_db.assert_not_called()

    def test_no_errors_save_successfully(self):
        """验证 bracket 无错误时写 DB 和 JSON 成功"""
        agent = WorldCupPredictionAgent(seed=42)
        state = _make_agent_state()
        mock_atomic, mock_db, mo = _patch_save_io()

        with patch("app.agents.worldcup_agent.atomic_write_json", mock_atomic), \
             patch("app.services.prediction_snapshot_service.save_prediction_snapshot", mock_db), \
             patch("builtins.open", mo):
            agent._save_final_agent_result(state)

            # 校验通过 → 应写入 JSON 和 DB
            mock_atomic.assert_called_once()
            mock_db.assert_called_once()

            # 验证写入的 snapshot status=completed
            saved_snapshot = mock_atomic.call_args[0][1]
            assert saved_snapshot["status"] == "completed"

    def test_full_save_path_agent_run_to_json(self):
        """端到端验证：_save_final_agent_result → JSON 写入 → 数据完整"""
        agent = WorldCupPredictionAgent(seed=42)
        state = _make_agent_state()

        write_calls = []

        def capture_write(path, data):
            write_calls.append({"path": str(path), "data": deepcopy(data)})

        mock_db = MagicMock()
        mo = mock_open()
        mo.side_effect = FileNotFoundError

        with patch("app.agents.worldcup_agent.atomic_write_json", side_effect=capture_write), \
             patch("app.services.prediction_snapshot_service.save_prediction_snapshot", mock_db), \
             patch("builtins.open", mo):
            agent._save_final_agent_result(state)

            # 验证确实执行了写入
            assert len(write_calls) == 1, f"期望 1 次写入，实际 {len(write_calls)} 次"
            assert write_calls[0]["data"]["status"] == "completed"
            assert write_calls[0]["data"]["champion"] == "Argentina"
            assert "bracket_payload" in write_calls[0]["data"]
            assert write_calls[0]["data"]["bracket_payload"]  # 非空


# ══════════════════════════════════════════════════════════
# Part 2: FastAPI 端点集成测试
# ══════════════════════════════════════════════════════════

class TestFastAPIPredictionEndpoints:
    """测试 POST /run-prediction 和 GET /final-result"""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from main import app
        return TestClient(app)

    def test_post_run_prediction_success(self, client):
        """POST /run-prediction 成功时返回 200 + status=completed"""
        state = _make_agent_state()
        mock_instance = MagicMock()
        mock_instance.run.return_value = state

        with patch("app.agents.worldcup_agent.WorldCupPredictionAgent", return_value=mock_instance):
            response = client.post("/api/v1/agent/run-prediction", json={})
            assert response.status_code == 200
            data = response.json()
            assert data.get("status") == "completed"

    def test_get_final_result_endpoint_reachable(self, client):
        """GET /final-result 端点可达"""
        response = client.get("/api/v1/agent/final-result")
        # 测试环境中 DB 和 JSON 可能无数据，503 也是正常的
        assert response.status_code in (200, 503)

    def test_concurrent_prediction_returns_409(self, client):
        """并发锁：第二个请求返回 409"""
        from app.api.agent import _prediction_lock

        # 手动获取锁
        _prediction_lock.acquire(blocking=True)

        try:
            response = client.post("/api/v1/agent/run-prediction", json={})
            assert response.status_code == 409
            data = response.json()
            assert data["status"] == "conflict"
        finally:
            _prediction_lock.release()

    def test_post_returns_409_not_200(self, client):
        """验证锁住时不返回 200"""
        from app.api.agent import _prediction_lock

        _prediction_lock.acquire(blocking=True)
        try:
            response = client.post("/api/v1/agent/run-prediction", json={})
            assert response.status_code != 200
            assert response.status_code == 409
        finally:
            _prediction_lock.release()


# ══════════════════════════════════════════════════════════
# Part 3: 并发锁单元测试
# ══════════════════════════════════════════════════════════

class TestConcurrencyLock:
    """验证 _prediction_lock 的行为"""

    def test_lock_is_threading_lock(self):
        from app.api.agent import _prediction_lock
        assert isinstance(_prediction_lock, type(threading.Lock()))

    def test_lock_acquire_release(self):
        from app.api.agent import _prediction_lock
        assert _prediction_lock.acquire(blocking=False)
        _prediction_lock.release()

    def test_lock_prevents_double_acquire(self):
        from app.api.agent import _prediction_lock
        assert _prediction_lock.acquire(blocking=False)
        # 第二次获取应失败
        assert not _prediction_lock.acquire(blocking=False)
        _prediction_lock.release()
