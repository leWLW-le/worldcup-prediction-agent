"""
解释工具

封装 app/services/llm_explainer.py 的 MatchExplainerAgent。
LLM 不可用时返回规则解释，final_explanation 永远不为 null。
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ExplanationTool:
    """封装 LLM 解释为标准 Agent 工具"""

    def __init__(self):
        self._explainer = None

    def _get_explainer(self):
        """懒加载 LLM 解释器"""
        if self._explainer is None:
            try:
                from app.services.llm_explainer import MatchExplainerAgent
                from app.core.config import get_settings
                settings = get_settings()
                api_key = settings.OPENAI_API_KEY or "sk-placeholder-key"
                self._explainer = MatchExplainerAgent(
                    model_name=settings.OPENAI_MODEL,
                    api_key=api_key,
                    use_local_model=settings.USE_LOCAL_MODEL,
                )
            except Exception as e:
                logger.warning(f"[ExplanationTool] LLM 初始化失败: {e}")
                self._explainer = None
        return self._explainer

    def explain_match(
        self, prediction: Dict[str, Any], features: Dict[str, Any]
    ) -> Dict[str, Any]:
        """解释单场比赛预测"""
        home = prediction.get("home_team", "Home")
        away = prediction.get("away_team", "Away")
        score_h = prediction.get("predicted_home_score", 0)
        score_a = prediction.get("predicted_away_score", 0)
        winner = prediction.get("predicted_winner", home)
        confidence = prediction.get("confidence", 0.5)
        reason_codes = prediction.get("reason_codes", [])

        home_feat = features.get(home, {})
        away_feat = features.get(away, {})

        # 尝试 LLM 解释
        explainer = self._get_explainer()
        if explainer:
            try:
                result = explainer.explain_match(
                    team_a_name=home,
                    team_a_elo=home_feat.get("elo_rating", 1500),
                    team_b_name=away,
                    team_b_elo=away_feat.get("elo_rating", 1500),
                    score_a=score_h,
                    score_b=score_a,
                    winner_name=winner,
                    adjustment=0.0,
                    base_win_prob=confidence,
                )
                return {
                    "success": True,
                    "source": "llm",
                    "data": {
                        "tactical_analysis": result.tactical_analysis,
                        "key_player_impact": result.key_player_impact,
                        "historical_context": result.historical_context,
                        "confidence_score": result.confidence_score,
                        "prediction_summary": result.prediction_summary,
                    },
                    "error": None,
                }
            except Exception as e:
                logger.warning(f"[ExplanationTool] LLM explain_match 失败: {e}")

        # 规则解释兜底
        return {
            "success": True,
            "source": "rule_based",
            "data": {
                "tactical_analysis": f"{home} 凭借 Elo 优势 ({home_feat.get('elo_rating', 1500):.0f} vs {away_feat.get('elo_rating', 1500):.0f}) 在战术层面占优。",
                "key_player_impact": f"关键依据：{', '.join(reason_codes)}",
                "historical_context": f"基于数据模型预测 {home} {score_h}:{score_a} {away}。",
                "confidence_score": confidence,
                "prediction_summary": f"{home} {score_h}:{score_a} {away}，{winner} 获胜。",
            },
            "error": None,
        }

    def explain_champion_path(
        self,
        champion: str,
        runner_up: str,
        knockout_predictions: List[Dict],
        team_features: Dict[str, Dict],
        reasoning_steps: List[str],
    ) -> str:
        """
        生成冠军路径的完整解释文本。
        永远返回非 null 字符串。
        """
        champ_feat = team_features.get(champion, {})
        runner_feat = team_features.get(runner_up, {})

        # 收集冠军晋级路径
        champ_matches = [
            m for m in knockout_predictions
            if m.get("winner") == champion
        ]
        path_lines = []
        for m in champ_matches[-5:]:  # 最多展示 5 轮
            path_lines.append(
                f"  {m['round']}: {m['home_team']} {m['predicted_score']} {m['away_team']} → {m['winner']} 晋级"
            )

        # 尝试 LLM 生成
        explainer = self._get_explainer()
        if explainer:
            try:
                # 用决赛信息调用 LLM
                final = next(
                    (m for m in knockout_predictions if m.get("round") == "final"),
                    None,
                )
                if final:
                    result = explainer.explain_match(
                        team_a_name=final["home_team"],
                        team_a_elo=team_features.get(final["home_team"], {}).get("elo_rating", 1500),
                        team_b_name=final["away_team"],
                        team_b_elo=team_features.get(final["away_team"], {}).get("elo_rating", 1500),
                        score_a=final.get("predicted_home_score", 0),
                        score_b=final.get("predicted_away_score", 0),
                        winner_name=champion,
                    )
                    llm_text = (
                        f"【战术分析】{result.tactical_analysis}\n"
                        f"【关键球员】{result.key_player_impact}\n"
                        f"【历史背景】{result.historical_context}\n"
                    )
                else:
                    llm_text = ""
            except Exception as e:
                logger.warning(f"[ExplanationTool] LLM champion_path 失败: {e}")
                llm_text = ""
        else:
            llm_text = ""

        # 构建完整解释
        explanation_parts = [
            f"=== 2026 世界杯冠军预测：{champion} ===\n",
            f"预测冠军：{champion}",
            f"  - Elo 评分：{champ_feat.get('elo_rating', 'N/A')}",
            f"  - 综合实力：{champ_feat.get('power_score', 'N/A')}",
            f"  - 近期战绩：{champ_feat.get('recent_form', 'N/A')}",
            f"  - 数据置信度：{champ_feat.get('data_confidence', 'N/A')}",
            "",
            f"预测亚军：{runner_up}",
            f"  - Elo 评分：{runner_feat.get('elo_rating', 'N/A')}",
            f"  - 综合实力：{runner_feat.get('power_score', 'N/A')}",
            "",
            "冠军晋级路径：",
            *path_lines,
            "",
        ]

        if llm_text:
            explanation_parts.append("LLM 战术分析：")
            explanation_parts.append(llm_text)
        else:
            explanation_parts.append(
                f"基于数据模型，{champion} 凭借更高的 Elo 评分和综合实力，"
                f"在淘汰赛中连续击败对手，最终夺得冠军。"
            )

        explanation_parts.append("")
        explanation_parts.append("不确定性说明：")
        explanation_parts.append(
            "本预测基于历史数据和统计模型，足球比赛具有高度不确定性，"
            "伤病、天气、裁判等因素可能导致实际结果与预测偏差较大。"
        )

        return "\n".join(explanation_parts)
