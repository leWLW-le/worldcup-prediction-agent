"""
冠军路径沙盘模拟服务（V2 — 动态阶段适配）

用户可假设一场未结束比赛的胜者，系统在假设条件下重新模拟后续世界杯，
输出新的冠军概率、可能决赛对阵、正式 vs 沙盘对比和 AI 解释。
结果保存到 data/scenario_result.json，不影响正式预测（final_agent_result.json）。

核心原则：
- 不修改数据库 fixtures
- 不修改 final_agent_result.json
- 不修改 simulation_distribution.json
- 只写入 data/scenario_result.json
- 动态读取 stage_info，不硬编码阶段假设
"""
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SCENARIO_RESULT_PATH = DATA_DIR / "scenario_result.json"
FINAL_RESULT_PATH = DATA_DIR / "final_agent_result.json"
SIMULATION_DIST_PATH = DATA_DIR / "simulation_distribution.json"


def _infer_stage_from_count(n_teams: int) -> str:
    """根据球队数量推断阶段"""
    if n_teams <= 1:
        return "completed"
    elif n_teams == 2:
        return "final"
    elif n_teams <= 4:
        return "semi_finals"
    elif n_teams <= 8:
        return "quarter_finals"
    elif n_teams <= 16:
        return "round_of_16"
    else:
        return "round_of_32"


# ──────────────────────────────────────────────
# 半决赛结构识别与决赛对阵生成（任务 1-6）
# ──────────────────────────────────────────────

_SEMI_FINAL_STAGE_ALIASES = {
    "semi_finals", "semi_final", "semifinal", "semifinals",
    "SEMI_FINAL", "SEMI_FINALS", "半决赛",
}


def get_semifinal_matches(fixtures: list) -> list:
    """
    从 fixtures 列表中识别两场半决赛（去重后）。

    识别 stage 为 semi_finals / semi_final / semifinal / semifinals / SEMI_FINAL / SEMI_FINALS / 半决赛 的比赛。

    去重逻辑：
    - 按规范化球队配对（canonical_pair）去重
    - 同一逻辑比赛有多条记录时，优先保留：
      1. 有真实外部 API fixture_id（不以 seed_ 开头）
      2. source_level 更高
      3. updated_at 更新

    返回两场半决赛，每场结构：
    {
        "match_id": str,
        "home_team": str,
        "away_team": str,
        "status": str,
        "winner": str | None,
        "_obj": Fixture  # 原始 ORM 对象（内部使用）
    }
    """
    # 收集所有半决赛记录
    semis_raw = []
    for f in fixtures:
        stage_val = getattr(f, 'stage', '') or ''
        if stage_val in _SEMI_FINAL_STAGE_ALIASES:
            semis_raw.append(f)

    # 按 canonical_pair 去重
    source_level_priority = {
        "external_real": 3,
        "verified_cache": 2,
        "manual_verified": 2,
        "unverified_candidate": 1,
        "unavailable": 0,
    }

    def _fixture_rank(f):
        """排名越高越优先保留"""
        fid = str(getattr(f, 'fixture_id', ''))
        has_real_id = not fid.startswith("seed_") if fid else False
        sl = source_level_priority.get(getattr(f, 'source_level', '') or '', 0)
        updated = getattr(f, 'updated_at', None) or getattr(f, 'fetched_at', None)
        return (has_real_id, sl, updated or datetime.min)

    # 尝试使用 canonical_pair 字段去重
    seen_pairs = {}
    for f in semis_raw:
        cp = getattr(f, 'canonical_pair', None)
        if cp:
            if cp not in seen_pairs or _fixture_rank(f) > _fixture_rank(seen_pairs[cp]):
                seen_pairs[cp] = f
    deduped = list(seen_pairs.values())

    # 如果 canonical_pair 不可用（旧数据库），退回到手动计算
    if not seen_pairs and semis_raw:
        manual_pairs = {}
        for f in semis_raw:
            home = (getattr(f, 'home_team', '') or '').strip()
            away = (getattr(f, 'away_team', '') or '').strip()
            if home and away:
                pair = " vs ".join(sorted([home, away]))
                if pair not in manual_pairs or _fixture_rank(f) > _fixture_rank(manual_pairs[pair]):
                    manual_pairs[pair] = f
        deduped = list(manual_pairs.values())

    # 构建返回结构
    semis = []
    for f in deduped:
        semis.append({
            "match_id": str(getattr(f, 'fixture_id', '')),
            "home_team": f.home_team,
            "away_team": f.away_team,
            "status": f.status,
            "winner": getattr(f, 'winner', None),
            "_obj": f,
        })

    # 诊断日志
    fixture_ids = [s["match_id"] for s in semis]
    logical_pairs = [
        " vs ".join(sorted([s["home_team"], s["away_team"]]))
        for s in semis
    ]
    logger.info(
        f"Semi-final fixture validation: expected=2 actual={len(semis)} "
        f"fixture_ids={fixture_ids} logical_pairs={logical_pairs}"
    )

    return semis


def validate_forced_semifinal(forced_fixture, semifinal_matches: list) -> dict:
    """
    校验 forced match 必须是半决赛之一。

    返回:
        {"valid": True} 或 {"valid": False, "message": "..."}
    """
    forced_id = str(getattr(forced_fixture, 'fixture_id', ''))
    for sf in semifinal_matches:
        if sf["match_id"] == forced_id:
            return {"valid": True}
    return {
        "valid": False,
        "message": "沙盘推演只允许选择当前未结束半决赛。"
    }


def get_loser(match, winner: str) -> str:
    """
    返回比赛的败者。

    match 需要有 home_team 和 away_team 属性。
    """
    home = getattr(match, 'home_team', None) or match.get("home_team", "")
    away = getattr(match, 'away_team', None) or match.get("away_team", "")
    if winner == home:
        return away
    if winner == away:
        return home
    raise ValueError(f"假设晋级队 '{winner}' 不是比赛双方之一 ({home} vs {away})")


def resolve_semifinal_winner(semifinal_match: dict, forced_match_id: str,
                             forced_winner: str, simulation_rng=None) -> str:
    """
    解析一场半决赛的胜者。

    1. 如果该场是 forced match → 返回 forced_winner
    2. 如果该场已结束 → 返回实际 winner
    3. 否则 → 用模型模拟胜者
    """
    if semifinal_match["match_id"] == forced_match_id:
        return forced_winner

    if semifinal_match["status"] in ("FT", "FINISHED", "AET", "PEN"):
        return semifinal_match["winner"]

    # 需要模拟 — 使用 ensemble service
    home_name = semifinal_match["home_team"]
    away_name = semifinal_match["away_team"]
    return _simulate_semi_winner(home_name, away_name, simulation_rng)


def _simulate_semi_winner(home_name: str, away_name: str,
                          ensemble_service=None) -> str:
    """模拟单场半决赛，返回胜者队名。"""
    if ensemble_service is None:
        # 无模型可用，按 50/50 随机
        return home_name if np.random.random() < 0.5 else away_name

    try:
        from app.db.database import SessionLocal
        from app.models.schemas import Team
        db = ensemble_service.db
        teams = db.query(Team).all()
        team_by_name = {t.name: t for t in teams}
        home_team = team_by_name.get(home_name)
        away_team = team_by_name.get(away_name)
        if home_team and away_team:
            pred = _simulate_match(ensemble_service, home_team, away_team)
            if pred['home_score'] > pred['away_score']:
                return home_name
            elif pred['away_score'] > pred['home_score']:
                return away_name
            else:
                return home_name if home_team.current_elo >= away_team.current_elo else away_name
    except Exception as e:
        logger.warning(f"Semi simulation failed: {e}")

    return home_name if np.random.random() < 0.5 else away_name


def normalize_final_matchup(final_team_1: str, final_team_2: str) -> str:
    """
    保留半决赛顺序生成决赛对阵字符串。

    semifinal_1 winner vs semifinal_2 winner
    """
    return f"{final_team_1} vs {final_team_2}"


def build_final_matchup_from_semifinal_winners(
    semifinal_matches: list,
    forced_match_id: str,
    forced_winner: str,
    ensemble_service=None,
    simulation_rng=None,
) -> tuple:
    """
    从两场半决赛胜者生成决赛对阵。

    关键要求：
    - 决赛双方必须分别来自两场不同半决赛的胜者
    - 不能从 surviving_teams 任意抽两个队
    - 不能从 final fixture 的 TBD 字段读队伍
    - 不能让半决赛败者进入决赛

    Returns:
        (final_team_1, final_team_2) — 按半决赛顺序
    """
    semifinal_winners = []
    for sf in semifinal_matches:
        winner = resolve_semifinal_winner(
            semifinal_match=sf,
            forced_match_id=forced_match_id,
            forced_winner=forced_winner,
            simulation_rng=simulation_rng,
        )
        semifinal_winners.append(winner)

    if len(semifinal_winners) != 2:
        raise ValueError(f"需要 2 场半决赛，实际 {len(semifinal_winners)} 场")

    return semifinal_winners[0], semifinal_winners[1]


def _simulate_semi_finals_scenario(
    db,
    fixture,
    home_team_name: str,
    away_team_name: str,
    forced_winner: str,
    forced_loser: str,
    match_label: str,
    stage: str,
    simulation_count: int = 3000,
) -> dict:
    """
    半决赛阶段专用沙盘模拟（任务 7-12）。

    流程：
    1. 识别两场半决赛
    2. forced match → 胜者固定
    3. 另一场 → 模型模拟
    4. 两场胜者组成决赛
    5. 模拟决赛胜者
    6. 统计：冠军、决赛晋级、决赛对阵

    输出包含：
    - final_matchup_distribution（可能决赛对阵）
    - finalist_distribution（晋级决赛概率）
    - scenario_prediction（沙盘夺冠概率）
    - comparison（正式 vs 沙盘对比）
    """
    from app.models.agent_models import Fixture
    from app.models.schemas import Team
    from app.services.ensemble_prediction_service import EnsemblePredictionService
    from app.services.tournament_state_service import get_current_tournament_stage

    # ── 1. 识别两场半决赛 ──
    all_fixtures = db.query(Fixture).all()
    semifinal_matches = get_semifinal_matches(all_fixtures)

    # Fallback: DB 为空时，从 stage_info 的 pending_scenario_matches 构造半决赛列表
    if len(semifinal_matches) < 2:
        stage_info_local = get_current_tournament_stage(db)
        pending = stage_info_local.get("pending_scenario_matches", [])
        if len(pending) >= 2:
            semifinal_matches = [
                {
                    "match_id": m.get("match_id", ""),
                    "home_team": m.get("home_team", ""),
                    "away_team": m.get("away_team", ""),
                    "status": m.get("status", "scheduled"),
                    "winner": None,
                    "_obj": None,
                }
                for m in pending
            ]

    if len(semifinal_matches) < 2:
        return {
            "success": False,
            "message": f"未能识别完整半决赛结构（仅找到 {len(semifinal_matches)} 场），无法进行沙盘推演。"
        }

    # ── 2. 校验 forced match 是半决赛之一 ──
    # 兼容 dict（fallback）和 ORM fixture
    if isinstance(fixture, dict):
        forced_fixture_id = fixture.get("match_id", "")
    else:
        forced_fixture_id = str(getattr(fixture, 'fixture_id', ''))

    validation = {"valid": False, "message": ""}
    for sf in semifinal_matches:
        if sf["match_id"] == forced_fixture_id:
            validation = {"valid": True}
            break
    if not validation["valid"]:
        validation["message"] = "沙盘推演只允许选择当前未结束的半决赛之一。"
        return {"success": False, "message": validation["message"]}

    # ── 3. 校验 forced_winner 是比赛双方之一 ──
    if forced_winner not in (home_team_name, away_team_name):
        return {
            "success": False,
            "message": f"假设晋级队必须是所选比赛双方之一。可选: {home_team_name}, {away_team_name}"
        }

    forced_match_id = forced_fixture_id

    # ── 4. 创建 ensemble service + 缓存特征 ──
    ensemble_service = EnsemblePredictionService(db)

    all_sf_teams = set()
    for sf in semifinal_matches:
        all_sf_teams.add(sf["home_team"])
        all_sf_teams.add(sf["away_team"])

    teams = db.query(Team).all()
    team_by_name = {t.name: t for t in teams}

    team_feature_cache = {}
    for name in all_sf_teams:
        if name in team_by_name:
            team = team_by_name[name]
            try:
                feats = ensemble_service._build_team_features_dict(team, is_home=True)
                team_feature_cache[team.id] = feats
            except Exception as e:
                logger.warning(f"Failed to cache features for {name}: {e}")

    original_build_dict = ensemble_service._build_team_features_dict
    def cached_build_dict(team, is_home=True):
        if team.id in team_feature_cache:
            return team_feature_cache[team.id]
        return original_build_dict(team, is_home)
    ensemble_service._build_team_features_dict = cached_build_dict

    # ── 5. Monte Carlo 模拟（任务 7） ──
    champion_counts = defaultdict(int)
    finalist_counts = defaultdict(int)
    final_matchup_counts = defaultdict(int)

    logger.info(f"[Scenario] 开始 {simulation_count} 次半决赛沙盘模拟")
    logger.info(f"[Scenario] 半决赛结构: {[(sf['home_team'] + ' vs ' + sf['away_team']) for sf in semifinal_matches]}")
    logger.info(f"[Scenario] forced_match_id={forced_match_id}, forced_winner={forced_winner}")

    for _ in range(simulation_count):
        # 1. 解析两场半决赛胜者（任务 5）
        final_team_1, final_team_2 = build_final_matchup_from_semifinal_winners(
            semifinal_matches=semifinal_matches,
            forced_match_id=forced_match_id,
            forced_winner=forced_winner,
            ensemble_service=ensemble_service,
        )

        # 2. 统计决赛对阵（任务 6 + 9）
        matchup_key = normalize_final_matchup(final_team_1, final_team_2)
        final_matchup_counts[matchup_key] += 1

        # 3. 统计晋级决赛球队（任务 10）
        finalist_counts[final_team_1] += 1
        finalist_counts[final_team_2] += 1

        # 4. 模拟决赛胜者
        champion = _simulate_semi_winner(final_team_1, final_team_2, ensemble_service)
        champion_counts[champion] += 1

    total = simulation_count

    # ── 6. 计算概率 ──
    champion_probs = {
        team: count / total
        for team, count in sorted(champion_counts.items(), key=lambda x: -x[1])
    }

    # ── 7. final_matchup_distribution（任务 9） ──
    total_matchups = sum(final_matchup_counts.values())
    final_matchup_distribution = []
    for matchup, count in sorted(final_matchup_counts.items(), key=lambda x: -x[1]):
        final_matchup_distribution.append({
            "matchup": matchup,
            "count": count,
            "probability": round(count / total_matchups, 4),
        })

    # ── 8. finalist_distribution（任务 10） ──
    finalist_distribution = []
    for team_name in sorted(all_sf_teams):
        f_count = finalist_counts.get(team_name, 0)
        finalist_distribution.append({
            "name": team_name,
            "finalist_probability": round(f_count / total, 4),
            "count": f_count,
        })
    finalist_distribution.sort(key=lambda x: -x["finalist_probability"])

    # ── 9. 确保 forced_loser 冠军概率为 0（任务 8） ──
    if forced_loser not in champion_counts:
        champion_counts[forced_loser] = 0
        champion_probs[forced_loser] = 0.0

    # ── 10. champion_distribution ──
    champion_distribution = [
        {
            "name": team,
            "count": champion_counts.get(team, 0),
            "probability": round(champion_probs.get(team, 0), 4),
        }
        for team in champion_probs
    ]
    # forced_loser 也要出现（概率为 0）
    if forced_loser not in champion_probs:
        champion_distribution.append({
            "name": forced_loser,
            "count": 0,
            "probability": 0.0,
        })
    champion_distribution.sort(key=lambda x: -x["probability"])

    scenario_champion = champion_distribution[0]["name"] if champion_distribution else "Unknown"
    scenario_champion_prob = champion_distribution[0]["probability"] if champion_distribution else 0

    # ── 11. 加载正式预测用于对比 ──
    official_prediction = _load_official_prediction()

    # ── 12. comparison（任务 12） ──
    comparison = _build_comparison(champion_probs, official_prediction, forced_loser)

    # ── 13. AI 解释 ──
    explanation = _generate_scenario_explanation(
        scenario={
            "match": match_label,
            "stage": stage,
            "forced_winner": forced_winner,
            "forced_loser": forced_loser,
        },
        champion_distribution=champion_distribution,
        official_result=official_prediction,
        final_matchup_distribution=final_matchup_distribution,
    )

    # ── 14. impact_summary ──
    biggest_beneficiary = _find_biggest_beneficiary(comparison, forced_winner)
    impact_summary = {
        "official_champion_before": official_prediction.get("champion", "Unknown"),
        "scenario_champion": scenario_champion,
        "eliminated_team": forced_loser,
        "biggest_beneficiary": biggest_beneficiary,
        "biggest_loser": forced_loser,
    }

    # ── 15. official_prediction 输出 ──
    official_top5 = official_prediction.get("top5", [])
    official_top_candidates = [
        {"name": t.get("team", ""), "probability": t.get("probability", 0)}
        for t in official_top5
    ]

    # ── 16. scenario_prediction（任务 11） ──
    scenario_top_candidates = [
        {"name": cd["name"], "probability": cd["probability"], "count": cd["count"]}
        for cd in champion_distribution
    ]

    # ── 17. 获取 stage_info ──
    stage_info = get_current_tournament_stage(db)
    current_stage = stage_info["stage"]

    # ── 18. 构建结果 ──
    result = {
        "success": True,
        "created_at": datetime.utcnow().isoformat(),
        "scenario_scope": "conditional_champion_probability",
        "stage_at_creation": current_stage,
        "is_stale": False,

        "scenario": {
            "match_id": forced_match_id,
            "match": match_label,
            "stage": stage,
            "forced_winner": forced_winner,
            "forced_loser": forced_loser,
            "note": "假设结果，不影响真实赛果",
        },

        "simulation_count": simulation_count,

        "official_prediction": {
            "champion": official_prediction.get("champion", "Unknown"),
            "probability": official_prediction.get("champion_probability", 0),
            "top_candidates": official_top_candidates,
        },

        "scenario_prediction": {
            "champion": scenario_champion,
            "probability": scenario_champion_prob,
            "top_candidates": scenario_top_candidates,
        },

        "final_matchup_distribution": final_matchup_distribution,
        "finalist_distribution": finalist_distribution,
        "champion_distribution": champion_distribution,
        "comparison": comparison,
        "impact_summary": impact_summary,
        "explanation": explanation,
    }

    # ── 19. 保存 ──
    _save_scenario_result(result)

    logger.info(f"[Scenario] 半决赛沙盘推演完成: {forced_winner} 淘汰 {forced_loser}, "
                 f"新冠军={scenario_champion} ({scenario_champion_prob:.2%})")

    return result


def _simulate_match(ensemble_service, home_team, away_team) -> dict:
    """模拟单场比赛 - 复用 run_champion_simulation.py 的逻辑"""
    try:
        pred = ensemble_service.predict_with_ensemble(home_team, away_team)
        probs = pred.get('probabilities', {})
        home_win_prob = probs.get('home_win', 0.5)
        draw_prob = probs.get('draw', 0.25)
        away_win_prob = probs.get('away_win', 0.25)

        outcome = np.random.random()
        if outcome < home_win_prob:
            home_score = int(round(max(0, 1.5 + (home_team.current_elo - away_team.current_elo) / 400 + 0.5)))
            away_score = int(round(max(0, 1.5 - (home_team.current_elo - away_team.current_elo) / 400 - 0.5)))
            if home_score <= away_score:
                home_score = away_score + 1
        elif outcome < home_win_prob + draw_prob:
            home_score = int(round(max(0, 1.5 + (home_team.current_elo - away_team.current_elo) / 400)))
            away_score = home_score
        else:
            home_score = int(round(max(0, 1.5 + (home_team.current_elo - away_team.current_elo) / 400 - 0.5)))
            away_score = int(round(max(0, 1.5 - (home_team.current_elo - away_team.current_elo) / 400 + 0.5)))
            if away_score <= home_score:
                away_score = home_score + 1

        pred['home_score'] = home_score
        pred['away_score'] = away_score
        return pred
    except Exception as e:
        logger.warning(f"Ensemble failed for {home_team.name} vs {away_team.name}: {e}")
        from app.services.prediction_service import PredictionService
        fallback = PredictionService(ensemble_service.db)
        return fallback._predict_with_elo(home_team, away_team)


def _simulate_knockout_with_final_tracking(
    ensemble_service, team_objects: list, forced_winner_name: str,
    n_simulations: int
) -> dict:
    """
    对给定球队列表运行淘汰赛 Monte Carlo 模拟，同时追踪决赛对阵分布。

    返回 champion_counts, final_matchup_counts。
    final_matchup_counts 记录每次模拟中进入决赛的两支球队（排序后的 tuple）。
    """
    champion_counts = defaultdict(int)
    final_matchup_counts = defaultdict(int)

    for sim in range(n_simulations):
        current_round = list(team_objects)
        np.random.shuffle(current_round)

        # 淘汰赛模拟
        while len(current_round) > 1:
            next_round = []
            for i in range(0, len(current_round), 2):
                if i + 1 < len(current_round):
                    home = current_round[i]
                    away = current_round[i + 1]
                    pred = _simulate_match(ensemble_service, home, away)
                    if pred['home_score'] > pred['away_score']:
                        next_round.append(home)
                    elif pred['away_score'] > pred['home_score']:
                        next_round.append(away)
                    else:
                        if home.current_elo >= away.current_elo:
                            next_round.append(home)
                        else:
                            next_round.append(away)
                else:
                    next_round.append(current_round[i])
            # 如果下一轮只剩 2 队 → 这就是决赛对阵
            if len(next_round) == 2:
                finalists = sorted([next_round[0].name, next_round[1].name])
                final_matchup_counts[tuple(finalists)] += 1
            current_round = next_round

        champion = current_round[0]
        champion_counts[champion.name] += 1

    return champion_counts, final_matchup_counts


def _simulate_knockout(ensemble_service, team_objects: list, n_simulations: int) -> dict:
    """
    对给定球队列表运行淘汰赛 Monte Carlo 模拟。
    返回 champion_counts 和 semifinalist_counts。
    """
    champion_counts = defaultdict(int)
    semifinalist_counts = defaultdict(int)

    for sim in range(n_simulations):
        current_round = list(team_objects)
        np.random.shuffle(current_round)

        semifinalists = []
        if len(current_round) >= 4:
            semifinalists = list(current_round[:4])

        while len(current_round) > 1:
            next_round = []
            for i in range(0, len(current_round), 2):
                if i + 1 < len(current_round):
                    home = current_round[i]
                    away = current_round[i + 1]
                    pred = _simulate_match(ensemble_service, home, away)
                    if pred['home_score'] > pred['away_score']:
                        next_round.append(home)
                    elif pred['away_score'] > pred['home_score']:
                        next_round.append(away)
                    else:
                        if home.current_elo >= away.current_elo:
                            next_round.append(home)
                        else:
                            next_round.append(away)
                else:
                    next_round.append(current_round[i])
            current_round = next_round

        champion = current_round[0]
        champion_counts[champion.name] += 1

        if semifinalists:
            for sf in semifinalists:
                semifinalist_counts[sf.name] += 1

    return champion_counts, semifinalist_counts


def get_pending_knockout_matches(db) -> List[Dict]:
    """
    获取当前未结束的淘汰赛比赛列表（向后兼容）。
    新代码应优先使用 stage_info["pending_scenario_matches"]。
    """
    from app.models.agent_models import Fixture

    _KNOCKOUT_STAGES = ["semi_finals", "quarter_finals", "round_of_16", "round_of_32"]
    _PENDING_STATUSES = {"TIMED", "SCHEDULED", "NS"}

    # 先获取 stage_info 判断 sandbox 是否启用
    from app.services.tournament_state_service import get_current_tournament_stage
    stage_info = get_current_tournament_stage(db)

    if not stage_info.get("sandbox_enabled"):
        return []

    # 只返回当前阶段的未结束比赛（排除决赛、三四名决赛）
    current_stage = stage_info["stage"]
    fixtures = db.query(Fixture).filter(
        Fixture.stage == current_stage,
        Fixture.status.in_(_PENDING_STATUSES),
    ).all()

    matches = []
    for f in fixtures:
        if "TBD" in (f.home_team or "") or "TBD" in (f.away_team or ""):
            continue
        matches.append({
            "match_id": str(f.fixture_id),
            "home_team": f.home_team,
            "away_team": f.away_team,
            "stage": f.stage,
        })

    return matches


def run_scenario_simulation(
    match_id: str,
    forced_winner: str,
    simulation_count: int = 3000,
) -> dict:
    """
    运行沙盘模拟。

    Args:
        match_id: 比赛 fixture_id（如 "fd_537387" 或 "537387"）
        forced_winner: 假设的晋级球队名
        simulation_count: 模拟次数（默认 3000，适配 Render 免费实例）

    Returns:
        沙盘结果 dict，包含新结构：
        - scenario_scope: "conditional_champion_probability"
        - stage_at_creation: 当前阶段
        - is_stale: false
        - scenario, official_prediction, scenario_prediction
        - final_matchup_distribution
        - comparison, explanation
    """
    from app.db.database import SessionLocal
    from app.models.schemas import Team
    from app.services.ensemble_prediction_service import EnsemblePredictionService
    from app.services.tournament_state_service import get_current_tournament_stage

    db = SessionLocal()
    try:
        # ── 0. 获取 stage_info，检查沙盘是否启用 ──
        stage_info = get_current_tournament_stage(db)
        current_stage = stage_info["stage"]

        if not stage_info.get("sandbox_enabled"):
            return {
                "success": False,
                "stage": current_stage,
                "scenario_scope": "disabled",
                "message": stage_info.get("sandbox_message", "沙盘推演已关闭。"),
            }

        # ── 1. 校验 match_id 属于 pending_scenario_matches ──
        pending_ids = {m["match_id"] for m in stage_info.get("pending_scenario_matches", [])}
        # 兼容纯数字 ID
        normalized_id = match_id
        if not normalized_id.startswith("fd_"):
            normalized_id = f"fd_{match_id}"

        if normalized_id not in pending_ids and match_id not in pending_ids:
            return {
                "success": False,
                "error": f"比赛 {match_id} 不在当前阶段可推演列表中。"
                         f"可选: {[m['match_id'] for m in stage_info.get('pending_scenario_matches', [])]}"
            }

        # ── 2. 查找比赛 ──
        from app.models.agent_models import Fixture

        fixture = db.query(Fixture).filter(
            (Fixture.fixture_id == normalized_id) | (Fixture.fixture_id == match_id)
        ).first()

        # Fallback: DB 为空时（Render 部署），从 stage_info 的 pending_scenario_matches 获取比赛信息
        if not fixture:
            for m in stage_info.get("pending_scenario_matches", []):
                if m.get("match_id") in (normalized_id, match_id):
                    fixture = m
                    break

        if not fixture:
            return {"success": False, "error": f"找不到比赛 {match_id}"}

        # 兼容 dict（fallback 来源）和 ORM 对象
        if isinstance(fixture, dict):
            home_team_name = fixture.get("home_team", "")
            away_team_name = fixture.get("away_team", "")
            stage = fixture.get("stage", current_stage)
        else:
            home_team_name = fixture.home_team
            away_team_name = fixture.away_team
            stage = fixture.stage

        # ── 3. 校验 forced_winner ──
        if forced_winner not in (home_team_name, away_team_name):
            return {
                "success": False,
                "error": f"{forced_winner} 不是该场比赛球队。可选: {home_team_name}, {away_team_name}"
            }

        forced_loser = away_team_name if forced_winner == home_team_name else home_team_name
        match_label = f"{home_team_name} vs {away_team_name}"
        # stage 已在上面 dict/ORM 兼容处理中设置，不再重复赋值

        # ── 半决赛阶段专用路径（任务 7-12） ──
        if stage == "semi_finals":
            logger.info(f"[Scenario] 半决赛阶段，使用专用沙盘模拟路径")
            return _simulate_semi_finals_scenario(
                db=db,
                fixture=fixture,
                home_team_name=home_team_name,
                away_team_name=away_team_name,
                forced_winner=forced_winner,
                forced_loser=forced_loser,
                match_label=match_label,
                stage=stage,
                simulation_count=simulation_count,
            )

        logger.info(f"[Scenario] 沙盘推演: {match_label}, forced_winner={forced_winner}, forced_loser={forced_loser}")

        # ── 4. 获取当前存活球队 ──
        surviving_teams = stage_info["surviving_teams"]

        if forced_loser not in surviving_teams:
            return {
                "success": False,
                "error": f"{forced_loser} 已不在存活球队列表中"
            }

        # ── 5. 移除 forced_loser ──
        scenario_surviving = [t for t in surviving_teams if t != forced_loser]

        if len(scenario_surviving) < 1:
            return {"success": False, "error": "沙盘推演后无剩余球队"}

        # ── 6. 加载球队对象 ──
        teams = db.query(Team).all()
        team_by_name = {t.name: t for t in teams}

        surviving_team_objects = []
        for name in scenario_surviving:
            if name in team_by_name:
                surviving_team_objects.append(team_by_name[name])
            else:
                logger.warning(f"Team '{name}' not found in database, skipping")

        if len(surviving_team_objects) < 1:
            return {"success": False, "error": "找不到沙盘球队数据"}

        # 如果只剩 1 队，直接是冠军
        if len(surviving_team_objects) == 1:
            champion_name = surviving_team_objects[0].name
            champion_counts = {champion_name: simulation_count}
            final_matchup_counts = {}
        else:
            # ── 7. 预计算特征缓存 ──
            ensemble_service = EnsemblePredictionService(db)
            team_feature_cache = {}
            for team in surviving_team_objects:
                try:
                    feats = ensemble_service._build_team_features_dict(team, is_home=True)
                    team_feature_cache[team.id] = feats
                except Exception as e:
                    logger.warning(f"Failed to cache features for {team.name}: {e}")

            original_build_dict = ensemble_service._build_team_features_dict
            def cached_build_dict(team, is_home=True):
                if team.id in team_feature_cache:
                    return team_feature_cache[team.id]
                return original_build_dict(team, is_home)
            ensemble_service._build_team_features_dict = cached_build_dict

            # ── 8. Monte Carlo 模拟（含决赛对阵追踪） ──
            logger.info(f"[Scenario] 开始 {simulation_count} 次沙盘模拟，存活球队: {scenario_surviving}")
            champion_counts, final_matchup_counts = _simulate_knockout_with_final_tracking(
                ensemble_service, surviving_team_objects, forced_winner, simulation_count
            )

        # ── 9. 计算概率 ──
        total = sum(champion_counts.values())
        assert total == simulation_count, f"champion_counts sum ({total}) != {simulation_count}"

        champion_probs = {
            team: count / total
            for team, count in sorted(champion_counts.items(), key=lambda x: -x[1])
        }

        prob_sum = sum(champion_probs.values())
        assert abs(prob_sum - 1.0) < 0.01, f"概率总和 ({prob_sum:.6f}) 偏离 1.0"

        # forced_loser 概率必须为 0
        assert forced_loser not in champion_probs or champion_probs[forced_loser] == 0, \
            f"{forced_loser} 在沙盘中仍有夺冠概率"

        # ── 10. 构建 champion_distribution ──
        champion_distribution = [
            {
                "name": team,
                "count": champion_counts.get(team, 0),
                "probability": round(champion_probs.get(team, 0), 4),
            }
            for team in champion_probs
        ]

        # forced_loser 也要出现在分布中（概率为 0）
        if forced_loser not in champion_probs:
            champion_distribution.append({
                "name": forced_loser,
                "count": 0,
                "probability": 0.0,
            })
            # 重新排序
            champion_distribution.sort(key=lambda x: -x["probability"])

        scenario_champion = champion_distribution[0]["name"] if champion_distribution else "Unknown"
        scenario_champion_prob = champion_distribution[0]["probability"] if champion_distribution else 0

        # ── 11. 构建 final_matchup_distribution ──
        final_matchup_distribution = []
        if final_matchup_counts:
            total_matchups = sum(final_matchup_counts.values())
            for matchup, count in sorted(final_matchup_counts.items(), key=lambda x: -x[1]):
                final_matchup_distribution.append({
                    "matchup": f"{matchup[0]} vs {matchup[1]}",
                    "count": count,
                    "probability": round(count / total_matchups, 4),
                })

        # ── 12. 加载正式预测结果用于对比 ──
        official_prediction = _load_official_prediction()

        # ── 13. 构建 comparison ──
        comparison = _build_comparison(
            champion_probs, official_prediction, forced_loser
        )

        # ── 14. 生成 AI 解释 ──
        explanation = _generate_scenario_explanation(
            scenario={
                "match": match_label,
                "stage": stage,
                "forced_winner": forced_winner,
                "forced_loser": forced_loser,
            },
            champion_distribution=champion_distribution,
            official_result=official_prediction,
            final_matchup_distribution=final_matchup_distribution,
        )

        # ── 15. 构建 impact_summary ──
        biggest_beneficiary = _find_biggest_beneficiary(comparison, forced_winner)
        impact_summary = {
            "official_champion_before": official_prediction.get("champion", "Unknown"),
            "scenario_champion": scenario_champion,
            "eliminated_team": forced_loser,
            "biggest_beneficiary": biggest_beneficiary,
            "biggest_loser": forced_loser,
        }

        # ── 16. 构建 official_prediction 输出 ──
        official_top5 = official_prediction.get("top5", [])
        official_top_candidates = [
            {"name": t.get("team", ""), "probability": t.get("probability", 0)}
            for t in official_top5
        ]

        # ── 17. 构建 scenario_prediction 输出 ──
        scenario_top_candidates = [
            {"name": cd["name"], "probability": cd["probability"]}
            for cd in champion_distribution
        ]

        # ── 18. 构建结果（新结构） ──
        result = {
            "success": True,
            "created_at": datetime.utcnow().isoformat(),
            "scenario_scope": "conditional_champion_probability",
            "stage_at_creation": current_stage,
            "is_stale": False,

            "scenario": {
                "match_id": fixture.get("match_id", "") if isinstance(fixture, dict) else str(fixture.fixture_id),
                "match": match_label,
                "stage": stage,
                "forced_winner": forced_winner,
                "forced_loser": forced_loser,
                "note": "假设结果，不影响真实赛果",
            },

            "simulation_count": simulation_count,

            "official_prediction": {
                "champion": official_prediction.get("champion", "Unknown"),
                "probability": official_prediction.get("champion_probability", 0),
                "top_candidates": official_top_candidates,
            },

            "scenario_prediction": {
                "champion": scenario_champion,
                "probability": scenario_champion_prob,
                "top_candidates": scenario_top_candidates,
            },

            "final_matchup_distribution": final_matchup_distribution,

            "champion_distribution": champion_distribution,
            "comparison": comparison,
            "impact_summary": impact_summary,
            "explanation": explanation,
        }

        # ── 19. 保存 ──
        _save_scenario_result(result)

        logger.info(f"[Scenario] 沙盘推演完成: {forced_winner} 淘汰 {forced_loser}, "
                     f"新冠军={scenario_champion} ({scenario_champion_prob:.2%})")

        return result

    except Exception as e:
        logger.error(f"[Scenario] 沙盘推演失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
    finally:
        db.close()


def _load_official_prediction() -> dict:
    """加载正式预测结果"""
    try:
        if FINAL_RESULT_PATH.exists():
            with open(FINAL_RESULT_PATH, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"加载正式预测结果失败: {e}")
    return {}


def _build_comparison(
    scenario_probs: dict,
    official_result: dict,
    forced_loser: str,
) -> list:
    """构建沙盘 vs 正式预测的对比表"""
    official_top5 = official_result.get("top5", [])
    official_probs = {}
    for t in official_top5:
        name = t.get("team", "")
        prob = float(t.get("probability", 0))
        official_probs[name] = prob

    # 合并所有出现过的球队
    all_teams = set(list(scenario_probs.keys()) + list(official_probs.keys()))
    # 确保 forced_loser 也在列表中
    all_teams.add(forced_loser)

    comparison = []
    for name in all_teams:
        official_p = official_probs.get(name, 0)
        scenario_p = scenario_probs.get(name, 0)
        delta = scenario_p - official_p

        if name == forced_loser:
            trend = "eliminated"
        elif delta > 0.001:
            trend = "up"
        elif delta < -0.001:
            trend = "down"
        else:
            trend = "same"

        comparison.append({
            "name": name,
            "official_probability": round(official_p, 4),
            "scenario_probability": round(scenario_p, 4),
            "delta": round(delta, 4),
            "trend": trend,
        })

    # 按沙盘概率降序
    comparison.sort(key=lambda x: -x["scenario_probability"])
    return comparison


def _find_biggest_beneficiary(comparison: list, forced_winner: str) -> str:
    """找出最大受益者（delta 最大且不是 forced_winner 本身）"""
    candidates = [
        c for c in comparison
        if c["name"] != forced_winner and c["trend"] != "eliminated"
    ]
    if not candidates:
        return forced_winner
    best = max(candidates, key=lambda x: x["delta"])
    return best["name"]


def _generate_scenario_explanation(
    scenario: dict,
    champion_distribution: list,
    official_result: dict,
    final_matchup_distribution: list = None,
) -> str:
    """生成沙盘 AI 解释"""
    forced_winner = scenario["forced_winner"]
    forced_loser = scenario["forced_loser"]
    match = scenario["match"]
    stage = scenario.get("stage", "")

    stage_name = {
        "semi_finals": "半决赛",
        "quarter_finals": "四分之一决赛",
        "round_of_16": "十六强赛",
        "final": "决赛",
    }.get(stage, stage)

    # 构建解释
    lines = []
    lines.append(f"**沙盘假设：{match}，{forced_winner} 晋级**\n")
    lines.append(f"在该假设下，{forced_loser} 在{stage_name}阶段被淘汰，"
                 f"{forced_winner} 晋级后续赛程。\n")

    # 可能决赛对阵（如果有）
    if final_matchup_distribution:
        lines.append("**可能决赛对阵：**")
        for fm in final_matchup_distribution[:3]:
            pct = f"{fm['probability'] * 100:.1f}%"
            lines.append(f"- {fm['matchup']}：{pct}")
        lines.append("")

    # 分析变化
    top3 = [cd for cd in champion_distribution if cd["name"] != forced_loser][:3]
    if top3:
        lines.append(f"**新的夺冠格局：**")
        for cd in top3:
            pct = f"{cd['probability'] * 100:.1f}%"
            lines.append(f"- {cd['name']}：{pct}")
        # forced_loser
        lines.append(f"- {forced_loser}：0.0%（淘汰）")
        lines.append("")

    # 对比正式预测
    official_champion = official_result.get("champion", "Unknown")
    scenario_champion = champion_distribution[0]["name"] if champion_distribution else "Unknown"

    if official_champion == scenario_champion:
        lines.append(f"**影响分析：** 即使 {forced_loser} 被淘汰，{official_champion} 仍然是最有可能夺冠的球队，"
                     f"但其夺冠概率发生了变化。")
    else:
        lines.append(f"**影响分析：** 由于 {forced_loser} 被淘汰，冠军竞争格局发生变化，"
                     f"{scenario_champion} 成为该假设下最有可能夺冠的球队。")

    lines.append(f"\n该结果仅为条件推演，不影响正式冠军预测。")

    return "\n".join(lines)


def _save_scenario_result(result: dict):
    """保存沙盘结果到 data/scenario_result.json"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(SCENARIO_RESULT_PATH, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"[Scenario] 结果已保存到 {SCENARIO_RESULT_PATH}")
    except Exception as e:
        logger.error(f"[Scenario] 保存失败: {e}")


def load_latest_scenario() -> dict:
    """
    加载最新的沙盘结果，并检查是否过期（is_stale）。
    如果 stage_at_creation != 当前 stage，标记为 stale。
    """
    try:
        if SCENARIO_RESULT_PATH.exists():
            with open(SCENARIO_RESULT_PATH, encoding="utf-8") as f:
                data = json.load(f)

            # 检查是否过期
            if data.get("success") and data.get("stage_at_creation"):
                from app.db.database import SessionLocal
                from app.services.tournament_state_service import get_current_tournament_stage
                db = SessionLocal()
                try:
                    current_stage_info = get_current_tournament_stage(db)
                finally:
                    db.close()

                current_stage = current_stage_info.get("stage", "unknown")
                if data["stage_at_creation"] != current_stage:
                    data["is_stale"] = True
                    return {
                        "success": False,
                        "is_stale": True,
                        "message": "沙盘结果已过期，请基于最新赛况重新推演。",
                        "stage": current_stage,
                    }

                # 如果当前阶段沙盘已关闭，也标记为不可用
                if not current_stage_info.get("sandbox_enabled"):
                    return {
                        "success": False,
                        "is_stale": True,
                        "message": current_stage_info.get("sandbox_message", "沙盘推演已关闭。"),
                        "stage": current_stage,
                    }

            return data
    except Exception as e:
        logger.warning(f"加载沙盘结果失败: {e}")
    return {"success": False, "message": "暂无沙盘推演结果"}
