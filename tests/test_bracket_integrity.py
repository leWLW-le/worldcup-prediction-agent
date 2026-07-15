"""
bracket_integrity 测试

覆盖场景：
1. FINISHED 比赛 winner 与比分一致 → 通过
2. FINISHED 比赛 winner 与比分不一致 → 报错
3. FINISHED 比赛无 winner → 报错
4. SCHEDULED 比赛有 winner → 报错
5. SCHEDULED 比赛 winner=None → 通过
6. 晋级链：后续轮次参赛队不在前一轮胜者中 → 报错
7. 决赛胜者 ≠ bracket champion → 报错
8. 缺少轮次 → 报错
"""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.tools.bracket_tool import validate_bracket_integrity, normalize_bracket_payload


# ── 辅助函数 ──

def _make_bracket(
    r32=None, r16=None, qf=None, sf=None, final=None,
    champion_team=None,
):
    """构建一个完整的 bracket_payload（5 轮）"""
    payload = {
        "round_of_32": r32 or [],
        "round_of_16": r16 or [],
        "quarter_finals": qf or [],
        "semi_finals": sf or [],
        "final": final or [],
    }
    if champion_team:
        payload["champion"] = {"team": champion_team, "source": "prediction"}
    return payload


def _finished_match(home, away, home_score, away_score, winner, round_name=""):
    """构建一场已结束的比赛"""
    return {
        "home_team": home,
        "away_team": away,
        "home_score": home_score,
        "away_score": away_score,
        "winner": winner,
        "status": "FINISHED",
        "source": "real_result",
        "round": round_name,
    }


def _scheduled_match(home, away, predicted_winner, winner=None, round_name=""):
    """构建一场预测中的比赛"""
    return {
        "home_team": home,
        "away_team": away,
        "predicted_home_score": 1,
        "predicted_away_score": 0,
        "predicted_winner": predicted_winner,
        "winner": winner,
        "status": "SCHEDULED",
        "source": "agent_prediction",
        "round": round_name,
    }


# ── Test 1: FINISHED 比赛 winner 与比分一致 → 通过 ──

class TestFinishedMatchCorrectWinner:
    """已结束比赛 winner 与比分一致时应通过校验"""

    def test_home_win_correct(self):
        """主队胜（3-1），winner=主队 → 通过"""
        match = _finished_match("Brazil", "Germany", 3, 1, "Brazil")
        bp = _make_bracket(sf=[match])
        errors = validate_bracket_integrity(bp)
        # 不应有 winner 相关错误
        winner_errors = [e for e in errors if "winner" in e.lower() or "WINNER" in e]
        assert len(winner_errors) == 0, f"不应有 winner 错误: {winner_errors}"

    def test_away_win_correct(self):
        """客队胜（1-2），winner=客队 → 通过"""
        match = _finished_match("France", "Argentina", 1, 2, "Argentina")
        bp = _make_bracket(sf=[match])
        errors = validate_bracket_integrity(bp)
        winner_errors = [e for e in errors if "winner" in e.lower() or "WINNER" in e]
        assert len(winner_errors) == 0, f"不应有 winner 错误: {winner_errors}"

    def test_penalty_shootout_correct(self):
        """点球大战（2-2 但 PEN），winner 为任一方 → 通过"""
        match = _finished_match("England", "Argentina", 2, 2, "Argentina")
        match["status"] = "PEN"
        bp = _make_bracket(sf=[match])
        errors = validate_bracket_integrity(bp)
        # 平局时 winner 不检查比分一致性（因为比分相同）
        winner_errors = [e for e in errors if "winner" in e.lower() and "比分" in e]
        assert len(winner_errors) == 0


# ── Test 2: FINISHED 比赛 winner 与比分不一致 → 报错 ──

class TestFinishedMatchWrongWinner:
    """已结束比赛 winner 与比分不一致时应报错"""

    def test_home_win_but_away_as_winner(self):
        """主队 3-1 胜但 winner=客队 → 报错"""
        match = _finished_match("Brazil", "Germany", 3, 1, "Germany")
        bp = _make_bracket(sf=[match])
        errors = validate_bracket_integrity(bp)
        assert any("winner" in e.lower() and "Brazil" in e for e in errors), \
            f"应检测到 winner 错误: {errors}"

    def test_away_win_but_home_as_winner(self):
        """客队 1-3 胜但 winner=主队 → 报错（原始 bug 场景）"""
        match = _finished_match("England", "Argentina", 2, 3, "England")
        bp = _make_bracket(sf=[match])
        errors = validate_bracket_integrity(bp)
        assert any("winner" in e.lower() and "Argentina" in e for e in errors), \
            f"应检测到 winner 错误: {errors}"

    def test_winner_not_participant(self):
        """winner 不是参赛队之一 → 报错"""
        match = _finished_match("Brazil", "Germany", 3, 1, "France")
        bp = _make_bracket(sf=[match])
        errors = validate_bracket_integrity(bp)
        assert any("不是参赛队" in e for e in errors), \
            f"应检测到 winner 非参赛队: {errors}"


# ── Test 3: FINISHED 比赛无 winner → 报错 ──

class TestFinishedMatchNoWinner:
    """已结束比赛无 winner 时应报错"""

    def test_finished_no_winner(self):
        """已结束但 winner 为空 → 报错"""
        match = _finished_match("Brazil", "Germany", 3, 1, "")
        bp = _make_bracket(sf=[match])
        errors = validate_bracket_integrity(bp)
        assert any("已结束但无 winner" in e for e in errors), \
            f"应检测到缺少 winner: {errors}"

    def test_finished_none_winner(self):
        """已结束但 winner 为 None → 报错"""
        match = _finished_match("Brazil", "Germany", 3, 1, None)
        bp = _make_bracket(sf=[match])
        errors = validate_bracket_integrity(bp)
        assert any("已结束但无 winner" in e for e in errors), \
            f"应检测到缺少 winner: {errors}"


# ── Test 4: SCHEDULED 比赛有 winner → 报错 ──

class TestScheduledMatchWithWinner:
    """SCHEDULED 比赛有 winner 时应报错"""

    def test_scheduled_with_real_winner(self):
        """SCHEDULED 比赛 winner='Brazil' → 报错"""
        match = _scheduled_match("Brazil", "Germany", "Brazil", winner="Brazil")
        bp = _make_bracket(sf=[match])
        errors = validate_bracket_integrity(bp)
        assert any("SCHEDULED" in e and "winner" in e.lower() for e in errors), \
            f"应检测到 SCHEDULED 有 winner: {errors}"

    def test_scheduled_with_empty_winner_ok(self):
        """SCHEDULED 比赛 winner='' → 不报错"""
        match = _scheduled_match("Brazil", "Germany", "Brazil", winner="")
        bp = _make_bracket(sf=[match])
        errors = validate_bracket_integrity(bp)
        scheduled_errors = [e for e in errors if "SCHEDULED" in e and "winner" in e.lower()]
        assert len(scheduled_errors) == 0, \
            f"空 winner 不应报错: {scheduled_errors}"


# ── Test 5: SCHEDULED 比赛 winner=None → 通过 ──

class TestScheduledMatchNoWinner:
    """SCHEDULED 比赛 winner=None 时应通过校验"""

    def test_scheduled_none_winner(self):
        """SCHEDULED 比赛 winner=None → 不报错"""
        match = _scheduled_match("Brazil", "Germany", "Brazil", winner=None)
        bp = _make_bracket(sf=[match])
        errors = validate_bracket_integrity(bp)
        scheduled_errors = [e for e in errors if "SCHEDULED" in e and "winner" in e.lower()]
        assert len(scheduled_errors) == 0, \
            f"winner=None 不应报错: {scheduled_errors}"

    def test_scheduled_only_predicted_winner(self):
        """只有 predicted_winner，winner=None → 正常"""
        match = {
            "home_team": "Spain",
            "away_team": "France",
            "predicted_home_score": 2,
            "predicted_away_score": 1,
            "predicted_winner": "Spain",
            "winner": None,
            "status": "SCHEDULED",
            "source": "agent_prediction",
        }
        bp = _make_bracket(sf=[match])
        errors = validate_bracket_integrity(bp)
        scheduled_errors = [e for e in errors if "SCHEDULED" in e and "winner" in e.lower()]
        assert len(scheduled_errors) == 0


# ── Test 6: 晋级链一致性 ──

class TestProgressionChain:
    """后续轮次参赛队必须来自前一轮胜者"""

    def test_valid_progression(self):
        """SF 胜者出现在 Final 中 → 通过"""
        sf1 = _finished_match("Brazil", "Germany", 2, 1, "Brazil")
        sf2 = _finished_match("Argentina", "France", 3, 2, "Argentina")
        final_match = _finished_match("Brazil", "Argentina", 1, 2, "Argentina")
        bp = _make_bracket(
            sf=[sf1, sf2],
            final=[final_match],
            champion_team="Argentina",
        )
        errors = validate_bracket_integrity(bp)
        progression_errors = [e for e in errors if "未出现在" in e]
        assert len(progression_errors) == 0, \
            f"不应有晋级链错误: {progression_errors}"

    def test_invalid_progression(self):
        """Final 参赛队不在 SF 胜者中 → 报错"""
        sf1 = _finished_match("Brazil", "Germany", 2, 1, "Brazil")
        sf2 = _finished_match("Argentina", "France", 3, 2, "Argentina")
        # England 不在 SF 胜者中（Brazil, Argentina）
        final_match = _finished_match("Brazil", "England", 1, 2, "England")
        bp = _make_bracket(
            sf=[sf1, sf2],
            final=[final_match],
            champion_team="England",
        )
        errors = validate_bracket_integrity(bp)
        progression_errors = [e for e in errors if "未出现在" in e]
        assert len(progression_errors) > 0, \
            f"应检测到晋级链错误: {errors}"


# ── Test 7: 决赛胜者 ≠ bracket champion ──

class TestFinalWinnerVsChampion:
    """决赛胜者必须等于 bracket_payload.champion.team"""

    def test_champion_matches_final_winner(self):
        """决赛胜者=Argentina, champion=Argentina → 通过"""
        final_match = _finished_match("Spain", "Argentina", 1, 2, "Argentina")
        bp = _make_bracket(
            final=[final_match],
            champion_team="Argentina",
        )
        errors = validate_bracket_integrity(bp)
        champion_errors = [e for e in errors if "champion" in e.lower() and "决赛" in e]
        assert len(champion_errors) == 0, \
            f"不应有冠军错误: {champion_errors}"

    def test_champion_mismatches_final_winner(self):
        """决赛胜者=Argentina, champion=Spain → 报错"""
        final_match = _finished_match("Spain", "Argentina", 1, 2, "Argentina")
        bp = _make_bracket(
            final=[final_match],
            champion_team="Spain",  # 错误：决赛胜者是 Argentina
        )
        errors = validate_bracket_integrity(bp)
        champion_errors = [e for e in errors if "champion" in e.lower() and "决赛" in e]
        assert len(champion_errors) > 0, \
            f"应检测到冠军不一致: {errors}"


# ── Test 8: 缺少轮次 ──

class TestMissingRounds:
    """bracket_payload 必须包含所有 5 轮"""

    def test_all_rounds_present(self):
        """5 轮齐全 → 通过"""
        bp = _make_bracket()
        errors = validate_bracket_integrity(bp)
        missing_errors = [e for e in errors if "缺少轮次" in e]
        assert len(missing_errors) == 0, \
            f"不应有缺少轮次错误: {missing_errors}"

    def test_missing_one_round(self):
        """缺少 semi_finals → 报错"""
        bp = _make_bracket()
        del bp["semi_finals"]
        errors = validate_bracket_integrity(bp)
        missing_errors = [e for e in errors if "缺少轮次" in e]
        assert len(missing_errors) > 0, \
            f"应检测到缺少 semi_finals: {errors}"

    def test_missing_multiple_rounds(self):
        """缺少多轮 → 报多个错误"""
        bp = _make_bracket()
        del bp["semi_finals"]
        del bp["final"]
        errors = validate_bracket_integrity(bp)
        missing_errors = [e for e in errors if "缺少轮次" in e]
        assert len(missing_errors) == 2, \
            f"应检测到 2 个缺少轮次错误: {errors}"

    def test_empty_bracket(self):
        """空 bracket_payload → 报错"""
        errors = validate_bracket_integrity({})
        assert len(errors) > 0

    def test_none_bracket(self):
        """None bracket_payload → 报错"""
        errors = validate_bracket_integrity(None)
        assert len(errors) > 0

    def test_non_dict_bracket(self):
        """非 dict bracket_payload → 报错"""
        errors = validate_bracket_integrity("not a dict")
        assert len(errors) > 0


# ── 附加：综合场景 ──

class TestComprehensiveScenarios:
    """综合场景测试"""

    def test_full_valid_bracket_all_finished(self):
        """全部已结束的完整 bracket → 校验通过"""
        # R32: Team0..15 胜
        r32 = [_finished_match(f"Team{i}", f"Team{i+16}", 2, 1, f"Team{i}")
               for i in range(16)]
        # R16: Team0..7 胜（都在 R32 胜者中）
        r16 = [_finished_match(f"Team{i}", f"Team{i+8}", 3, 2, f"Team{i}")
               for i in range(8)]
        # QF: Team0..3 胜（都在 R16 胜者中）
        qf = [_finished_match(f"Team{i}", f"Team{i+4}", 2, 0, f"Team{i}")
              for i in range(4)]
        # SF: Team0, Team2 胜（都在 QF 胜者中）
        sf = [_finished_match("Team0", "Team2", 2, 1, "Team0"),
              _finished_match("Team1", "Team3", 3, 1, "Team1")]
        # Final: Team0 胜（在 SF 胜者中）
        final_match = _finished_match("Team0", "Team1", 2, 1, "Team0")
        bp = _make_bracket(
            r32=r32, r16=r16, qf=qf, sf=sf, final=[final_match],
            champion_team="Team0",
        )
        errors = validate_bracket_integrity(bp)
        assert len(errors) == 0, f"完整合法 bracket 不应有错误: {errors}"

    def test_mixed_finished_and_scheduled(self):
        """混合已结束和预测中的比赛 → 各自按规则校验"""
        sf1 = _finished_match("Brazil", "Germany", 2, 1, "Brazil")
        sf2 = _scheduled_match("Argentina", "France", "Argentina", winner=None)
        # Final 是预测
        final_match = _scheduled_match("Brazil", "Argentina", "Brazil", winner=None)
        bp = _make_bracket(
            sf=[sf1, sf2],
            final=[final_match],
            champion_team="Brazil",
        )
        errors = validate_bracket_integrity(bp)
        # 不应有 winner 相关错误
        winner_errors = [e for e in errors if "winner" in e.lower()
                         and ("已结束但无" in e or "SCHEDULED" in e)]
        assert len(winner_errors) == 0, \
            f"混合状态不应有 winner 错误: {winner_errors}"

    def test_match_count_exceeded(self):
        """某轮比赛数量超过预期 → 报错"""
        # final 应有 1 场，放 2 场
        final_matches = [
            _finished_match("Brazil", "Argentina", 2, 1, "Brazil"),
            _finished_match("Spain", "France", 3, 2, "Spain"),
        ]
        bp = _make_bracket(final=final_matches, champion_team="Brazil")
        errors = validate_bracket_integrity(bp)
        count_errors = [e for e in errors if "超过预期" in e]
        assert len(count_errors) > 0, \
            f"应检测到比赛数量超限: {errors}"


# ══════════════════════════════════════════════════════════════
# normalize_bracket_payload 回归测试
# ══════════════════════════════════════════════════════════════


class TestNormalizeProductionData:
    """回归测试：生产环境 England vs Argentina SCHEDULED + stale winner=England"""

    def test_scheduled_match_stale_winner_cleared(self):
        """SCHEDULED 比赛 winner=England → normalize 后 winner=None, predicted_winner=Argentina"""
        sf1 = _scheduled_match("Spain", "France", "Spain")
        sf2 = {
            "home_team": "England",
            "away_team": "Argentina",
            "predicted_winner": "Argentina",
            "winner": "England",  # STALE — must be cleared
            "status": "SCHEDULED",
            "source": "agent_prediction",
            "predicted_home_score": 2,
            "predicted_away_score": 3,
            "round": "semi_finals",
        }
        final_match = _scheduled_match("Spain", "Argentina", "Spain")
        bracket = _make_bracket(
            sf=[sf1, sf2],
            final=[final_match],
            champion_team="Spain",
        )

        normalized = normalize_bracket_payload(bracket)

        # England vs Argentina: winner=None, predicted_winner=Argentina
        sf_match = normalized["semi_finals"][1]
        assert sf_match["winner"] is None, \
            f"SCHEDULED 比赛 winner 应为 None，实际为 {sf_match['winner']}"
        assert sf_match["predicted_winner"] == "Argentina", \
            f"predicted_winner 应为 Argentina，实际为 {sf_match['predicted_winner']}"

    def test_final_must_be_spain_vs_argentina(self):
        """normalize 后决赛必须为 Spain vs Argentina"""
        sf1 = _scheduled_match("Spain", "France", "Spain")
        sf2 = {
            "home_team": "England",
            "away_team": "Argentina",
            "predicted_winner": "Argentina",
            "winner": "England",  # STALE
            "status": "SCHEDULED",
            "source": "agent_prediction",
            "predicted_home_score": 2,
            "predicted_away_score": 3,
            "round": "semi_finals",
        }
        # 决赛可能有 TBD 或错误的队伍
        final_match = {
            "home_team": "Spain",
            "away_team": "TBD",
            "predicted_winner": "Spain",
            "winner": None,
            "status": "SCHEDULED",
            "source": "agent_prediction",
            "predicted_home_score": 2,
            "predicted_away_score": 1,
            "round": "final",
        }
        bracket = _make_bracket(
            sf=[sf1, sf2],
            final=[final_match],
        )

        normalized = normalize_bracket_payload(bracket)

        # 决赛的 away_team 应为 Argentina（从 SF predicted_winner 晋级）
        fm = normalized["final"][0]
        assert fm["home_team"] == "Spain", f"决赛主队应为 Spain，实际为 {fm['home_team']}"
        assert fm["away_team"] == "Argentina", f"决赛客队应为 Argentina，实际为 {fm['away_team']}"
        assert fm["predicted_winner"] == "Spain", f"决赛 predicted_winner 应为 Spain"

    def test_champion_derived_from_final_predicted_winner(self):
        """champion 应从决赛 predicted_winner 推导"""
        sf1 = _scheduled_match("Spain", "France", "Spain")
        sf2 = {
            "home_team": "England",
            "away_team": "Argentina",
            "predicted_winner": "Argentina",
            "winner": "England",  # STALE
            "status": "SCHEDULED",
            "source": "agent_prediction",
            "predicted_home_score": 2,
            "predicted_away_score": 3,
            "round": "semi_finals",
        }
        final_match = {
            "home_team": "Spain",
            "away_team": "TBD",
            "predicted_winner": "Spain",
            "winner": None,
            "status": "SCHEDULED",
            "source": "agent_prediction",
            "predicted_home_score": 2,
            "predicted_away_score": 1,
            "round": "final",
        }
        bracket = _make_bracket(
            sf=[sf1, sf2],
            final=[final_match],
            champion_team="England",  # 错误的旧 champion
        )

        normalized = normalize_bracket_payload(bracket)

        # champion 应被修正为 Spain（决赛 predicted_winner）
        champion_data = normalized.get("champion", {})
        if isinstance(champion_data, dict):
            assert champion_data.get("team") == "Spain", \
                f"champion 应为 Spain，实际为 {champion_data.get('team')}"

    def test_full_pipeline_normalize_then_validate(self):
        """normalize 后 validate 应通过（无错误）"""
        sf1 = _scheduled_match("Spain", "France", "Spain")
        sf2 = {
            "home_team": "England",
            "away_team": "Argentina",
            "predicted_winner": "Argentina",
            "winner": "England",  # STALE
            "status": "SCHEDULED",
            "source": "agent_prediction",
            "predicted_home_score": 2,
            "predicted_away_score": 3,
            "round": "semi_finals",
        }
        final_match = {
            "home_team": "Spain",
            "away_team": "TBD",
            "predicted_winner": "Spain",
            "winner": None,
            "status": "SCHEDULED",
            "source": "agent_prediction",
            "predicted_home_score": 2,
            "predicted_away_score": 1,
            "round": "final",
        }
        bracket = _make_bracket(
            sf=[sf1, sf2],
            final=[final_match],
        )

        normalized = normalize_bracket_payload(bracket)
        errors = validate_bracket_integrity(normalized)
        assert errors == [], f"normalize 后 validate 应无错误，实际: {errors}"


class TestNormalizeFinishedMatch:
    """normalize 对 FINISHED 比赛的处理"""

    def test_finished_match_winner_from_score(self):
        """FINISHED 比赛无 winner → 从比分生成"""
        match = {
            "home_team": "Brazil",
            "away_team": "Germany",
            "home_score": 3,
            "away_score": 1,
            "winner": None,  # 缺失
            "predicted_winner": "Brazil",
            "status": "FINISHED",
            "source": "real_result",
            "round": "quarter_finals",
        }
        bracket = _make_bracket(qf=[match])
        normalized = normalize_bracket_payload(bracket)

        qf_match = normalized["quarter_finals"][0]
        assert qf_match["winner"] == "Brazil", \
            f"winner 应为 Brazil（比分 3-1），实际为 {qf_match['winner']}"
        assert qf_match["predicted_winner"] is None, \
            f"FINISHED 比赛 predicted_winner 应为 None"

    def test_finished_match_wrong_winner_corrected(self):
        """FINISHED 比赛 winner 与比分不符 → 从比分修正"""
        match = {
            "home_team": "Brazil",
            "away_team": "Germany",
            "home_score": 3,
            "away_score": 1,
            "winner": "Germany",  # 错误
            "status": "FINISHED",
            "source": "real_result",
            "round": "quarter_finals",
        }
        bracket = _make_bracket(qf=[match])
        normalized = normalize_bracket_payload(bracket)

        qf_match = normalized["quarter_finals"][0]
        assert qf_match["winner"] == "Brazil", \
            f"winner 应修正为 Brazil（比分 3-1），实际为 {qf_match['winner']}"


class TestNormalizeScheduledMatch:
    """normalize 对 SCHEDULED 比赛的处理"""

    def test_scheduled_winner_cleared(self):
        """SCHEDULED 比赛有 winner → 清除为 None"""
        match = _scheduled_match("Spain", "France", "Spain", winner="Spain")
        bracket = _make_bracket(sf=[match])
        normalized = normalize_bracket_payload(bracket)

        sf_match = normalized["semi_finals"][0]
        assert sf_match["winner"] is None, \
            f"SCHEDULED 比赛 winner 应为 None，实际为 {sf_match['winner']}"
        assert sf_match["predicted_winner"] == "Spain", \
            f"predicted_winner 应保留为 Spain"

    def test_predicted_winner_from_predicted_score(self):
        """SCHEDULED 比赛无 predicted_winner → 从 predicted_score 生成"""
        match = {
            "home_team": "Brazil",
            "away_team": "Argentina",
            "predicted_home_score": 1,
            "predicted_away_score": 3,
            "predicted_winner": None,  # 缺失
            "winner": None,
            "status": "SCHEDULED",
            "source": "agent_prediction",
            "round": "semi_finals",
        }
        bracket = _make_bracket(sf=[match])
        normalized = normalize_bracket_payload(bracket)

        sf_match = normalized["semi_finals"][0]
        assert sf_match["predicted_winner"] == "Argentina", \
            f"predicted_winner 应从 predicted_score 推导为 Argentina，实际为 {sf_match['predicted_winner']}"

    def test_predicted_winner_from_predicted_score_string(self):
        """SCHEDULED 比赛无 predicted_winner → 从 predicted_score 字符串生成"""
        match = {
            "home_team": "Brazil",
            "away_team": "Argentina",
            "predicted_score": "1-3",
            "predicted_winner": None,
            "winner": None,
            "status": "SCHEDULED",
            "source": "agent_prediction",
            "round": "semi_finals",
        }
        bracket = _make_bracket(sf=[match])
        normalized = normalize_bracket_payload(bracket)

        sf_match = normalized["semi_finals"][0]
        assert sf_match["predicted_winner"] == "Argentina", \
            f"predicted_winner 应从 '1-3' 推导为 Argentina，实际为 {sf_match['predicted_winner']}"


class TestNormalizeAdvancementChain:
    """normalize 修复晋级链"""

    def test_tbd_teams_filled_from_previous_winners(self):
        """后续轮次 TBD 队伍应从前一轮胜者填充"""
        qf1 = _scheduled_match("Spain", "France", "Spain")
        qf2 = _scheduled_match("Brazil", "Germany", "Brazil")
        qf3 = _scheduled_match("Argentina", "Portugal", "Argentina")
        qf4 = _scheduled_match("England", "Netherlands", "England")
        # SF 有 TBD
        sf1 = {
            "home_team": "TBD",
            "away_team": "TBD",
            "predicted_winner": None,
            "winner": None,
            "status": "SCHEDULED",
            "source": "agent_prediction",
            "predicted_home_score": 2,
            "predicted_away_score": 1,
            "round": "semi_finals",
        }
        sf2 = {
            "home_team": "TBD",
            "away_team": "TBD",
            "predicted_winner": None,
            "winner": None,
            "status": "SCHEDULED",
            "source": "agent_prediction",
            "predicted_home_score": 1,
            "predicted_away_score": 2,
            "round": "semi_finals",
        }
        bracket = _make_bracket(
            qf=[qf1, qf2, qf3, qf4],
            sf=[sf1, sf2],
        )

        normalized = normalize_bracket_payload(bracket)

        # SF1: Spain vs Brazil (QF 前两场胜者)
        sf1_norm = normalized["semi_finals"][0]
        assert sf1_norm["home_team"] == "Spain", f"SF1 主队应为 Spain，实际为 {sf1_norm['home_team']}"
        assert sf1_norm["away_team"] == "Brazil", f"SF1 客队应为 Brazil，实际为 {sf1_norm['away_team']}"
        assert sf1_norm["predicted_winner"] == "Spain", f"SF1 predicted_winner 应为 Spain"

        # SF2: Argentina vs England (QF 后两场胜者)
        sf2_norm = normalized["semi_finals"][1]
        assert sf2_norm["home_team"] == "Argentina", f"SF2 主队应为 Argentina，实际为 {sf2_norm['home_team']}"
        assert sf2_norm["away_team"] == "England", f"SF2 客队应为 England，实际为 {sf2_norm['away_team']}"
        assert sf2_norm["predicted_winner"] == "England", f"SF2 predicted_winner 应为 England (1-2)"

    def test_finished_match_teams_not_overwritten(self):
        """已结束的当前轮次比赛不修改参赛队"""
        qf1 = _finished_match("Spain", "France", 2, 1, "Spain")
        qf2 = _finished_match("Brazil", "Germany", 3, 2, "Brazil")
        qf3 = _finished_match("Argentina", "Portugal", 1, 0, "Argentina")
        qf4 = _finished_match("England", "Netherlands", 2, 0, "England")
        # SF1 已结束（真实结果）
        sf1 = _finished_match("Spain", "Brazil", 2, 1, "Spain")
        # SF2 还是 TBD
        sf2 = {
            "home_team": "TBD",
            "away_team": "TBD",
            "predicted_winner": None,
            "winner": None,
            "status": "SCHEDULED",
            "source": "agent_prediction",
            "predicted_home_score": 1,
            "predicted_away_score": 2,
            "round": "semi_finals",
        }
        bracket = _make_bracket(
            qf=[qf1, qf2, qf3, qf4],
            sf=[sf1, sf2],
        )

        normalized = normalize_bracket_payload(bracket)

        # SF1 已结束，参赛队不应被修改
        sf1_norm = normalized["semi_finals"][0]
        assert sf1_norm["home_team"] == "Spain"
        assert sf1_norm["away_team"] == "Brazil"
        assert sf1_norm["winner"] == "Spain"

        # SF2 未结束，TBD 应被填充
        sf2_norm = normalized["semi_finals"][1]
        assert sf2_norm["home_team"] == "Argentina", f"SF2 主队应为 Argentina，实际为 {sf2_norm['home_team']}"
        assert sf2_norm["away_team"] == "England", f"SF2 客队应为 England，实际为 {sf2_norm['away_team']}"
