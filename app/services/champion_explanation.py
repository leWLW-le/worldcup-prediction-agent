"""
champion_explanation - 冠军预测 LLM 解释模块

基于 feature_breakdown 生成面向普通用户的通俗解释。
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_FALLBACK_TEMPLATE = (
    "根据已结束比赛结果和后续对阵形势，{champion} 在当前路径中展现出较强稳定性。"
    "球队攻防表现均衡，关键比赛胜率较高，且在后续潜在对手对比中占据一定优势。"
    "因此系统将 {champion} 评为当前最可能夺冠的球队。"
)


def generate_champion_explanation(
    champion: str,
    probability: float,
    feature_breakdown: Dict[str, Any],
    key_reasons: List[str],
    remaining_path: List[str],
    use_llm: bool = True,
) -> Dict[str, Any]:
    """
    生成冠军预测解释。

    Args:
        champion: 冠军球队名称
        probability: 夺冠概率 (0-100)
        feature_breakdown: 特征分解
        key_reasons: 关键原因列表
        remaining_path: 剩余路径
        use_llm: 是否尝试使用 LLM

    Returns:
        {title, content, source}
    """
    title = f"为什么预测 {champion} 夺冠？"

    # 尝试 LLM
    if use_llm:
        try:
            content = _call_llm(champion, probability, feature_breakdown, key_reasons, remaining_path)
            if content:
                return {"title": title, "content": content, "source": "llm"}
        except Exception as e:
            logger.warning("LLM champion explanation failed: %s", e)

    # Fallback
    content = _fallback_explanation(champion, probability, feature_breakdown, key_reasons)
    return {"title": title, "content": content, "source": "fallback"}


def _call_llm(
    champion: str,
    probability: float,
    feature_breakdown: Dict[str, Any],
    key_reasons: List[str],
    remaining_path: List[str],
) -> Optional[str]:
    """调用 LLM 生成解释"""
    try:
        from app.core.config import get_settings
        settings = get_settings()
        api_key = settings.OPENAI_API_KEY
        model = settings.OPENAI_MODEL or "glm-4-flash"
    except Exception:
        api_key = None
        model = "glm-4-flash"

    if not api_key or api_key == "sk-placeholder-key":
        logger.info("No valid API key for LLM explanation, using fallback")
        return None

    prompt = f"""你是一个专业的足球分析师，需要向普通球迷解释为什么 {champion} 被预测为 2026 世界杯冠军。

预测信息：
- 冠军：{champion}
- 夺冠概率：{probability:.1f}%
- 综合实力指数：{feature_breakdown.get('team_strength_index', feature_breakdown.get('overall_strength_score', 'N/A'))}
- 关键指标：
  - 综合实力评分：{feature_breakdown.get('elo_rating', 'N/A')}
  - 近期状态（近5场）：{feature_breakdown.get('recent_form_score', 'N/A')}
  - 攻击力：{feature_breakdown.get('attack_score', 'N/A')}
  - 防守力：{feature_breakdown.get('defense_score', 'N/A')}
  - 路径优势：{feature_breakdown.get('path_advantage_score', 'N/A')}
  - 淘汰赛表现：{feature_breakdown.get('knockout_performance_score', 'N/A')}
  - 大赛经验：{feature_breakdown.get('world_cup_experience', 'N/A')}
  - 近10场胜率：{feature_breakdown.get('win_rate_10', 'N/A')}
- 关键原因：{', '.join(key_reasons[:5]) if key_reasons else '综合表现'}
- 剩余路径：{', '.join(remaining_path[:3]) if remaining_path else '未知'}
- 模拟次数：10000 次蒙特卡洛模拟

要求：
1. 120-200 字，中文
2. 面向普通球迷，专业但通俗易懂
3. 严禁出现以下技术词汇：workflow, llm_planner, tool_trace, source_level, fixtures, bracket_payload, API, ensemble, xgboost, neural network, 神经网络, 集成模型, 蒙特卡洛, 泊松分布, elo, feature, 特征向量, 模型融合, 权重, softmax, focal loss
4. 可以使用的概念：综合实力、近期状态、攻防能力、晋级路径、大赛经验、历史战绩、夺冠概率
5. 解释参考：已结束比赛结果、当前晋级路径、球队整体实力、近期表现、可能对手、历史大赛成绩
6. 直接输出解释文字，不要加标题或前缀"""

    try:
        from zhipuai import ZhipuAI
        client = ZhipuAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=400,
        )
        content = response.choices[0].message.content.strip()
        if content and len(content) > 30:
            return content
    except ImportError:
        logger.info("zhipuai not installed, using fallback explanation")
    except Exception as e:
        logger.warning("LLM call failed: %s", e)

    return None


def _fallback_explanation(
    champion: str,
    probability: float,
    feature_breakdown: Dict[str, Any],
    key_reasons: List[str],
) -> str:
    """生成基于规则的解释"""
    parts = []

    # 开头
    parts.append(
        f"根据已结束比赛结果和后续对阵形势，{champion} 在当前路径中展现出较强稳定性。"
    )

    # 基于特征的分析
    form = feature_breakdown.get("recent_form_score", 0.5)
    atk = feature_breakdown.get("attack_score", 0.5)
    dfs = feature_breakdown.get("defense_score", 0.5)
    path_adv = feature_breakdown.get("path_advantage_score", 0.5)

    if form > 0.6:
        parts.append(f"球队近期状态出色，胜率高且进球稳定。")
    elif form > 0.4:
        parts.append(f"球队近期表现稳定，保持了良好的竞技状态。")

    if atk > 0.6:
        parts.append(f"进攻端表现强劲，场均进球数领先。")
    if dfs > 0.6:
        parts.append(f"防守端同样稳固，失球数控制得当。")
    if path_adv > 0.55:
        parts.append(f"后续晋级路径相对有利，潜在对手实力相对较弱。")

    # 关键原因
    if key_reasons:
        parts.append(f"主要原因包括：{'、'.join(key_reasons[:3])}。")

    # 概率
    parts.append(f"综合评估，系统给予 {champion} {probability:.1f}% 的夺冠概率。")

    return "".join(parts)


def build_feature_breakdown(
    team_features: Dict[str, Dict[str, Any]],
    champion: str,
) -> Dict[str, Any]:
    """从 team_features 构建 feature_breakdown 结构（兼容新旧特征）"""
    feat = team_features.get(champion, {})
    return {
        "elo_rating": feat.get("elo_rating", 1500),
        "recent_form_score": feat.get("recent_form_score", 0.5),
        "attack_score": feat.get("attack_score", 0.5),
        "defense_score": feat.get("defense_score", 0.5),
        "path_advantage_score": feat.get("path_advantage_score", 0.5),
        "knockout_performance_score": feat.get("knockout_performance_score", 0.5),
        "team_strength_index": feat.get("team_strength_index", feat.get("overall_strength_score", 0.5)),
        "world_cup_experience": feat.get("world_cup_experience", 0),
        "win_rate_10": feat.get("win_rate_10", 0.4),
        "big_win_rate": feat.get("big_win_rate", 0.2),
        "scoring_consistency": feat.get("scoring_consistency", 0.5),
        "clean_sheet_rate": feat.get("clean_sheet_rate", 0.3),
    }


def extract_key_reasons(
    team_features: Dict[str, Dict[str, Any]],
    champion: str,
) -> List[str]:
    """从特征中提取关键原因（兼容新旧特征）"""
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
    if feat.get("big_win_rate", 0) > 0.3:
        reasons.append("大比分获胜能力强")
    if feat.get("scoring_consistency", 0) > 0.8:
        reasons.append("得分稳定性高")
    if feat.get("clean_sheet_rate", 0) > 0.5:
        reasons.append("零封对手率高")
    if feat.get("squad_strength", 0) > 0.8:
        reasons.append("阵容深度充足")

    if not reasons:
        reasons.append("综合实力均衡")

    return reasons[:5]
