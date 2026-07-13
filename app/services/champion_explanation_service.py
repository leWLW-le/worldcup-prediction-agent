"""
champion_explanation_service — 冠军预测解释服务

整合蒙特卡洛模拟结果 + 球队特征 + LLM，生成面向普通用户的中文解释。
禁止出现技术术语：ensemble, xgboost, neural network, 神经网络, 集成模型,
蒙特卡洛, 泊松分布, elo, feature, 特征向量, 模型融合, 权重, softmax,
focal loss, workflow, llm_planner, tool_trace, source_level, fixtures,
bracket_payload, API 等。
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 禁止在输出中出现的术语
_FORBIDDEN_TERMS = [
    "workflow", "llm_planner", "tool_trace", "source_level",
    "fixtures", "bracket_payload", "API", "ensemble", "xgboost",
    "neural network", "神经网络", "集成模型", "蒙特卡洛", "泊松分布",
    "elo", "feature", "特征向量", "模型融合", "权重", "softmax",
    "focal loss", "tree_predictor", "feature_network", "Z-score",
    "ProbabilityEngine", "MatchPredictorTool",
]


class ChampionExplanationService:
    """冠军预测解释服务"""

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm

    def generate(
        self,
        champion: str,
        champion_probability: float,
        top_contenders: List[Dict[str, Any]],
        team_features: Dict[str, Dict[str, Any]],
        knockout_predictions: List[Dict[str, Any]],
        simulation_data: Optional[Dict[str, Any]] = None,
        surviving_teams: Optional[List[str]] = None,
        stage: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        生成完整的冠军解释。

        Args:
            champion: 冠军球队名称
            champion_probability: 夺冠概率 (0-1)
            top_contenders: 前几名竞争者列表
            team_features: 球队特征字典
            knockout_predictions: 淘汰赛预测结果
            simulation_data: 模拟结果数据（可选，自动从文件加载）
            surviving_teams: 仍有夺冠可能的球队列表（可选）
            stage: 当前比赛阶段（可选，如 "semi_finals"）

        Returns:
            {
                "title": str,
                "content": str,
                "source": "llm" | "fallback",
                "champion_card": {...},
                "key_factors": [...],
            }
        """
        # 自动加载模拟数据
        if simulation_data is None:
            simulation_data = self._load_simulation_data()

        # 自动从模拟数据提取 surviving_teams 和 stage
        if surviving_teams is None:
            surviving_teams = simulation_data.get("surviving_teams",
                              simulation_data.get("distribution", {}).get("surviving_teams", []))
        if stage is None:
            stage = simulation_data.get("stage",
                    simulation_data.get("distribution", {}).get("stage", "unknown"))

        # 构建 feature_breakdown（兼容旧模块）
        feature_breakdown = self._build_feature_breakdown(team_features, champion)
        key_reasons = self._extract_key_reasons(team_features, champion)
        remaining_path = self._extract_remaining_path(knockout_predictions, champion)

        # 概率百分比
        prob_pct = round(champion_probability * 100, 1) if champion_probability <= 1 else round(champion_probability, 1)

        # 尝试 LLM
        content = None
        source = "fallback"
        if self.use_llm:
            content = self._call_llm(
                champion, prob_pct, feature_breakdown,
                key_reasons, remaining_path, simulation_data,
                surviving_teams=surviving_teams, stage=stage,
            )
            if content:
                source = "llm"

        # Fallback
        if not content:
            content = self._fallback_explanation(
                champion, prob_pct, feature_breakdown,
                key_reasons, top_contenders,
                surviving_teams=surviving_teams, stage=stage,
            )

        # 构建冠军卡片
        champion_card = self._build_champion_card(
            champion, prob_pct, feature_breakdown, key_reasons,
        )

        # 清理输出：确保不含禁止术语
        content = self._sanitize(content)

        title = f"为什么预测 {champion} 夺冠？"

        return {
            "title": title,
            "content": content,
            "source": source,
            "champion_card": champion_card,
            "key_factors": key_reasons,
        }

    def _load_simulation_data(self) -> Dict[str, Any]:
        """从文件加载模拟数据"""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        result = {}

        # 冠军概率
        champ_path = os.path.join(base_dir, "data", "champion_prediction_ensemble.json")
        if os.path.exists(champ_path):
            try:
                with open(champ_path, "r", encoding="utf-8") as f:
                    result["champion_probabilities"] = json.load(f)
            except Exception as e:
                logger.warning("Failed to load champion_prediction_ensemble.json: %s", e)

        # 模拟分布
        dist_path = os.path.join(base_dir, "data", "simulation_distribution.json")
        if os.path.exists(dist_path):
            try:
                with open(dist_path, "r", encoding="utf-8") as f:
                    result["distribution"] = json.load(f)
            except Exception as e:
                logger.warning("Failed to load simulation_distribution.json: %s", e)

        # 最终预测
        final_path = os.path.join(base_dir, "data", "final_prediction_result.json")
        if os.path.exists(final_path):
            try:
                with open(final_path, "r", encoding="utf-8") as f:
                    result["final_prediction"] = json.load(f)
            except Exception as e:
                logger.warning("Failed to load final_prediction_result.json: %s", e)

        return result

    def _build_feature_breakdown(
        self, team_features: Dict[str, Dict], champion: str,
    ) -> Dict[str, Any]:
        """从 team_features 构建特征分解"""
        feat = team_features.get(champion, {})
        return {
            "elo_rating": feat.get("elo_rating", 1500),
            "recent_form_score": feat.get("recent_form_score", 0.5),
            "attack_score": feat.get("attack_score", 0.5),
            "defense_score": feat.get("defense_score", 0.5),
            "path_advantage_score": feat.get("path_advantage_score", 0.5),
            "knockout_performance_score": feat.get("knockout_performance_score", 0.5),
            # team_strength_index: 综合实力指数（非夺冠概率）
            "team_strength_index": feat.get("team_strength_index", feat.get("overall_strength_score", 0.5)),
            "world_cup_experience": feat.get("world_cup_experience", 0),
            "win_rate_10": feat.get("win_rate_10", 0.4),
        }

    def _extract_key_reasons(
        self, team_features: Dict[str, Dict], champion: str,
    ) -> List[str]:
        """从特征中提取关键原因（通俗表述）"""
        feat = team_features.get(champion, {})
        reasons = []

        if feat.get("elo_rating", 0) > 2000:
            reasons.append("综合实力评分位居前列")
        if feat.get("recent_form_score", 0) > 0.6:
            reasons.append("近期状态出色")
        if feat.get("attack_score", 0) > 0.6:
            reasons.append("攻击力强劲")
        if feat.get("defense_score", 0) > 0.6:
            reasons.append("防守稳固")
        if feat.get("path_advantage_score", 0) > 0.55:
            reasons.append("晋级路径有利")
        if feat.get("knockout_performance_score", 0) > 0.6:
            reasons.append("淘汰赛表现优异")
        if feat.get("world_cup_experience", 0) > 5:
            reasons.append("大赛经验丰富")
        if feat.get("win_rate_10", 0) > 0.7:
            reasons.append("近10场胜率高")

        if not reasons:
            reasons.append("综合实力均衡")

        return reasons[:5]

    def _extract_remaining_path(
        self, knockout_predictions: List[Dict], champion: str,
    ) -> List[str]:
        """提取冠军的剩余晋级路径中的潜在对手"""
        opponents = []
        for m in knockout_predictions:
            if m.get("winner") == champion or champion in (m.get("home_team"), m.get("away_team")):
                other = m.get("away_team") if m.get("home_team") == champion else m.get("home_team")
                if other and other != champion:
                    opponents.append(other)
        return opponents[:5]

    def _call_llm(
        self,
        champion: str,
        probability: float,
        feature_breakdown: Dict,
        key_reasons: List[str],
        remaining_path: List[str],
        simulation_data: Dict,
        surviving_teams: Optional[List[str]] = None,
        stage: Optional[str] = None,
    ) -> Optional[str]:
        """调用 LLM 生成结构化通俗解释"""
        try:
            from app.core.config import get_settings
            settings = get_settings()
            api_key = settings.OPENAI_API_KEY
            model = settings.OPENAI_MODEL or "glm-4-flash"
        except Exception:
            api_key = None
            model = "glm-4-flash"

        if not api_key or api_key == "sk-placeholder-key":
            logger.info("No valid API key, using fallback explanation")
            return None

        # 从模拟数据提取夺冠概率（新格式：champion dict 只含 surviving_teams）
        top5_text = ""
        champ_probs = simulation_data.get("champion", {})
        if not champ_probs:
            # 兼容旧格式
            champ_probs_old = simulation_data.get("champion_probabilities", {})
            if champ_probs_old and "top5" in champ_probs_old:
                top5_text = "、".join(
                    f"{t['team']}({t['probability']*100:.1f}%)"
                    for t in champ_probs_old["top5"][:5]
                )
        if champ_probs and not top5_text:
            top5_text = "、".join(
                f"{team}({p*100:.1f}%)"
                for team, p in list(champ_probs.items())[:5]
            )

        # 阶段和存活球队
        stage_text = ""
        if stage and stage != "unknown":
            stage_labels = {
                "semi_finals": "四强半决赛",
                "final": "决赛",
                "quarter_finals": "八强赛",
                "round_of_16": "16强赛",
                "round_of_32": "32强赛",
                "tournament_ended": "赛事已结束",
            }
            stage_text = stage_labels.get(stage, stage)

        surviving_text = ""
        if surviving_teams:
            surviving_text = "、".join(surviving_teams)

        prompt = f"""你是一个专业的足球分析师，需要向普通球迷解释为什么 {champion} 被预测为 2026 世界杯冠军。

预测信息：
- 冠军：{champion}
- 夺冠概率：{probability:.1f}%
- 当前阶段：{stage_text or '未知'}
- 仍有夺冠可能的球队：{surviving_text or '未知'}
- 综合实力评分：{feature_breakdown.get('elo_rating', 'N/A')}
- 近期状态：{feature_breakdown.get('recent_form_score', 'N/A')}
- 攻击力：{feature_breakdown.get('attack_score', 'N/A')}
- 防守力：{feature_breakdown.get('defense_score', 'N/A')}
- 路径优势：{feature_breakdown.get('path_advantage_score', 'N/A')}
- 淘汰赛表现：{feature_breakdown.get('knockout_performance_score', 'N/A')}
- 大赛经验：{feature_breakdown.get('world_cup_experience', 'N/A')}
- 近10场胜率：{feature_breakdown.get('win_rate_10', 'N/A')}
- 关键原因：{'、'.join(key_reasons[:5]) if key_reasons else '综合表现'}
- 潜在对手：{'、'.join(remaining_path[:3]) if remaining_path else '未知'}
- 夺冠概率前五：{top5_text or '数据暂缺'}

请严格按以下格式输出（使用 Markdown 标题）：

## 为什么预测{champion}夺冠？

一段 80-120 字的概述，说明为什么这支球队最有可能夺冠。

### 核心优势

列出 3-4 个核心优势，每个用一句话描述。

### 关键因素

列出 2-3 个影响夺冠的关键因素。

### AI综合判断

一段 50-80 字的总结性判断。

要求：
1. 面向普通球迷，专业但通俗易懂
2. 严禁出现以下技术词汇：workflow, llm_planner, tool_trace, source_level, fixtures, bracket_payload, API, ensemble, xgboost, neural network, 神经网络, 集成模型, 蒙特卡洛, 泊松分布, elo, feature, 特征向量, 模型融合, 权重, softmax, focal loss
3. 可以使用的概念：综合实力、近期状态、攻防能力、晋级路径、大赛经验、历史战绩、夺冠概率
4. 直接输出以上内容，不要加额外前缀或解释"""

        try:
            from zhipuai import ZhipuAI
            client = ZhipuAI(api_key=api_key)
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=600,
            )
            content = response.choices[0].message.content.strip()
            if content and len(content) > 50 and "##" in content:
                return content
        except ImportError:
            logger.info("zhipuai not installed, using fallback")
        except Exception as e:
            logger.warning("LLM call failed: %s", e)

        return None

    def _fallback_explanation(
        self,
        champion: str,
        probability: float,
        feature_breakdown: Dict,
        key_reasons: List[str],
        top_contenders: List[Dict],
        surviving_teams: Optional[List[str]] = None,
        stage: Optional[str] = None,
    ) -> str:
        """基于规则的结构化通俗解释"""
        parts = []

        # 阶段描述
        stage_desc = ""
        if stage == "semi_finals" and surviving_teams:
            teams_text = "、".join(surviving_teams)
            stage_desc = f"当前赛事已进入四强阶段，系统只在{teams_text}四支仍有夺冠可能的球队中进行模拟分析。"
        elif stage == "final" and surviving_teams:
            teams_text = "、".join(surviving_teams)
            stage_desc = f"当前赛事已进入决赛阶段，{teams_text}两支球队争夺大力神杯。"
        elif stage == "tournament_ended":
            stage_desc = "本届世界杯已圆满落幕。"

        # ## 标题概述
        if stage_desc:
            parts.append(
                f"## 为什么预测 {champion} 夺冠？\n\n"
                f"{stage_desc}\n\n"
                f"根据已结束比赛结果和后续对阵形势，{champion} 展现出较强的夺冠实力，"
                f"系统给出 {probability:.1f}% 的夺冠概率。"
                f"球队在攻防两端表现均衡，是当前最有可能捧起大力神杯的队伍。\n"
            )
        else:
            parts.append(
                f"## 为什么预测 {champion} 夺冠？\n\n"
                f"根据已结束比赛结果和后续对阵形势，{champion} 展现出较强的夺冠实力，"
                f"系统给出 {probability:.1f}% 的夺冠概率。"
                f"球队在攻防两端表现均衡，是当前最有可能捧起大力神杯的队伍。\n"
            )

        # ### 核心优势
        parts.append("\n### 核心优势\n")
        advantages = []
        form = feature_breakdown.get("recent_form_score", 0.5)
        atk = feature_breakdown.get("attack_score", 0.5)
        dfs = feature_breakdown.get("defense_score", 0.5)
        path_adv = feature_breakdown.get("path_advantage_score", 0.5)
        exp = feature_breakdown.get("world_cup_experience", 0)

        if atk > 0.6:
            advantages.append("进攻端表现强劲，场均进球数领先，锋线火力十足。")
        else:
            advantages.append("进攻组织有序，能够创造足够的得分机会。")
        if dfs > 0.6:
            advantages.append("防守端同样稳固，失球数控制得当，后防线值得信赖。")
        else:
            advantages.append("防守体系完整，能够有效地限制对手进攻。")
        if form > 0.6:
            advantages.append("近期状态出色，连续多场保持高水平竞技状态。")
        if exp > 5:
            advantages.append("大赛经验丰富，核心球员多次参加世界顶级赛事。")
        if not advantages:
            advantages.append("综合实力均衡，各位置无明显短板。")
        for a in advantages[:4]:
            parts.append(f"- {a}\n")

        # ### 关键因素
        parts.append("\n### 关键因素\n")
        factors = []
        if path_adv > 0.55:
            factors.append("后续晋级路径相对有利，潜在对手实力相对较弱。")
        if key_reasons:
            factors.append(f"主要优势包括：{'、'.join(key_reasons[:3])}。")
        # 竞争对手：优先用 surviving_teams，兜底用 top_contenders
        if surviving_teams and len(surviving_teams) >= 2:
            rivals = "、".join(t for t in surviving_teams if t != champion)
            if rivals:
                factors.append(f"主要竞争对手包括{rivals}，但{champion}在综合实力上占据优势。")
        elif top_contenders and len(top_contenders) >= 2:
            rivals = "、".join(t.get("team", "") for t in top_contenders[1:4] if t.get("team"))
            if rivals:
                factors.append(f"主要竞争对手包括{rivals}，但{champion}在综合实力上占据优势。")
        if not factors:
            factors.append(f"{champion}在综合评估中表现突出，是当前最具竞争力的球队。")
        for f in factors[:3]:
            parts.append(f"- {f}\n")

        # ### AI综合判断
        parts.append(
            f"\n### AI综合判断\n\n"
            f"综合各方面分析，{champion} 以 {probability:.1f}% 的夺冠概率领跑群雄。"
            f"球队整体实力突出，晋级形势有利，是最有可能夺冠的球队。\n"
        )

        return "".join(parts)

    def _build_champion_card(
        self,
        champion: str,
        probability: float,
        feature_breakdown: Dict,
        key_reasons: List[str],
    ) -> Dict[str, Any]:
        """构建冠军展示卡片"""
        return {
            "team": champion,
            "probability": probability,
            "strength_label": self._strength_label(feature_breakdown),
            "highlights": key_reasons[:3],
            "radar": {
                "攻击力": round(feature_breakdown.get("attack_score", 0.5) * 100),
                "防守力": round(feature_breakdown.get("defense_score", 0.5) * 100),
                "近期状态": round(feature_breakdown.get("recent_form_score", 0.5) * 100),
                "大赛经验": min(100, round(feature_breakdown.get("world_cup_experience", 0) * 10)),
                "路径优势": round(feature_breakdown.get("path_advantage_score", 0.5) * 100),
            },
        }

    def _strength_label(self, feature_breakdown: Dict) -> str:
        """根据综合实力指数给出标签（team_strength_index，非概率）"""
        overall = feature_breakdown.get("team_strength_index",
                                        feature_breakdown.get("overall_strength_score", 0.5))
        if overall > 0.75:
            return "夺冠热门"
        elif overall > 0.6:
            return "强力竞争者"
        elif overall > 0.45:
            return "有力争夺者"
        else:
            return "潜在黑马"

    def _sanitize(self, text: str) -> str:
        """清理输出，替换可能出现的禁止术语"""
        result = text
        replacements = {
            "ELO评分": "综合实力评分",
            "ELO": "综合实力",
            "集成预测": "综合评估",
            "神经网络模型": "分析模型",
            "XGBoost": "分析模型",
            "蒙特卡洛模拟": "大量模拟推演",
            "泊松分布": "统计模型",
            "特征向量": "能力指标",
            "模型融合": "综合分析",
            "softmax": "概率计算",
            "focal loss": "训练优化",
            "API": "数据接口",
            "fixtures": "赛程数据",
        }
        for term, replacement in replacements.items():
            result = result.replace(term, replacement)
        return result
