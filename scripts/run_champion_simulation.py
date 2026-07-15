"""
冠军模拟 V3 — 10000 次 Monte Carlo 模拟（支持 surviving_teams 过滤）

使用集成预测服务 V2（含 NN V2 + XGBoost）
输出: champion_probability + simulation_distribution.json

运行:
    python scripts/run_champion_simulation.py

特性:
    - 自动从 fixtures 表识别 surviving_teams（仍有夺冠可能的球队）
    - 已淘汰球队不参与模拟
    - 只模拟剩余赛程（半决赛/决赛等）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
import numpy as np
from collections import defaultdict
from sqlalchemy import text

from app.db.database import SessionLocal
from app.models.schemas import Team
from app.services.ensemble_prediction_service import EnsemblePredictionService
from app.services.tournament_state_service import get_surviving_teams_from_fixtures

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

_FINISHED_STATUSES = {"FT", "FINISHED", "AET", "PEN"}


def _get_bracket_state(db) -> dict:
    """
    查询 DB 中的半决赛/决赛 fixtures，判断当前 bracket 状态。

    返回:
        {
            "finalists": ["Spain"],          # 已晋级决赛的球队（赢了已结束的半决赛）
            "pending_semis": [("England", "Argentina")],  # 未结束的半决赛配对
            "has_final": False,              # 决赛 fixture 是否已有真实球队
        }
    """
    from app.models.agent_models import Fixture

    sf_fixtures = (
        db.query(Fixture)
        .filter(Fixture.stage == "semi_finals")
        .all()
    )
    final_fixtures = (
        db.query(Fixture)
        .filter(Fixture.stage == "final")
        .all()
    )

    finalists = []
    pending_semis = []

    for f in sf_fixtures:
        if f.status in _FINISHED_STATUSES and f.winner:
            # 已结束的半决赛 → 胜者晋级决赛
            if f.winner == f.home_team or f.winner == f.away_team:
                finalists.append(f.winner)
        else:
            # 未结束的半决赛
            if not _is_placeholder(f.home_team) and not _is_placeholder(f.away_team):
                pending_semis.append((f.home_team, f.away_team))

    # 检查决赛是否已有真实球队
    has_final = False
    for f in final_fixtures:
        if not _is_placeholder(f.home_team) and not _is_placeholder(f.away_team):
            has_final = True
            break

    return {
        "finalists": finalists,
        "pending_semis": pending_semis,
        "has_final": has_final,
    }


def _is_placeholder(team_name: str) -> bool:
    """判断球队名是否为占位符（TBD / Winner of 等）"""
    if not team_name:
        return True
    lower = team_name.lower().strip()
    return lower in ("", "tbd", "null", "none") or lower.startswith("winner")


def simulate_match(ensemble_service, home_team, away_team) -> dict:
    """模拟单场比赛 - 根据概率采样结果"""
    try:
        pred = ensemble_service.predict_with_ensemble(home_team, away_team)
        probs = pred.get('probabilities', {})
        home_win_prob = probs.get('home_win', 0.5)
        draw_prob = probs.get('draw', 0.25)
        away_win_prob = probs.get('away_win', 0.25)

        # 根据概率采样比赛结果
        outcome = np.random.random()
        if outcome < home_win_prob:
            # 主队赢
            home_score = int(round(max(0, 1.5 + (home_team.current_elo - away_team.current_elo) / 400 + 0.5)))
            away_score = int(round(max(0, 1.5 - (home_team.current_elo - away_team.current_elo) / 400 - 0.5)))
            if home_score <= away_score:
                home_score = away_score + 1
        elif outcome < home_win_prob + draw_prob:
            # 平局
            home_score = int(round(max(0, 1.5 + (home_team.current_elo - away_team.current_elo) / 400)))
            away_score = home_score
        else:
            # 客队赢
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


def simulate_tournament(n_simulations: int = 10000, surviving_teams: list = None):
    """
    模拟锦标赛。

    Args:
        n_simulations: 模拟次数
        surviving_teams: 仍有夺冠可能的球队列表。
                        如果为 None，自动从 fixtures 表识别。
    """
    db = SessionLocal()
    ensemble_service = EnsemblePredictionService(db)

    try:
        # ── 识别 surviving_teams（动态阶段识别） ──
        if surviving_teams is None:
            from app.services.tournament_state_service import get_current_tournament_stage
            stage_info = get_current_tournament_stage(db)
            surviving_teams = stage_info["surviving_teams"]
            stage = stage_info["stage"]
            logger.info(f"Auto-detected stage={stage}, surviving_teams={surviving_teams}")
        else:
            stage = _infer_stage_from_count(len(surviving_teams))
            logger.info(f"Using provided surviving_teams={surviving_teams} (stage={stage})")

        if not surviving_teams:
            logger.error("No surviving teams found! Cannot simulate.")
            return None

        # ── 冠军已产生：跳过 Monte Carlo ──
        if stage in ("completed", "tournament_ended") or len(surviving_teams) == 1:
            champion_name = surviving_teams[0]
            logger.info(f"Tournament completed. Champion: {champion_name}")
            results = {
                'n_simulations': 0,
                'surviving_teams': surviving_teams,
                'stage': 'completed',
                'champion_probabilities': {champion_name: 1.0},
                'top_champion': champion_name,
                'top_probability': 1.0,
                'top5': [{'team': champion_name, 'probability': 1.0}],
                'france_champion_probability': 0.0 if champion_name != 'France' else 1.0,
                'argentina_champion_probability': 0.0 if champion_name != 'Argentina' else 1.0,
            }
            # 保存
            output_file = "data/champion_prediction_ensemble.json"
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            distribution = {
                'n_simulations': 0,
                'surviving_teams': surviving_teams,
                'stage': 'completed',
                'champion': {champion_name: 1.0},
                'champion_counts': {champion_name: 1},
                'semifinalist': {champion_name: 1.0},
                'semifinalist_counts': {champion_name: 1},
            }
            with open("data/simulation_distribution.json", 'w', encoding='utf-8') as f:
                json.dump(distribution, f, indent=2, ensure_ascii=False)
            return results

        # ── 加载球队数据 ──
        teams = db.query(Team).all()
        team_by_name = {t.name: t for t in teams}

        # 获取 surviving_teams 对应的 Team 对象（DB 为空时自动创建）
        surviving_team_objects = []
        for name in surviving_teams:
            if name in team_by_name:
                surviving_team_objects.append(team_by_name[name])
            else:
                logger.warning(f"Team '{name}' not found in database, auto-creating with default ELO")
                new_team = Team(name=name, current_elo=1500.0, confederation=None)
                try:
                    db.add(new_team)
                    db.commit()
                    db.refresh(new_team)
                    surviving_team_objects.append(new_team)
                    team_by_name[name] = new_team
                    logger.info(f"Created team: {name} (ID: {new_team.id})")
                except Exception as e:
                    db.rollback()
                    logger.error(f"Failed to create team {name}: {e}")

        if len(surviving_team_objects) < 2:
            logger.error(f"Need at least 2 surviving teams, got {len(surviving_team_objects)}")
            return None

        logger.info(f"Simulating with {len(surviving_team_objects)} surviving teams: "
                     f"{[t.name for t in surviving_team_objects]}")

        # ── 预计算特征缓存 ──
        logger.info(f"Pre-computing features for {len(surviving_team_objects)} teams...")
        team_feature_cache = {}
        for team in surviving_team_objects:
            try:
                feats = ensemble_service._build_team_features_dict(team, is_home=True)
                team_feature_cache[team.id] = feats
            except Exception as e:
                logger.warning(f"Failed to cache features for {team.name}: {e}")

        logger.info(f"Feature caching complete: {len(team_feature_cache)} teams")

        # Monkey-patch ensemble_service to use cached features
        original_build_dict = ensemble_service._build_team_features_dict
        def cached_build_dict(team, is_home=True):
            if team.id in team_feature_cache:
                return team_feature_cache[team.id]
            return original_build_dict(team, is_home)
        ensemble_service._build_team_features_dict = cached_build_dict

        # ── 探测 bracket 状态（支持部分半决赛已结束的 scenario）──
        bracket_state = None
        try:
            bracket_state = _get_bracket_state(db)
            if bracket_state["finalists"] or bracket_state["pending_semis"]:
                logger.info(
                    f"[Bracket] finalists={bracket_state['finalists']}, "
                    f"pending_semis={bracket_state['pending_semis']}, "
                    f"has_final={bracket_state['has_final']}"
                )
        except Exception as e:
            logger.warning(f"[Bracket] 无法探测 bracket 状态: {e}")
            bracket_state = None

        use_bracket = (
            bracket_state
            and (bracket_state["finalists"] or bracket_state["pending_semis"])
        )

        # ── 模拟 ──
        champion_counts = defaultdict(int)
        finalist_counts = defaultdict(int)
        semifinalist_counts = defaultdict(int)

        surviving_names_set = set(surviving_teams)

        for sim in range(n_simulations):
            if (sim + 1) % 1000 == 0:
                logger.info(f"Simulation {sim + 1}/{n_simulations}")

            if use_bracket:
                # ── bracket-aware 模拟：尊重已完成的半决赛结果 ──
                # 1. 已晋级决赛的球队
                finalists_in_final = list(bracket_state["finalists"])

                # 2. 模拟未结束的半决赛
                pending_winners = []
                for home_name, away_name in bracket_state["pending_semis"]:
                    home_obj = team_by_name.get(home_name)
                    away_obj = team_by_name.get(away_name)
                    if home_obj and away_obj:
                        pred = simulate_match(ensemble_service, home_obj, away_obj)
                        if pred['home_score'] > pred['away_score']:
                            pending_winners.append(home_obj)
                        elif pred['away_score'] > pred['home_score']:
                            pending_winners.append(away_obj)
                        else:
                            if home_obj.current_elo >= away_obj.current_elo:
                                pending_winners.append(home_obj)
                            else:
                                pending_winners.append(away_obj)

                # 3. 组合：已晋级球队 + 半决赛胜者 → 决赛
                final_participants = []
                for name in finalists_in_final:
                    obj = team_by_name.get(name)
                    if obj:
                        final_participants.append(obj)
                final_participants.extend(pending_winners)

                # 4. 模拟决赛
                if len(final_participants) == 1:
                    champion = final_participants[0]
                elif len(final_participants) >= 2:
                    # 如果决赛已有两支球队（has_final=True），直接模拟
                    # 如果只有两支球队，直接模拟
                    np.random.shuffle(final_participants)
                    current_round = final_participants
                    while len(current_round) > 1:
                        next_round = []
                        for i in range(0, len(current_round), 2):
                            if i + 1 < len(current_round):
                                home = current_round[i]
                                away = current_round[i + 1]
                                pred = simulate_match(ensemble_service, home, away)
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
                else:
                    # 不应发生
                    continue

            else:
                # ── 原始随机配对模拟（无 bracket 信息时使用）──
                current_round = list(surviving_team_objects)
                np.random.shuffle(current_round)

                while len(current_round) > 1:
                    next_round = []
                    for i in range(0, len(current_round), 2):
                        if i + 1 < len(current_round):
                            home = current_round[i]
                            away = current_round[i + 1]

                            pred = simulate_match(ensemble_service, home, away)

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

            # ── 断言：冠军必须属于 surviving_teams ──
            assert champion.name in surviving_names_set, (
                f"Champion '{champion.name}' is NOT in surviving_teams {surviving_teams}! "
                f"This should never happen."
            )

            champion_counts[champion.name] += 1

            # 记录四强：所有 surviving teams 都是四强
            for t in surviving_team_objects:
                semifinalist_counts[t.name] += 1

        # ── 计算概率 ──
        total = sum(champion_counts.values())

        # ── Monte Carlo 断言验证 ──
        assert total == n_simulations, (
            f"champion_counts 总和 ({total}) != n_simulations ({n_simulations})"
        )

        # ── 断言：所有冠军必须属于 surviving_teams ──
        for team_name in champion_counts:
            assert team_name in surviving_names_set, (
                f"Team '{team_name}' appears in champion_counts but is NOT in "
                f"surviving_teams {surviving_teams}!"
            )

        champion_probs = {
            team: count / total
            for team, count in sorted(champion_counts.items(), key=lambda x: -x[1])
        }

        # 概率总和必须 ≈ 1.0
        prob_sum = sum(champion_probs.values())
        assert abs(prob_sum - 1.0) < 0.01, (
            f"概率总和 ({prob_sum:.6f}) 偏离 1.0 超过 1%"
        )
        logger.info(f"Monte Carlo 验证通过: {total} 次模拟, {len(champion_counts)} 支冠军球队, 概率总和={prob_sum:.6f}")

        semifinalist_probs = {
            team: count / total
            for team, count in sorted(semifinalist_counts.items(), key=lambda x: -x[1])
        }

        # ── 构建结果 ──
        all_candidates = list(champion_probs.items())
        display_count = min(5, len(surviving_teams))
        top_candidates = all_candidates[:display_count]

        results = {
            'n_simulations': n_simulations,
            'surviving_teams': surviving_teams,
            'stage': stage,
            'champion_probabilities': dict(all_candidates),
            'top_champion': top_candidates[0][0] if top_candidates else None,
            'top_probability': top_candidates[0][1] if top_candidates else 0,
            'top5': [{'team': t, 'probability': round(p, 4)} for t, p in top_candidates],
            'france_champion_probability': champion_probs.get('France', 0),
            'argentina_champion_probability': champion_probs.get('Argentina', 0),
        }

        # 保存冠军概率
        output_file = "data/champion_prediction_ensemble.json"
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"Champion prediction saved to {output_file}")

        # ── 保存完整分布（只含 surviving_teams）──
        distribution = {
            'n_simulations': n_simulations,
            'surviving_teams': surviving_teams,
            'stage': stage,
            'champion': {t: round(p, 4) for t, p in all_candidates},
            'champion_counts': {t: c for t, c in champion_counts.items()},
            'semifinalist': {t: round(p, 4) for t, p in semifinalist_probs.items()},
            'semifinalist_counts': {t: c for t, c in semifinalist_counts.items()},
        }
        dist_file = "data/simulation_distribution.json"
        with open(dist_file, 'w', encoding='utf-8') as f:
            json.dump(distribution, f, indent=2, ensure_ascii=False)
        logger.info(f"Distribution saved to {dist_file}")

        # 打印结果
        logger.info(f"\n{'='*60}")
        logger.info(f"冠军模拟结果 ({n_simulations} 次) | 阶段: {stage}")
        logger.info(f"Surviving teams: {surviving_teams}")
        logger.info(f"{'='*60}")
        logger.info(f"\n冠军概率:")
        for i, (team, prob) in enumerate(all_candidates):
            logger.info(f"  {i+1}. {team}: {prob:.2%}")

        return results

    finally:
        db.close()


def _infer_stage_from_count(n_teams: int) -> str:
    """根据球队数量推断阶段"""
    if n_teams <= 1:
        return "tournament_ended"
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


if __name__ == "__main__":
    results = simulate_tournament(n_simulations=10000)

    if results:
        print("\n=== 冠军模拟完成 ===")
        print(f"当前阶段: {results.get('stage', 'unknown')}")
        print(f"Surviving teams: {results.get('surviving_teams', [])}")
        print(f"最可能冠军: {results['top_champion']} ({results['top_probability']:.2%})")
        print(f"Top {len(results['top5'])}:")
        for item in results['top5']:
            print(f"  {item['team']}: {item['probability']:.2%}")
        print(f"法国: {results['france_champion_probability']:.2%}")
        print(f"阿根廷: {results['argentina_champion_probability']:.2%}")
