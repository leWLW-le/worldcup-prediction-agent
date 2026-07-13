"""
淘汰赛推演工具

负责：小组赛预测 → 积分榜 → 晋级 → 淘汰赛逐轮推演 → 冠军/亚军
复用 tournament_sim.py 的赛制逻辑。
数据源仅来自 fixtures 表：FINISHED 比赛使用真实比分，其余使用 EnsemblePredictor 预测。
"""

import logging
import random
from typing import Any, Dict

from app.services.tournament_sim import (
    simulate_group_stage,
    simulate_knockout_stage,
    simulate_knockout_match,
    ProbabilityEngine,
    KNOCKOUT_BRACKET,
    resolve_knockout_matchup,
)
from app.tools.match_predictor_tool import MatchPredictorTool
from app.services.fixture_repository import FixtureRepository

logger = logging.getLogger(__name__)


class BracketTool:
    """淘汰赛推演工具"""

    def __init__(self, seed: int | None = None):
        self.seed = seed

    def predict_group_stage(
        self,
        groups: list[list[tuple]],
        team_features: dict[str, dict],
        predictor: MatchPredictorTool,
    ) -> dict[str, Any]:
        """
        预测小组赛。使用 tournament_sim 模拟。

        Args:
            groups: 12 个小组，每组 [(team_id, team_name, elo), ...]
            team_features: {team_name: {power_score, ...}}
            predictor: MatchPredictorTool 实例

        Returns:
            {group_predictions: [...], tournament_result: {...}}
        """
        # 使用 tournament_sim 模拟小组赛
        tournament_result = simulate_group_stage(
            groups=[[(int(tid), str(name), float(elo)) for tid, name, elo in group] for group in groups],
            seed=self.seed
        )

        # 生成可解释的小组赛预测结果
        group_predictions = []
        for gr in tournament_result["group_results"]:
            group_name = gr["group_name"]
            standings = gr["standings"]
            matches_in_group = []

            # 从 standings 反推比赛
            teams_in_group = [(s["team_id"], s["team_name"]) for s in standings]
            for i in range(len(teams_in_group)):
                for j in range(i + 1, len(teams_in_group)):
                    _, name_a = teams_in_group[i]
                    _, name_b = teams_in_group[j]
                    feat_a = team_features.get(name_a, {})
                    feat_b = team_features.get(name_b, {})
                    pred = predictor.predict_match(
                        {"team_name": name_a, **feat_a},
                        {"team_name": name_b, **feat_b},
                        stage="group",
                    )
                    matches_in_group.append({
                        **pred,
                        "source": "agent_prediction",
                    })

            group_predictions.append({
                "group_name": group_name,
                "standings": standings,
                "qualified_teams": gr["qualified_teams"],
                "matches": matches_in_group,
            })

        return {
            "group_predictions": group_predictions,
            "tournament_result": tournament_result,
        }

    def calculate_group_standings(
        self, group_predictions: list[dict]
    ) -> list[dict]:
        """从 group_predictions 提取积分榜"""
        standings_map = []
        for gp in group_predictions:
            standings_map.append({"group_name": gp["group_name"], "standings": gp["standings"]})
        return standings_map

    def build_knockout_bracket(
        self, tournament_result: dict
    ) -> dict[str, Any]:
        """从小组赛结果构建淘汰赛对阵"""
        return {
            "qualified_32": tournament_result["qualified_32"],
            "group_results": tournament_result["group_results"],
            "third_places_ranking": tournament_result["third_places_ranking"],
        }

    def predict_knockout_stage(
        self,
        bracket: dict[str, Any],
        team_features: dict[str, dict],
        predictor: MatchPredictorTool,
    ) -> dict[str, Any]:
        """
        Updated to ensure bracket_payload includes all required fields and matches have consistent structure.
        """
        repo = FixtureRepository()
        db_knockout = repo.get_knockout_fixtures()
        if db_knockout:
            logger.info(f"从 fixtures 表读取 {len(db_knockout)} 场淘汰赛真实数据")
            return self._build_from_db_knockout_data(db_knockout, bracket, team_features, predictor)

        group_results = bracket["group_results"]
        third_places = bracket["third_places_ranking"]

        knockout_result = simulate_knockout_stage(
            group_results, third_places, seed=self.seed
        )

        knockout_predictions = []
        bracket_payload = {
            "round_of_32": [],
            "round_of_16": [],
            "quarter_finals": [],
            "semi_finals": [],
            "final": [],
            "champion": {
                "team": None,
                "probability": None,
                "source": "unknown",
                "status": "unknown",
            },
            "runner_up": {
                "team": None,
                "source": "unknown",
            },
        }

        for round_key, round_label in [
            ("round_of_32", "round_of_32"),
            ("round_of_16", "round_of_16"),
            ("quarter_finals", "quarter_finals"),
            ("semi_finals", "semi_finals"),
            ("final", "final"),
        ]:
            round_data = knockout_result.get(round_key, {})
            for match in round_data.get("matches", []):
                home_name = match["team_a_name"]
                away_name = match["team_b_name"]
                winner_name = match["winner_name"]

                feat_a = team_features.get(home_name, {})
                feat_b = team_features.get(away_name, {})
                predictor.predict_match(
                    {"team_name": home_name, **feat_a},
                    {"team_name": away_name, **feat_b},
                    stage="knockout",
                )

                match_payload = {
                    "round": round_label,
                    "home_team": home_name,
                    "away_team": away_name,
                    "home_score": match.get("score_a"),
                    "away_score": match.get("score_b"),
                    "predicted_score": f"{match['score_a']}-{match['score_b']}" if match.get("score_a") is not None else None,
                    "winner": winner_name,
                    "status": match.get("status", "unknown"),
                    "display_label": "已结束" if match.get("status") in self._FINISHED_STATUSES else "预测",
                    "match_source": "real_result" if match.get("status") in self._FINISHED_STATUSES else "prediction",
                    "source": "agent_prediction",
                    "is_verified": match.get("is_verified", True),
                    "needs_review": not match.get("is_verified", True),
                }

                knockout_predictions.append(match_payload)
                bracket_payload[round_label].append(match_payload)

        final_match = knockout_result.get("final", {}).get("matches", [{}])[0]
        if final_match.get("winner_name"):
            bracket_payload["champion"] = {
                "team": final_match["winner_name"],
                "probability": None,  # Add logic for probability if available
                "source": "real_result",
                "status": "confirmed",
            }
            bracket_payload["runner_up"] = {
                "team": final_match["team_b_name"] if final_match["winner_name"] == final_match["team_a_name"] else final_match["team_a_name"],
                "source": "real_result",
            }

        return {
            "bracket_payload": bracket_payload,
            "knockout_predictions": knockout_predictions,
        }

    
    # 阶段名标准映射
    _STAGE_NORMALIZE = {
        "last_32": "round_of_32",
        "last_16": "round_of_16",
        "round_of_32": "round_of_32",
        "round_of_16": "round_of_16",
        "quarter_finals": "quarter_finals",
        "quarterfinals": "quarter_finals",
        "semi_finals": "semi_finals",
        "semifinals": "semi_finals",
        "final": "final",
    }

    _FINISHED_STATUSES = {"FT", "AET", "PEN", "FINISHED"}
    _SCHEDULED_STATUSES = {"TIMED", "SCHEDULED", "NS", "TBD"}
    _LIVE_STATUSES = {"LIVE", "IN_PLAY", "1H", "2H", "HT"}

    def _normalize_stage(self, stage: str) -> str:
        """标准化阶段名"""
        return self._STAGE_NORMALIZE.get(stage.lower().strip(), stage.lower().strip())

    def _build_from_db_knockout_data(
        self,
        db_fixtures: list[dict[str, Any]],
        bracket: dict[str, Any],
        team_features: dict[str, dict],
        predictor: MatchPredictorTool,
    ) -> dict[str, Any]:
        """
        从 fixtures 表的真实淘汰赛数据构建预测结果。
        已结束的比赛使用真实比分，未开始的比赛用 predictor 预测。
        尚未存在于 DB 中的轮次（如半决赛/决赛）从上一轮胜者模拟。
        如果 round_of_32 / round_of_16 不在 DB 中，从小组赛结果模拟。
        """
        engine = ProbabilityEngine()
        if self.seed is not None:
            random.seed(self.seed)

        def _get_elo(name: str) -> float:
            return team_features.get(name, {}).get("elo_rating", 1500.0)

        # 按阶段分组
        rounds: dict[str, list[dict]] = {}
        for fx in db_fixtures:
            stage = self._normalize_stage(fx.get("stage", ""))
            if stage not in rounds:
                rounds[stage] = []
            rounds[stage].append(fx)

        # 按顺序处理每一轮
        round_order = ["round_of_32", "round_of_16", "quarter_finals", "semi_finals", "final"]
        knockout_predictions = []
        # previous_round_winners: {"R32_1": (tid, name, elo)}
        previous_round_winners: dict[str, tuple] = {}

        for round_key in round_order:
            round_fixtures = rounds.get(round_key, [])

            if not round_fixtures:
                # 这一轮在 DB 中不存在，需要模拟
                if round_key in ("round_of_32", "round_of_16"):
                    # 从小组赛结果模拟早期轮次
                    previous_round_winners = self._simulate_early_round_from_groups(
                        round_key, previous_round_winners, bracket,
                        engine, team_features, predictor, knockout_predictions,
                    )
                elif round_key == "semi_finals":
                    previous_round_winners = self._simulate_sf_from_qf_winners(
                        previous_round_winners, engine, team_features, predictor,
                        knockout_predictions,
                    )
                elif round_key == "final":
                    self._simulate_final_from_sf_winners(
                        previous_round_winners, engine, team_features, predictor,
                        knockout_predictions,
                    )
                continue

            # 过滤掉含 TBD 球队的比赛（这些需要从上一轮胜者模拟）
            real_fixtures = []
            tbd_count = 0
            for fx in round_fixtures:
                home = fx.get("home_team", "TBD")
                away = fx.get("away_team", "TBD")
                if home == "TBD" or away == "TBD":
                    tbd_count += 1
                else:
                    real_fixtures.append(fx)

            current_round_winners: dict[str, tuple] = {}
            round_prefix = {"round_of_32": "R32", "round_of_16": "R16",
                            "quarter_finals": "QF", "semi_finals": "SF"}.get(round_key, round_key.upper())

            for i, fx in enumerate(real_fixtures, 1):
                home = fx.get("home_team", "TBD")
                away = fx.get("away_team", "TBD")
                status = (fx.get("status") or "").upper()
                home_score = fx.get("home_score")
                away_score = fx.get("away_score")
                winner = fx.get("winner")

                if status in self._FINISHED_STATUSES and home_score is not None and away_score is not None:
                    # 已结束：使用真实比分
                    is_penalty = status == "PEN"
                    # 处理平局+点球的情况
                    if winner == "Draw" and is_penalty:
                        winner_name = home
                    else:
                        winner_name = winner if winner else home

                    current_round_winners[f"{round_prefix}_{i}"] = (
                        winner_name,
                        winner_name,
                        _get_elo(winner_name),
                    )

                    knockout_predictions.append({
                        "round": round_key,
                        "home_team": home,
                        "away_team": away,
                        "predicted_score": f"{home_score}-{away_score}",
                        "predicted_home_score": home_score,
                        "predicted_away_score": away_score,
                        "winner": winner_name,
                        "is_penalty_shootout": is_penalty,
                        "status": "FINISHED",
                        "source": "real_result",
                        "confidence": 1.0,
                        "reason_codes": ["real_result"],
                    })
                else:
                    # 未开始：用 predictor 预测
                    pred = predictor.predict_match(
                        {"team_name": home, **team_features.get(home, {})},
                        {"team_name": away, **team_features.get(away, {})},
                        stage="knockout",
                    )
                    pred_winner = pred.get("winner", home)
                    pred_home = pred.get("predicted_home_score", 0)
                    pred_away = pred.get("predicted_away_score", 0)
                    pred_score = f"{pred_home}-{pred_away}"

                    current_round_winners[f"{round_prefix}_{i}"] = (
                        pred_winner,
                        pred_winner,
                        _get_elo(pred_winner),
                    )

                    knockout_predictions.append({
                        "round": round_key,
                        "home_team": home,
                        "away_team": away,
                        "predicted_score": pred_score,
                        "predicted_home_score": pred_home,
                        "predicted_away_score": pred_away,
                        "winner": pred_winner,
                        "is_penalty_shootout": False,
                        "status": "SCHEDULED",
                        "source": "agent_prediction",
                        "confidence": round(pred.get("confidence", 0.6), 4),
                        "reason_codes": pred.get("reason_codes", []),
                    })

            # 如果这一轮有 TBD 比赛（SF/Final），从上一轮胜者模拟补充
            if tbd_count > 0 and round_key == "quarter_finals":
                # QF 有 TBD → 模拟 SF 和 Final
                pass  # 会在后续 round 的 "not round_fixtures" 分支处理
            elif tbd_count > 0 and round_key == "semi_finals":
                # SF 有 TBD 比赛 → 从 QF 胜者模拟缺失的 SF
                previous_round_winners = self._simulate_sf_from_qf_winners(
                    previous_round_winners, engine, team_features, predictor,
                    knockout_predictions,
                )
            elif tbd_count > 0 and round_key == "final":
                # Final 有 TBD → 从 SF 胜者模拟
                self._simulate_final_from_sf_winners(
                    previous_round_winners, engine, team_features, predictor,
                    knockout_predictions,
                )

            previous_round_winners = current_round_winners

        # 构建 knockout_result（兼容旧格式）
        knockout_result = {}
        for round_key in round_order:
            round_preds = [m for m in knockout_predictions if m["round"] == round_key]
            if round_key == "final":
                if round_preds:
                    m = round_preds[0]
                    knockout_result[round_key] = {"matches": [{
                        "team_a_name": m["home_team"], "team_b_name": m["away_team"],
                        "score_a": m["predicted_home_score"], "score_b": m["predicted_away_score"],
                        "winner_name": m["winner"],
                        "is_penalty_shootout": m.get("is_penalty_shootout", False),
                    }]}
            else:
                knockout_result[round_key] = {"matches": [
                    {"team_a_name": m["home_team"], "team_b_name": m["away_team"],
                     "score_a": m["predicted_home_score"], "score_b": m["predicted_away_score"],
                     "winner_name": m["winner"],
                     "is_penalty_shootout": m.get("is_penalty_shootout", False)}
                    for m in round_preds
                ]}

        # 提取冠军和亚军
        final_preds = [m for m in knockout_predictions if m["round"] == "final"]
        if final_preds:
            champion = final_preds[0]["winner"]
            loser = final_preds[0]["away_team"] if champion == final_preds[0]["home_team"] else final_preds[0]["home_team"]
        else:
            champion = "Unknown"
            loser = "Unknown"

        bracket_payload = self._build_bracket_payload(knockout_predictions, champion)

        return {
            "knockout_predictions": knockout_predictions,
            "champion": champion,
            "runner_up": loser,
            "knockout_result": knockout_result,
            "bracket_payload": bracket_payload,
        }

    def _simulate_early_round_from_groups(
        self, round_key: str, previous_round_winners: dict,
        bracket: dict[str, Any], engine, team_features: dict,
        predictor: MatchPredictorTool, knockout_predictions: list,
    ) -> dict[str, tuple]:
        """
        从小组赛结果模拟缺失的早期淘汰赛轮次（round_of_32 / round_of_16）。
        复用 tournament_sim 的 KNOCKOUT_BRACKET 对阵表和 resolve_knockout_matchup。
        """
        group_results = bracket.get("group_results", [])
        third_places = bracket.get("third_places_ranking", [])

        # 构建 qualified_teams_map（与 simulate_knockout_stage 相同逻辑）
        qualified_teams_map: dict[str, tuple[int, str, float]] = {}
        for group_idx, gr in enumerate(group_results):
            group_letter = chr(65 + group_idx)
            standings = gr["standings"]
            for pos_idx, pos_key in [(0, "1"), (1, "2")]:
                if pos_idx < len(standings):
                    s = standings[pos_idx]
                    qualified_teams_map[f"{group_letter}{pos_key}"] = (
                        s["team_id"], s["team_name"],
                        s.get("elo_rating", 1500.0),
                    )
        for i, third in enumerate(third_places[:8], 1):
            qualified_teams_map[f"3rd_{i}"] = (
                third["team_id"], third["team_name"],
                third.get("elo_rating", 1500.0),
            )

        matchups = KNOCKOUT_BRACKET.get(round_key, [])
        current_round_winners: dict[str, tuple] = {}
        round_prefix = "R32" if round_key == "round_of_32" else "R16"

        for i, matchup in enumerate(matchups, 1):
            try:
                team_a, team_b = resolve_knockout_matchup(
                    matchup, qualified_teams_map, previous_round_winners,
                )
            except ValueError as e:
                logger.warning(f"无法解析 {round_key} 对阵 {matchup}: {e}")
                continue

            match = simulate_knockout_match(
                engine,
                team_a[0], team_a[1], team_a[2],
                team_b[0], team_b[1], team_b[2],
                round_key.replace("_", " ").title(), i,
            )

            current_round_winners[f"{round_prefix}_{i}"] = (
                match["winner_id"],
                match["winner_name"],
                match["team_a_elo"] if match["winner_id"] == match["team_a_id"]
                else match["team_b_elo"],
            )

            pred = predictor.predict_match(
                {"team_name": match["team_a_name"],
                 **team_features.get(match["team_a_name"], {})},
                {"team_name": match["team_b_name"],
                 **team_features.get(match["team_b_name"], {})},
                stage="knockout",
            )

            knockout_predictions.append({
                "round": round_key,
                "home_team": match["team_a_name"],
                "away_team": match["team_b_name"],
                "predicted_score": f"{match['score_a']}-{match['score_b']}",
                "predicted_home_score": match["score_a"],
                "predicted_away_score": match["score_b"],
                "winner": match["winner_name"],
                "is_penalty_shootout": match.get("is_penalty_shootout", False),
                "source": "agent_prediction",
                "confidence": round(pred.get("confidence", 0.6), 4),
                "reason_codes": pred.get("reason_codes", []),
            })

        return current_round_winners

    def _simulate_sf_from_qf_winners(
        self, qf_winners, engine, team_features, predictor,
        knockout_predictions
    ) -> Dict[str, tuple]:
        """从 QF 胜者模拟半决赛"""
        sf_winners: Dict[str, tuple] = {}
        for i, (qa, qb) in enumerate(
            [("QF_1", "QF_2"), ("QF_3", "QF_4")], 1
        ):
            if qa not in qf_winners or qb not in qf_winners:
                continue
            team_a = qf_winners[qa]
            team_b = qf_winners[qb]
            match = simulate_knockout_match(
                engine,
                team_a[0], team_a[1], team_a[2],
                team_b[0], team_b[1], team_b[2],
                "Semi-finals", i,
            )
            sf_winners[f"SF_{i}"] = (
                match["winner_id"], match["winner_name"],
                match["team_a_elo"] if match["winner_id"] == match["team_a_id"]
                else match["team_b_elo"],
            )
            pred = predictor.predict_match(
                {"team_name": match["team_a_name"],
                 **team_features.get(match["team_a_name"], {})},
                {"team_name": match["team_b_name"],
                 **team_features.get(match["team_b_name"], {})},
                stage="knockout",
            )
            knockout_predictions.append({
                "round": "semi_finals",
                "home_team": match["team_a_name"],
                "away_team": match["team_b_name"],
                "predicted_score": f"{match['score_a']}-{match['score_b']}",
                "predicted_home_score": match["score_a"],
                "predicted_away_score": match["score_b"],
                "winner": match["winner_name"],
                "is_penalty_shootout": match.get("is_penalty_shootout", False),
                "source": "agent_prediction",
                "confidence": round(pred.get("confidence", 0.6), 4),
                "reason_codes": pred.get("reason_codes", []),
            })
        return sf_winners

    def _simulate_final_from_sf_winners(
        self, sf_winners, engine, team_features, predictor,
        knockout_predictions,
    ):
        """从 SF 胜者模拟决赛"""
        if "SF_1" not in sf_winners or "SF_2" not in sf_winners:
            return
        team_a = sf_winners["SF_1"]
        team_b = sf_winners["SF_2"]
        final_match = simulate_knockout_match(
            engine,
            team_a[0], team_a[1], team_a[2],
            team_b[0], team_b[1], team_b[2],
            "Final", 1,
        )
        pred = predictor.predict_match(
            {"team_name": final_match["team_a_name"],
             **team_features.get(final_match["team_a_name"], {})},
            {"team_name": final_match["team_b_name"],
             **team_features.get(final_match["team_b_name"], {})},
            stage="knockout",
        )
        knockout_predictions.append({
            "round": "final",
            "home_team": final_match["team_a_name"],
            "away_team": final_match["team_b_name"],
            "predicted_score": f"{final_match['score_a']}-{final_match['score_b']}",
            "predicted_home_score": final_match["score_a"],
            "predicted_away_score": final_match["score_b"],
            "winner": final_match["winner_name"],
            "is_penalty_shootout": final_match.get("is_penalty_shootout", False),
            "source": "agent_prediction",
            "confidence": round(pred.get("confidence", 0.6), 4),
            "reason_codes": pred.get("reason_codes", []),
        })


    # ── bracket_payload 构建辅助方法 ──

    def _build_bracket_payload(self, knockout_predictions, champion):
        """从 knockout_predictions 构建统一 bracket_payload"""
        payload = {
            "round_of_32": [],
            "round_of_16": [],
            "quarter_finals": [],
            "semi_finals": [],
            "final": [],
            "champion": {"team": champion, "probability": None, "source": "prediction", "status": "predicted"},
        }
        for m in knockout_predictions:
            rnd = m.get("round", "")
            if rnd in payload and rnd != "champion":
                payload[rnd].append(self._unify_match_fields(m))
        return payload

    def _unify_match_fields(self, m):
        """统一比赛字段"""
        status = (m.get("status") or "").upper()
        source = m.get("source", "agent_prediction")
        is_verified = m.get("is_verified", True)
        needs_review = m.get("needs_review", False)

        if needs_review or not is_verified:
            display_label, match_source = "待核验", "unverified"
        elif status in self._FINISHED_STATUSES or source in ("real_result", "real_data"):
            display_label, match_source = "已结束", "real_result"
        elif status in self._LIVE_STATUSES or source == "live_real_data":
            display_label, match_source = "进行中", "live_result"
        else:
            display_label, match_source = "预测", "prediction"

        home_score = m.get("home_score", m.get("predicted_home_score"))
        away_score = m.get("away_score", m.get("predicted_away_score"))
        predicted_score = m.get("predicted_score")
        if predicted_score is None and home_score is not None and away_score is not None:
            predicted_score = f"{home_score}-{away_score}"

        return {
            "round": m.get("round", ""),
            "home_team": m.get("home_team", ""),
            "away_team": m.get("away_team", ""),
            "home_score": home_score,
            "away_score": away_score,
            "predicted_score": predicted_score,
            "winner": m.get("winner", ""),
            "status": status or m.get("status", ""),
            "display_label": display_label,
            "match_source": match_source,
            "source": source,
            "is_verified": is_verified,
            "needs_review": needs_review,
        }
