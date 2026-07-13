"""
工具适配器层

把现有复杂工具包装成 LLM 容易调用的简单工具函数。
所有 adapter 返回统一格式：
{
    "success": True/False,
    "data": {...},
    "error_type": None 或 "rate_limited" / "missing_dependency" / ...,
    "message": "...",
    "state_updates": {...}   # AgentExecutor 据此更新 AgentState
}

禁止工具返回零散格式。
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ── 统一返回格式辅助 ──

def _ok(data: Any, message: str = "", state_updates: Optional[Dict] = None) -> Dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error_type": None,
        "message": message,
        "state_updates": state_updates or {},
    }


def _fail(error_type: str, message: str, state_updates: Optional[Dict] = None) -> Dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "error_type": error_type,
        "message": message,
        "state_updates": state_updates or {},
    }


# ═══════════════════════════════════════════════════════════════
# 1. get_cached_fixtures
# ═══════════════════════════════════════════════════════════════

def tool_get_cached_fixtures(state, season: int = 2026) -> Dict[str, Any]:
    """从 fixtures 表读取缓存数据。只从数据库读取，不调用外部 API。"""
    from app.services.data_source_manager import DataSourceManager

    # 如果 state 已有 fixtures 且非空，直接返回
    fixtures = state.collected_data.get("fixtures")
    if fixtures and isinstance(fixtures, list) and len(fixtures) > 0:
        return _ok(
            data={"fixtures": fixtures, "source": "cache", "count": len(fixtures)},
            message=f"缓存中已有 {len(fixtures)} 场赛程",
            state_updates={"has_fixtures": True},
        )

    # 从 fixtures 表读取
    mgr = DataSourceManager()
    result = mgr.get_cached_fixtures(season)
    
    # get_cached_fixtures 返回的是列表（不是 dict）
    if isinstance(result, list):
        fixtures = result
    else:
        fixtures = []
    
    if fixtures and len(fixtures) > 0:
        return _ok(
            data={"fixtures": fixtures, "source": "football_data", "count": len(fixtures)},
            message=f"从 fixtures 表读取 {len(fixtures)} 场赛程",
            state_updates={
                "has_fixtures": True,
                "data_source_level": "external_real",
            },
        )
    else:
        return _fail(
            error_type="empty_data",
            message="fixtures 表为空，当前没有可用真实赛程数据",
            state_updates={
                "has_fixtures": False,
                "data_source_level": "unavailable",
            },
        )


# ═══════════════════════════════════════════════════════════════
# 2. refresh_real_fixtures
# ═══════════════════════════════════════════════════════════════

def tool_refresh_real_fixtures(state, season: int = 2026) -> Dict[str, Any]:
    """从外部 API 刷新真实赛程和比分。调用 DataSourceManager.refresh_fixtures()。"""
    from app.services.data_source_manager import DataSourceManager

    mgr = DataSourceManager()
    result = mgr.refresh_fixtures(season)
    
    if result["success"]:
        # 获取最新的 fixtures 数据
        cached = mgr.get_cached_fixtures(season)
        # get_cached_fixtures 返回的是列表
        fixtures = cached if isinstance(cached, list) else []
        
        return _ok(
            data={
                "fixtures": fixtures,
                "source": result["source"],
                "source_level": result["source_level"],
                "count": len(fixtures),
                "inserted": result.get("inserted", 0),
                "updated": result.get("updated", 0),
            },
            message=f"刷新成功，获取 {len(fixtures)} 场赛程",
            state_updates={
                "has_fixtures": len(fixtures) > 0,
                "data_source_level": result["source_level"],
            },
        )
    else:
        return _fail(
            error_type="unavailable",
            message="所有数据源均失败，fixtures 表为空",
            state_updates={
                "has_fixtures": False,
                "data_source_level": "unavailable",
            },
        )


# ═══════════════════════════════════════════════════════════════
# 3. get_worldcup_teams
# ═══════════════════════════════════════════════════════════════

def tool_get_worldcup_teams(state, season: int = 2026) -> Dict[str, Any]:
    """获取世界杯球队列表，优先缓存。"""
    teams = state.collected_data.get("teams")
    if teams and isinstance(teams, list) and len(teams) > 0:
        return _ok(
            data={"teams": teams, "source": "cache", "count": len(teams)},
            message=f"缓存中已有 {len(teams)} 支球队",
            state_updates={"has_teams": True},
        )

    from app.tools.api_sports_tool import APISportsTool
    api = APISportsTool()
    if not api.api_key_detected:
        return _fail(error_type="api_key_missing", message="API Key 未配置")

    try:
        result = api.get_worldcup_teams(season)
        if result["success"]:
            teams = result.get("data", [])
            if not teams:
                return _fail(
                    error_type="empty_data",
                    message="API 返回 0 支球队，数据可能尚未更新",
                    state_updates={},
                )
            return _ok(
                data={"teams": teams, "source": "api-sports", "count": len(teams)},
                message=f"获取 {len(teams)} 支球队",
                state_updates={"has_teams": True},
            )
        else:
            error_msg = result.get("error", "")
            if "额度" in error_msg or "rate" in error_msg.lower():
                return _fail(error_type="rate_limited", message="API 限流",
                             state_updates={"api_rate_limited": True})
            return _fail(error_type="api_error", message=error_msg)
    except Exception as e:
        return _fail(error_type="exception", message=str(e))


# ═══════════════════════════════════════════════════════════════
# 4. load_historical_matches
# ═══════════════════════════════════════════════════════════════

def tool_load_historical_matches(state, start_year: int = 2018) -> Dict[str, Any]:
    """加载历史比赛数据。"""
    if state.collected_data.get("historical") or state.collected_data.get("historical_matches"):
        hist = state.collected_data.get("historical") or state.collected_data.get("historical_matches")
        count = hist.get("total", 0) if isinstance(hist, dict) else len(hist) if hist else 0
        return _ok(
            data={"historical_matches": hist, "source": "cache", "count": count},
            message=f"缓存中已有 {count} 场历史比赛",
            state_updates={"has_historical_matches": True},
        )

    from app.tools.historical_data_tool import HistoricalDataTool
    tool = HistoricalDataTool()
    result = tool.load_matches(start_year=start_year)
    if result["success"]:
        data = result.get("data", {})
        count = data.get("total", 0) if isinstance(data, dict) else 0
        return _ok(
            data={"historical_matches": data, "source": "historical_csv", "count": count},
            message=f"加载 {count} 场历史比赛",
            state_updates={"has_historical_matches": True},
        )
    else:
        return _fail(error_type="load_error", message=result.get("error", "历史数据加载失败"))


# ═══════════════════════════════════════════════════════════════
# 5. check_data_quality
# ═══════════════════════════════════════════════════════════════

def tool_check_data_quality(state) -> Dict[str, Any]:
    """检查当前数据是否足够预测。"""
    from app.agents.data_quality_agent import DataQualityAgent
    quality = DataQualityAgent()
    report = quality.check(state.collected_data)

    score = report.get("score", 0.0)
    can_predict = report.get("is_usable", False)
    missing = report.get("missing_data", [])

    return _ok(
        data={
            "data_quality_score": score,
            "can_predict": can_predict,
            "missing_fields": missing,
            "fallback_used": report.get("fallback_used", False),
            "warnings": report.get("warnings", []),
        },
        message=f"数据质量分数 {score:.2f}，可预测: {can_predict}",
        state_updates={
            "data_quality_report": report,
            "data_quality_score": score,
            "can_predict": can_predict,
            "missing_fields": missing,
        },
    )


# ═══════════════════════════════════════════════════════════════
# 6. build_team_features
# ═══════════════════════════════════════════════════════════════

def tool_build_team_features(state) -> Dict[str, Any]:
    """构建球队特征。"""
    from app.tools.feature_builder_tool import FeatureBuilderTool
    from app.agents.worldcup_agent import DEFAULT_48_TEAMS

    # 获取球队列表
    api_teams = state.collected_data.get("teams", [])
    if api_teams and len(api_teams) >= 8:
        teams = []
        for t in api_teams:
            team_info = t.get("team", {})
            teams.append({
                "name": team_info.get("name", "Unknown"),
                "id": team_info.get("id"),
                "elo_rating": 1500.0,
            })
    else:
        teams = []
        for group in DEFAULT_48_TEAMS:
            for name, elo in group:
                teams.append({"name": name, "id": None, "elo_rating": float(elo)})

    builder = FeatureBuilderTool()
    result = builder.build_features(teams)
    if result["success"]:
        features = result.get("data", {})
        return _ok(
            data={"team_features": features, "count": len(features)},
            message=f"为 {len(features)} 支球队构建特征",
            state_updates={
                "team_features": features,
                "has_team_features": True,
            },
        )
    else:
        return _fail(error_type="build_error", message=result.get("error", "特征构建失败"))


# ═══════════════════════════════════════════════════════════════
# 7. predict_group_stage
# ═══════════════════════════════════════════════════════════════

def tool_predict_group_stage(state) -> Dict[str, Any]:
    """预测或读取小组赛结果。"""
    from app.tools.bracket_tool import BracketTool
    from app.tools.match_predictor_tool import MatchPredictorTool
    from app.agents.worldcup_agent import DEFAULT_48_TEAMS

    if not state.team_features:
        return _fail(
            error_type="missing_dependency",
            message="需要先调用 build_team_features",
        )

    # 构建小组
    groups = _build_groups(state, DEFAULT_48_TEAMS)
    predictor = MatchPredictorTool(seed=42)
    bracket_tool = BracketTool(seed=42)

    result = bracket_tool.predict_group_stage(groups, state.team_features, predictor)
    group_predictions = result.get("group_predictions", [])
    tournament_result = result.get("tournament_result")

    # 计算 standings 和 qualified
    standings = bracket_tool.calculate_group_standings(group_predictions)
    qualified = []
    for gp in group_predictions:
        qualified.extend(gp.get("qualified_teams", []))

    return _ok(
        data={
            "group_predictions": group_predictions,
            "qualified_count": len(qualified),
        },
        message=f"小组赛预测完成，{len(qualified)} 支球队晋级",
        state_updates={
            "group_predictions": group_predictions,
            "group_standings": standings,
            "qualified_teams": qualified,
            "has_group_predictions": True,
            "_tournament_result": tournament_result,
        },
    )


# ═══════════════════════════════════════════════════════════════
# 8. predict_knockout_bracket
# ═══════════════════════════════════════════════════════════════

def tool_predict_knockout_bracket(state) -> Dict[str, Any]:
    """推演淘汰赛路径。"""
    from app.tools.bracket_tool import BracketTool
    from app.tools.match_predictor_tool import MatchPredictorTool
    from app.services import real_tournament_data as rtd

    if not state.group_predictions:
        return _fail(
            error_type="missing_dependency",
            message="需要先调用 predict_group_stage",
        )

    predictor = MatchPredictorTool(seed=42)
    bracket_tool = BracketTool(seed=42)

    if rtd.is_real_data_available():
        bracket = {"group_results": [], "third_places_ranking": []}
    else:
        tournament_result = state.collected_data.get("_tournament_result")
        if not tournament_result:
            return _fail(
                error_type="missing_dependency",
                message="缺少小组赛结果，无法推演淘汰赛",
            )
        bracket = bracket_tool.build_knockout_bracket(tournament_result)

    result = bracket_tool.predict_knockout_stage(bracket, state.team_features, predictor)
    knockout_preds = result.get("knockout_predictions", [])
    champion = result.get("champion")
    runner_up = result.get("runner_up")
    bracket_payload = result.get("bracket_payload", {})

    # 兜底：如果 bracket 没返回冠军，从决赛数据提取
    if not champion and knockout_preds:
        final_matches = [m for m in knockout_preds if m.get("round") == "final"]
        if final_matches:
            champion = final_matches[0].get("winner")

    # 提取决赛信息
    final_matches = [m for m in knockout_preds if m.get("round") == "final"]
    final_match = final_matches[0] if final_matches else None

    return _ok(
        data={
            "knockout_predictions": knockout_preds,
            "champion": champion,
            "runner_up": runner_up,
            "match_count": len(knockout_preds),
        },
        message=f"淘汰赛推演完成，共 {len(knockout_preds)} 场，冠军: {champion}",
        state_updates={
            "knockout_predictions": knockout_preds,
            "predicted_champion": champion,
            "predicted_runner_up": runner_up,
            "final_match": final_match,
            "bracket_payload": bracket_payload,
            "has_knockout_predictions": True,
            "has_champion_prediction": bool(champion),
            "_champion": champion,
            "_runner_up": runner_up,
        },
    )


# ═══════════════════════════════════════════════════════════════
# 9. predict_champion
# ═══════════════════════════════════════════════════════════════

def tool_predict_champion(state) -> Dict[str, Any]:
    """计算冠军、亚军、夺冠概率。如果已有冠军预测，直接返回。"""
    if state.predicted_champion:
        # 从 knockout_predictions 计算简单概率
        champ_matches = [
            m for m in state.knockout_predictions
            if m.get("winner") == state.predicted_champion
        ]
        avg_conf = (
            sum(m.get("confidence", 0.5) for m in champ_matches) / len(champ_matches)
            if champ_matches else 0.5
        )
        return _ok(
            data={
                "champion": state.predicted_champion,
                "runner_up": state.predicted_runner_up,
                "champion_probability": round(avg_conf, 4),
            },
            message=f"冠军已确定: {state.predicted_champion}",
            state_updates={"has_champion_prediction": True},
        )

    if not state.knockout_predictions:
        return _fail(
            error_type="missing_dependency",
            message="需要先调用 predict_knockout_bracket",
        )

    # 从 knockout 结果提取
    final_matches = [m for m in state.knockout_predictions if m.get("round") == "final"]
    if not final_matches:
        return _fail(error_type="no_final", message="淘汰赛结果中没有决赛数据")

    final = final_matches[0]
    champion = final.get("winner")
    loser = final.get("away_team") if champion == final.get("home_team") else final.get("home_team")
    prob = final.get("confidence", 0.5)

    return _ok(
        data={
            "champion": champion,
            "runner_up": loser,
            "champion_probability": round(prob, 4),
        },
        message=f"冠军: {champion}，概率: {prob:.2%}",
        state_updates={
            "predicted_champion": champion,
            "predicted_runner_up": loser,
            "has_champion_prediction": True,
            "_champion": champion,
            "_runner_up": loser,
        },
    )


# ═══════════════════════════════════════════════════════════════
# 10. build_visualization_payload
# ═══════════════════════════════════════════════════════════════

def tool_build_visualization_payload(state) -> Dict[str, Any]:
    """构建页面展示数据。"""
    if not state.team_features:
        return _fail(
            error_type="missing_dependency",
            message="需要先构建球队特征",
        )

    # 实力排行
    sorted_teams = sorted(
        state.team_features.values(),
        key=lambda x: x.get("power_score", 0),
        reverse=True,
    )[:10]

    # 确保 champion 有效
    champ = state.predicted_champion
    if not champ or champ == "Unknown":
        if sorted_teams:
            champ = sorted_teams[0].get("team_name", "Unknown")
            state.predicted_champion = champ

    champ_prob = getattr(state, "champion_probability", None)
    if champ_prob is None and sorted_teams:
        feat = state.team_features.get(champ, {})
        ps = feat.get("power_score", 0)
        if ps:
            champ_prob = round(ps * 100, 1)
            state.champion_probability = champ_prob

    # 判断决赛状态
    final_source = "prediction"
    final_status = "predicted"
    if state.final_match:
        fm_source = state.final_match.get("source", "")
        if fm_source in ("real_result", "real_data"):
            final_source = "real_result"
            final_status = "confirmed"

    runner_up = state.predicted_runner_up
    if runner_up == "Unknown":
        runner_up = None

    payload = {
        "power_ranking": [
            {
                "rank": i + 1,
                "team": t["team_name"],
                "power_score": t["power_score"],
                "elo": t["elo_rating"],
            }
            for i, t in enumerate(sorted_teams)
        ],
        "group_summary": [
            {
                "group": gp["group_name"],
                "qualified": [s["team_name"] for s in gp["standings"][:2]],
            }
            for gp in state.group_predictions
        ],
        "knockout_bracket": [
            {
                "round": m["round"],
                "matchup": f"{m['home_team']} vs {m['away_team']}",
                "score": m["predicted_score"],
                "winner": m["winner"],
            }
            for m in state.knockout_predictions
        ],
        "champion": {
            "team": champ,
            "probability": champ_prob,
            "source": final_source,
            "status": final_status,
        },
        "final_prediction": {
            "champion": champ,
            "runner_up": runner_up,
            "win_prob": champ_prob,
        },
        "final_match": state.final_match,
        "qualified_teams": state.qualified_teams,
    }

    return _ok(
        data=payload,
        message="可视化数据构建完成",
        state_updates={
            "visualization_payload": payload,
            "has_visualization_payload": True,
        },
    )


# ═══════════════════════════════════════════════════════════════
# 11. generate_final_explanation
# ═══════════════════════════════════════════════════════════════

def tool_generate_final_explanation(state) -> Dict[str, Any]:
    """生成最终中文解释。"""
    if not state.predicted_champion:
        return _fail(
            error_type="missing_dependency",
            message="需要先完成冠军预测",
        )

    from app.tools.explanation_tool import ExplanationTool
    explainer = ExplanationTool()

    champion = state.predicted_champion or "Unknown"
    runner_up = state.predicted_runner_up or "Unknown"

    explanation = explainer.explain_champion_path(
        champion=champion,
        runner_up=runner_up,
        knockout_predictions=state.knockout_predictions,
        team_features=state.team_features,
        reasoning_steps=state.reasoning_steps,
    )

    return _ok(
        data={"explanation": explanation},
        message="冠军解释已生成",
        state_updates={
            "final_explanation": explanation,
            "has_final_explanation": True,
        },
    )


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _build_groups(state, DEFAULT_48_TEAMS):
    """从 state 构建 12 个小组"""
    api_teams = state.collected_data.get("teams", [])
    if api_teams and len(api_teams) >= 48:
        groups = []
        for i in range(0, 48, 4):
            group = []
            for t in api_teams[i:i + 4]:
                team_info = t.get("team", {})
                name = team_info.get("name", f"Team_{i}")
                elo = state.team_features.get(name, {}).get("elo_rating", 1500.0)
                group.append((i + len(group) + 1, name, elo))
            groups.append(group)
        if len(groups) == 12:
            return groups

    groups = []
    tid = 1
    for group in DEFAULT_48_TEAMS:
        g = []
        for name, elo in group:
            feat_elo = state.team_features.get(name, {}).get("elo_rating", elo)
            g.append((tid, name, float(feat_elo)))
            tid += 1
        groups.append(g)
    return groups


# ═══════════════════════════════════════════════════════════════
# 工具注册表（供 ToolRegistry 使用）
# ═══════════════════════════════════════════════════════════════

ADAPTER_TOOLS = {
    "get_cached_fixtures": tool_get_cached_fixtures,
    "refresh_real_fixtures": tool_refresh_real_fixtures,
    "get_worldcup_teams": tool_get_worldcup_teams,
    "load_historical_matches": tool_load_historical_matches,
    "check_data_quality": tool_check_data_quality,
    "build_team_features": tool_build_team_features,
    "predict_group_stage": tool_predict_group_stage,
    "predict_knockout_bracket": tool_predict_knockout_bracket,
    "predict_champion": tool_predict_champion,
    "build_visualization_payload": tool_build_visualization_payload,
    "generate_final_explanation": tool_generate_final_explanation,
}
