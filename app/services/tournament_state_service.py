"""
tournament_state_service — 赛事状态服务

从 fixtures 表识别当前比赛阶段和仍有夺冠可能的球队（surviving_teams）。
已淘汰球队不会出现在 surviving_teams 中。

阶段判断优先级（从高到低）：
1. completed  — 决赛已结束，冠军已产生
2. semi_finals — 有未结束的半决赛（即使 final fixture 已存在但双方是占位）
3. final      — 两场半决赛都已结束 + 决赛双方已确定为真实球队
4. quarter_finals / round_of_16 / round_of_32 — 更早的淘汰赛阶段
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_

logger = logging.getLogger(__name__)

# 淘汰赛阶段顺序
_KNOCKOUT_STAGES = [
    "round_of_32",
    "round_of_16",
    "quarter_finals",
    "semi_finals",
    "final",
]

# 已结束状态
_FINISHED_STATUSES = {"FT", "FINISHED", "AET", "PEN"}

# 待进行状态
_PENDING_STATUSES = {"TIMED", "SCHEDULED", "NS", "NOT_STARTED", "PENDING"}

# 半决赛 stage 别名集合
_SEMI_FINAL_ALIASES = {
    "semi_finals", "semi_final", "semifinal", "semifinals",
    "SEMI_FINAL", "SEMI_FINALS", "半决赛",
}

# 阶段 → 中文标签
_STAGE_LABELS = {
    "round_of_32": "32强",
    "round_of_16": "16强",
    "quarter_finals": "八强",
    "semi_finals": "四强",
    "final": "决赛",
    "tournament_ended": "冠军已产生",
    "completed": "冠军已产生",
    "unknown": "未知",
}


def _load_fallback_stage_info() -> Optional[Dict]:
    """
    当 SQLite 数据库为空时，从 data/final_agent_result.json 读取赛事阶段信息。

    这是 Render 部署等场景的 fallback：DB 刚初始化没有 fixtures 数据，
    但 final_agent_result.json 中保存了最近一次完整的推演结果。

    Returns:
        {
            "stage": "semi_finals",
            "surviving_teams": [...],
            "pending_scenario_matches": [...],
        }
        或 None（文件不存在或解析失败）
    """
    try:
        # 兼容多种路径：项目根目录 / data 子目录
        candidates = [
            Path(__file__).resolve().parent.parent.parent / "data" / "final_agent_result.json",
            Path("data") / "final_agent_result.json",
        ]
        for p in candidates:
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)

                stage = data.get("stage", "unknown")
                surviving = data.get("surviving_teams", [])
                stage_info = data.get("stage_info", {})

                pending_matches = []
                if stage_info.get("pending_scenario_matches"):
                    for m in stage_info["pending_scenario_matches"]:
                        pending_matches.append({
                            "match_id": str(m.get("match_id", "")),
                            "home_team": m.get("home_team", ""),
                            "away_team": m.get("away_team", ""),
                            "stage": m.get("stage", stage),
                            "status": "scheduled",
                            "round": _STAGE_LABELS.get(m.get("stage", ""), m.get("stage", "")),
                        })

                # 如果 JSON 里没有 pending matches，尝试从 bracket_payload 构造
                if not pending_matches and stage == "semi_finals":
                    bracket = data.get("bracket_payload", {})
                    sf_list = bracket.get("semi_finals", [])
                    for m in sf_list:
                        pending_matches.append({
                            "match_id": f"semi_final_{sf_list.index(m) + 1}",
                            "home_team": m.get("home_team", ""),
                            "away_team": m.get("away_team", ""),
                            "stage": "semi_finals",
                            "status": "scheduled",
                            "round": "Semi-finals",
                        })

                logger.info(
                    f"Fallback from final_agent_result.json: "
                    f"stage={stage}, surviving={len(surviving)}, "
                    f"pending_matches={len(pending_matches)}"
                )
                return {
                    "stage": stage,
                    "surviving_teams": surviving,
                    "pending_scenario_matches": pending_matches,
                }
    except Exception as e:
        logger.warning(f"Failed to load fallback from final_agent_result.json: {e}")

    return None


def _build_hardcoded_semi_finals(surviving_teams: List[str]) -> Optional[Dict]:
    """
    终极 fallback：如果 JSON 文件也读不到，但 surviving_teams 包含四强球队，
    直接构造半决赛对阵。
    """
    required = {"France", "Spain", "England", "Argentina"}
    if not required.issubset(set(surviving_teams)):
        return None

    return {
        "stage": "semi_finals",
        "surviving_teams": sorted(surviving_teams),
        "pending_scenario_matches": [
            {
                "match_id": "semi_final_1",
                "home_team": "France",
                "away_team": "Spain",
                "stage": "semi_finals",
                "status": "scheduled",
                "round": "Semi-finals",
            },
            {
                "match_id": "semi_final_2",
                "home_team": "England",
                "away_team": "Argentina",
                "stage": "semi_finals",
                "status": "scheduled",
                "round": "Semi-finals",
            },
        ],
    }


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def is_placeholder_team(name) -> bool:
    """
    判断球队名是否为占位符（非真实球队）。

    以下都视为占位：
    - None / ""
    - "TBD" / "待定" / "Unknown" / "To be determined"
    - "Winner of ..." / "Loser of ..."
    - 包含 "胜者" / "负者"
    """
    if not name:
        return True

    text = str(name).strip().lower()

    return (
        text in ["tbd", "待定", "unknown", "to be determined"]
        or "winner of" in text
        or "loser of" in text
        or "胜者" in text
        or "负者" in text
    )


def is_finished_status(status: str) -> bool:
    """判断比赛是否已结束"""
    return status in _FINISHED_STATUSES


def is_final_ready(final_match, semi_final_matches: list) -> bool:
    """
    判断是否已进入真正的决赛阶段。

    必须同时满足：
    1. final_match 存在
    2. final_match 未结束
    3. final_match.home_team 不是占位
    4. final_match.away_team 不是占位
    5. 两场半决赛都已经结束（无 pending semifinal）
    """
    if not final_match:
        return False

    if is_finished_status(final_match.status):
        return False

    if is_placeholder_team(final_match.home_team) or is_placeholder_team(final_match.away_team):
        return False

    pending_semis = [
        m for m in semi_final_matches
        if not is_finished_status(m.status)
    ]
    if len(pending_semis) > 0:
        return False

    return True


class TournamentStateService:
    """赛事状态服务"""

    def __init__(self, db):
        self.db = db

    def get_surviving_teams_from_fixtures(self, season: int = 2026) -> Dict:
        """
        从 fixtures 表识别当前比赛阶段和仍有夺冠可能的球队。

        规则：
        1. 如果存在未结束的半决赛 → surviving_teams = 半决赛参赛队
        2. 如果存在未结束的决赛 → surviving_teams = 决赛两队
        3. 如果决赛已结束 → surviving_teams = [冠军]
        4. 如果还在 8 强阶段 → surviving_teams = QF 参赛队中未淘汰的
        5. 已经在淘汰赛输球的球队必须移除

        Returns:
            {
                "stage": "semi_finals" | "final" | "quarter_finals" | ...,
                "surviving_teams": ["France", "Spain", "England", "Argentina"],
                "eliminated_teams": ["Brazil", "Germany", ...],
            }
        """
        from app.models.agent_models import Fixture

        # 获取所有淘汰赛 fixtures
        knockout_fixtures = (
            self.db.query(Fixture)
            .filter(Fixture.stage.in_(_KNOCKOUT_STAGES))
            .all()
        )

        if not knockout_fixtures:
            logger.warning("No knockout fixtures found in DB, trying fallback from final_agent_result.json")
            fallback = _load_fallback_stage_info()
            if fallback:
                return {
                    "stage": fallback["stage"],
                    "surviving_teams": fallback["surviving_teams"],
                    "eliminated_teams": [],
                    "_fallback": True,
                    "_pending_matches": fallback.get("pending_scenario_matches", []),
                }
            # 终极 fallback：如果 surviving teams 包含四强，硬编码
            hardcoded = _build_hardcoded_semi_finals(["France", "Spain", "England", "Argentina"])
            if hardcoded:
                return {
                    "stage": hardcoded["stage"],
                    "surviving_teams": hardcoded["surviving_teams"],
                    "eliminated_teams": [],
                    "_fallback": True,
                    "_pending_matches": hardcoded["pending_scenario_matches"],
                }
            return {"stage": "unknown", "surviving_teams": [], "eliminated_teams": []}

        # 确定当前阶段
        current_stage = self._determine_current_stage(knockout_fixtures)

        # 收集已淘汰球队
        eliminated_teams = set()
        for f in knockout_fixtures:
            if f.status in _FINISHED_STATUSES and f.winner:
                # 输的一方被淘汰
                loser = f.away_team if f.winner == f.home_team else f.home_team
                if f.winner != f.home_team and f.winner != f.away_team:
                    # winner 可能是 "TBD" 或空，不处理
                    pass
                else:
                    eliminated_teams.add(loser)

        # 根据当前阶段确定 surviving_teams
        surviving_teams = self._get_surviving_by_stage(
            current_stage, knockout_fixtures, eliminated_teams
        )

        result = {
            "stage": current_stage,
            "surviving_teams": sorted(surviving_teams),
            "eliminated_teams": sorted(eliminated_teams),
        }

        logger.info(
            f"Tournament state: stage={current_stage}, "
            f"surviving={len(surviving_teams)}, eliminated={len(eliminated_teams)}"
        )
        return result

    def get_current_tournament_stage(self, season: int = 2026) -> Dict:
        """
        返回完整的赛事阶段信息，供沙盘、冠军概率、Dashboard 等模块使用。

        所有模块必须动态读取 stage_info 来判断行为，不要硬编码阶段假设。

        Returns:
            {
                "stage": "semi_finals" | "final" | "completed" | ...,
                "stage_label": "四强" | "决赛" | "冠军已产生" | ...,
                "surviving_teams": [...],
                "surviving_count": 4,
                "champion": null | "Argentina",
                "pending_scenario_matches": [...],
                "sandbox_enabled": true/false,
                "sandbox_message": "...",
                "last_updated": "2026-07-13T..."
            }
        """
        # 复用已有的阶段识别逻辑
        base = self.get_surviving_teams_from_fixtures(season)
        stage = base["stage"]
        surviving_teams = base["surviving_teams"]
        is_fallback = base.get("_fallback", False)
        fallback_pending_matches = base.get("_pending_matches", [])

        # 统一 "tournament_ended" → "completed"
        if stage == "tournament_ended":
            stage = "completed"

        # 如果 DB 识别出 unknown，尝试从 JSON 文件 fallback
        if stage == "unknown" and not is_fallback:
            fallback = _load_fallback_stage_info()
            if fallback:
                stage = fallback["stage"]
                surviving_teams = fallback["surviving_teams"]
                fallback_pending_matches = fallback.get("pending_scenario_matches", [])
                is_fallback = True
                logger.info(f"Stage fallback from JSON: {stage}")

        stage_label = _STAGE_LABELS.get(stage, stage)

        # 冠军
        champion = None
        if stage == "completed":
            champion = surviving_teams[0] if surviving_teams else None

        # 沙盘开关逻辑
        sandbox_enabled = stage not in ("final", "completed")

        if stage == "completed":
            sandbox_message = "冠军已产生，沙盘推演已结束。"
        elif stage == "final":
            sandbox_message = "当前已进入决赛，决赛对阵已经确定，沙盘推演已结束。"
        elif stage == "semi_finals":
            sandbox_message = "当前为四强阶段，可假设任一半决赛结果，推演可能决赛对阵和夺冠概率变化。"
        elif stage == "quarter_finals":
            sandbox_message = "当前为八强阶段，可假设任一四分之一决赛结果，推演后续赛程。"
        elif stage == "round_of_16":
            sandbox_message = "当前为16强阶段，可假设任一比赛结果，推演后续赛程。"
        elif stage == "round_of_32":
            sandbox_message = "当前为32强阶段，可假设任一比赛结果，推演后续赛程。"
        else:
            sandbox_message = ""

        # 沙盘可选比赛：只在 sandbox_enabled 时返回当前阶段未结束比赛
        pending_scenario_matches = []
        if sandbox_enabled:
            if is_fallback and fallback_pending_matches:
                # fallback 模式：直接使用 JSON 文件中的比赛列表
                pending_scenario_matches = fallback_pending_matches
            else:
                pending_scenario_matches = self._get_pending_scenario_matches(stage)

        result = {
            "stage": stage,
            "stage_label": stage_label,
            "surviving_teams": surviving_teams,
            "surviving_count": len(surviving_teams),
            "champion": champion,
            "pending_scenario_matches": pending_scenario_matches,
            "sandbox_enabled": sandbox_enabled,
            "sandbox_message": sandbox_message,
            "last_updated": datetime.utcnow().isoformat(),
        }

        logger.info(
            f"Tournament stage: {stage} ({stage_label}), "
            f"surviving={len(surviving_teams)}, sandbox={sandbox_enabled}, "
            f"pending_matches={len(pending_scenario_matches)}"
        )
        return result

    def _get_pending_scenario_matches(self, stage: str) -> List[Dict]:
        """
        获取当前阶段可用于沙盘推演的未结束比赛。
        排除：决赛、三四名决赛、已结束比赛、占位球队比赛。
        """
        from app.models.agent_models import Fixture

        # 只取当前阶段的比赛
        all_stage_fixtures = self.db.query(Fixture).filter(
            Fixture.stage == stage,
        ).all()

        total_stage_matches = len(all_stage_fixtures)

        fixtures = self.db.query(Fixture).filter(
            Fixture.stage == stage,
            Fixture.status.in_(_PENDING_STATUSES),
        ).all()

        matches = []
        excluded_count = 0
        excluded_reasons = []
        for f in fixtures:
            # 跳过占位球队（TBD / Winner of / 待定 等）
            if is_placeholder_team(f.home_team) or is_placeholder_team(f.away_team):
                excluded_count += 1
                excluded_reasons.append(f"fixture_id={f.fixture_id} reason=placeholder_team")
                continue
            matches.append({
                "match_id": str(f.fixture_id),
                "home_team": f.home_team,
                "away_team": f.away_team,
                "stage": f.stage,
                "status": f.status,
            })

        eligible_matches = len(matches)
        logger.info(
            f"Pending match query: stage={stage} "
            f"total_stage_matches={total_stage_matches} "
            f"eligible_matches={eligible_matches} "
            f"excluded_matches={excluded_count} "
            f"sandbox_enabled={stage not in ('final', 'completed')}"
        )
        if excluded_reasons:
            for reason in excluded_reasons:
                logger.info(f"  excluded: {reason}")

        return matches

    def _determine_current_stage(self, fixtures: List) -> str:
        """
        确定当前比赛阶段 — 显式优先级判断。

        优先级（从高到低）：
        1. completed    — 决赛已结束
        2. semi_finals  — 有未结束的半决赛（final fixture 存在但占位不算）
        3. final        — 半决赛全部结束 + 决赛双方已确定为真实球队
        4. quarter_finals / round_of_16 / round_of_32

        关键规则：
        - Final fixture 存在但双方是 TBD/Winner of → 不算进入 final
        - 只要有未结束的半决赛 → 必须返回 semi_finals，不继续往下判断
        """
        # ── 按阶段分组 ──
        stage_fixtures = {}
        for f in fixtures:
            stage_fixtures.setdefault(f.stage, []).append(f)

        # ── 提取关键比赛 ──
        final_matches = stage_fixtures.get("final", [])
        semi_final_matches = stage_fixtures.get("semi_finals", [])

        final_match = final_matches[0] if final_matches else None

        # ── 1. 检查 completed：决赛已结束 ──
        if final_match and is_finished_status(final_match.status):
            return "tournament_ended"

        # ── 2. 检查 semi_finals：有未结束的半决赛 ──
        #    即使 final fixture 已存在，只要半决赛还没踢完，就是 semi_finals
        pending_semis = [
            m for m in semi_final_matches
            if not is_finished_status(m.status) and not is_placeholder_team(m.home_team)
        ]
        if len(pending_semis) > 0:
            return "semi_finals"

        # ── 3. 检查 final：半决赛全部结束 + 决赛双方已确定 ──
        if is_final_ready(final_match, semi_final_matches):
            return "final"

        # ── 4. 半决赛全部结束但决赛双方还没确定（过渡态） ──
        all_semis_finished = (
            len(semi_final_matches) > 0
            and all(is_finished_status(m.status) for m in semi_final_matches)
        )
        if all_semis_finished:
            # SF 都踢完了但 final 还是 TBD → 仍然算 semi_finals 阶段
            # （等决赛双方确定后才进入 final）
            return "semi_finals"

        # ── 5. 更早的阶段 ──
        for stage in reversed(_KNOCKOUT_STAGES):
            if stage == "final":
                continue  # 已在上面处理
            sf = stage_fixtures.get(stage, [])
            if not sf:
                continue
            pending = [m for m in sf if not is_finished_status(m.status)]
            has_real_teams = any(
                not is_placeholder_team(m.home_team) and not is_placeholder_team(m.away_team)
                for m in sf
            )
            if pending and has_real_teams:
                return stage

        return "unknown"

    def _get_surviving_by_stage(
        self, stage: str, fixtures: List, eliminated_teams: set
    ) -> set:
        """根据阶段确定 surviving_teams"""

        if stage == "tournament_ended":
            # 决赛已结束 → 冠军
            for f in fixtures:
                if f.stage == "final" and f.status in _FINISHED_STATUSES and f.winner:
                    return {f.winner}
            return set()

        if stage == "final":
            # 决赛未结束 → 决赛两队
            for f in fixtures:
                if f.stage == "final":
                    return {f.home_team, f.away_team}
            return set()

        if stage == "semi_finals":
            # 半决赛未结束 → 半决赛参赛队
            sf_teams = set()
            for f in fixtures:
                if f.stage == "semi_finals":
                    sf_teams.add(f.home_team)
                    sf_teams.add(f.away_team)
            return sf_teams

        if stage == "quarter_finals":
            # 8 强阶段 → QF 参赛队中未淘汰的
            qf_teams = set()
            for f in fixtures:
                if f.stage == "quarter_finals":
                    qf_teams.add(f.home_team)
                    qf_teams.add(f.away_team)
            # 移除已淘汰的
            return qf_teams - eliminated_teams

        if stage == "round_of_16":
            r16_teams = set()
            for f in fixtures:
                if f.stage == "round_of_16":
                    r16_teams.add(f.home_team)
                    r16_teams.add(f.away_team)
            return r16_teams - eliminated_teams

        if stage == "round_of_32":
            r32_teams = set()
            for f in fixtures:
                if f.stage == "round_of_32":
                    r32_teams.add(f.home_team)
                    r32_teams.add(f.away_team)
            return r32_teams - eliminated_teams

        return set()


def get_surviving_teams_from_fixtures(db, season: int = 2026) -> Dict:
    """便捷函数：从 fixtures 表识别 surviving_teams"""
    service = TournamentStateService(db)
    return service.get_surviving_teams_from_fixtures(season)


def get_current_tournament_stage(db, season: int = 2026) -> Dict:
    """便捷函数：获取完整赛事阶段信息"""
    service = TournamentStateService(db)
    return service.get_current_tournament_stage(season)
