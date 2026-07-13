"""
模拟预测 API 路由

提供完整的蒙特卡洛模拟接口，集成概率引擎、注意力网络和 LLM 解释器。
所有返回值均通过 Pydantic 校验，确保前端接收规范的 JSON 结构。
"""

import random
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from app.services.probability_engine import ProbabilityEngine
from app.services.tournament_sim import simulate_group_stage, simulate_knockout_stage
from app.services.feature_network import (
    FeatureAttentionMixer,
    normalize_features,
    integrate_with_probability_engine
)
from app.services.llm_explainer import MatchExplainerAgent, MatchExplanation

router = APIRouter(
    prefix="/simulation",
    tags=["simulation"],
    responses={404: {"description": "Not found"}}
)


# ==================== Pydantic Models ====================

class TeamInfo(BaseModel):
    """球队信息模型"""
    team_id: int = Field(..., description="球队ID")
    team_name: str = Field(..., description="球队名称")
    elo_rating: float = Field(..., ge=1000, le=2500, description="Elo评分")
    player_value: float = Field(..., ge=0, description="核心球员身价总和（百万欧元）")
    recent_form: float = Field(..., ge=0, le=1, description="近期胜率（0-1）")
    injury_rate: float = Field(..., ge=0, le=1, description="伤病折损率（0-1）")


class GroupInfo(BaseModel):
    """小组信息模型"""
    group_name: str = Field(..., description="小组名称（如 'Group A'）")
    teams: List[TeamInfo] = Field(..., min_items=4, max_items=4, description="小组内的4支球队")


class SimulationRequest(BaseModel):
    """模拟请求模型"""
    groups: List[GroupInfo] = Field(..., min_items=12, max_items=12, description="12个小组")
    seed: Optional[int] = Field(None, description="随机种子（用于复现结果）")
    enable_attention_adjustment: bool = Field(True, description="是否启用注意力网络调整")
    generate_final_explanation: bool = Field(True, description="是否为决赛生成LLM解释")


class MatchResult(BaseModel):
    """比赛结果模型"""
    team_a_id: int = Field(..., description="A队ID")
    team_a_name: str = Field(..., description="A队名称")
    team_b_id: int = Field(..., description="B队ID")
    team_b_name: str = Field(..., description="B队名称")
    score_a: int = Field(..., description="A队进球数")
    score_b: int = Field(..., description="B队进球数")
    winner_id: int = Field(..., description="获胜队伍ID（平局为-1）")


class StandingEntry(BaseModel):
    """排名条目模型"""
    rank: int = Field(..., description="排名")
    team_id: int = Field(..., description="球队ID")
    team_name: str = Field(..., description="球队名称")
    played: int = Field(..., description="已赛场次")
    wins: int = Field(..., description="胜场")
    draws: int = Field(..., description="平局")
    losses: int = Field(..., description="负场")
    goals_for: int = Field(..., description="进球数")
    goals_against: int = Field(..., description="失球数")
    goal_difference: int = Field(..., description="净胜球")
    points: int = Field(..., description="积分")


class GroupStageResult(BaseModel):
    """小组赛结果模型"""
    group_name: str = Field(..., description="小组名称")
    standings: List[StandingEntry] = Field(..., description="小组排名")
    qualified_teams: List[int] = Field(..., description="晋级球队ID列表（前两名）")
    third_place_team: Optional[int] = Field(None, description="第三名球队ID")
    matches: List[MatchResult] = Field(default_factory=list, description="本组比赛记录")


class KnockoutMatchResult(BaseModel):
    """淘汰赛结果模型"""
    round_name: str = Field(..., description="轮次名称（如 'Round of 32'）")
    team_a_id: int = Field(..., description="A队ID")
    team_a_name: str = Field(..., description="A队名称")
    team_b_id: int = Field(..., description="B队ID")
    team_b_name: str = Field(..., description="B队名称")
    score_a: int = Field(..., description="A队进球数")
    score_b: int = Field(..., description="B队进球数")
    winner_id: int = Field(..., description="获胜队伍ID")
    is_penalty_shootout: bool = Field(False, description="是否点球大战")
    explanation: Optional[str] = Field(None, description="比赛简要说明")


class FinalExplanation(MatchExplanation):
    """决赛解释模型（继承自Pydantic Schema）"""
    pass


class SimulationResponse(BaseModel):
    """模拟响应模型"""
    status: str = Field("success", description="状态")
    tournament_winner_id: int = Field(..., description="冠军队伍ID")
    tournament_winner_name: str = Field(..., description="冠军队伍名称")
    runner_up_id: int = Field(..., description="亚军队伍ID")
    runner_up_name: str = Field(..., description="亚军队伍名称")
    final_score: str = Field(..., description="决赛比分")
    
    # 阶段结果
    group_results: List[GroupStageResult] = Field(..., description="小组赛结果")
    knockout_results: List[KnockoutMatchResult] = Field(..., description="淘汰赛结果")
    
    # LLM解释
    final_explanation: Optional[FinalExplanation] = Field(None, description="决赛的LLM解释")
    
    # 元数据
    total_matches: int = Field(..., description="总比赛场次")
    simulation_seed: Optional[int] = Field(None, description="使用的随机种子")
    attention_adjustment_enabled: bool = Field(True, description="是否启用了注意力调整")


# ==================== Helper Functions ====================

def _get_global_services(app_state):
    """从应用状态获取全局服务实例"""
    feature_model = getattr(app_state, 'feature_model', None)
    tactical_kb = getattr(app_state, 'tactical_kb', None)
    explainer_agent = getattr(app_state, 'explainer_agent', None)
    return feature_model, tactical_kb, explainer_agent


def _simulate_single_match(
    engine: ProbabilityEngine,
    team_a: TeamInfo,
    team_b: TeamInfo,
    feature_model: Optional[FeatureAttentionMixer] = None,
    enable_attention: bool = True
) -> tuple[int, int, float]:
    """
    模拟单场比赛
    
    Returns:
        (score_a, score_b, win_prob_a)
    """
    # 基础 Elo 胜率预测
    base_scores = engine.predict_score_distribution(team_a.elo_rating, team_b.elo_rating)
    
    # 如果启用了注意力网络且有模型可用，进行调整
    if enable_attention and feature_model:
        try:
            # 构建特征字典
            team_a_features = {
                'elo_rating': team_a.elo_rating,
                'player_value': team_a.player_value,
                'recent_form': team_a.recent_form,
                'injury_rate': team_a.injury_rate
            }
            team_b_features = {
                'elo_rating': team_b.elo_rating,
                'player_value': team_b.player_value,
                'recent_form': team_b.recent_form,
                'injury_rate': team_b.injury_rate
            }
            
            # 计算基础胜率（从 Elo 分差）
            rating_diff = team_b.elo_rating - team_a.elo_rating
            base_win_prob_a = 1 / (1 + 10 ** (rating_diff / 400))
            
            # 使用注意力网络调整
            adjusted_prob_a = integrate_with_probability_engine(
                engine,
                team_a.elo_rating,
                team_b.elo_rating,
                team_a_features,
                team_b_features,
                feature_model,
                base_win_prob_a
            )
            
            # 根据调整后的概率选择比分
            # 这里简化处理：如果调整后胜率显著提高，倾向于选择更有利的比分
            rand = random.random()
            cumulative_prob = 0.0
            
            for goals_a, goals_b, prob in base_scores:
                cumulative_prob += prob
                # 应用调整：如果 A 队优势增强，增加选择 A 队有利比分的概率
                adjusted_threshold = cumulative_prob * (1 + (adjusted_prob_a - base_win_prob_a) * 2)
                if rand < adjusted_threshold:
                    return goals_a, goals_b, adjusted_prob_a
            
            # 默认返回最可能的比分
            return base_scores[0][0], base_scores[0][1], adjusted_prob_a
            
        except Exception as e:
            # 如果注意力网络失败，回退到基础预测
            print(f"⚠️  Attention network failed: {e}, using base prediction")
    
    # 基础预测（无注意力调整）
    rand = random.random()
    cumulative_prob = 0.0
    
    for goals_a, goals_b, prob in base_scores:
        cumulative_prob += prob
        if rand < cumulative_prob:
            # 计算基础胜率
            rating_diff = team_b.elo_rating - team_a.elo_rating
            base_win_prob_a = 1 / (1 + 10 ** (rating_diff / 400))
            return goals_a, goals_b, base_win_prob_a
    
    # 如果随机数超出范围，返回最可能的比分
    rating_diff = team_b.elo_rating - team_a.elo_rating
    base_win_prob_a = 1 / (1 + 10 ** (rating_diff / 400))
    return base_scores[0][0], base_scores[0][1], base_win_prob_a


# ==================== API Endpoints ====================

@router.post("/predict", response_model=SimulationResponse)
async def run_simulation(
    request: SimulationRequest,
    req: Request  # 从 FastAPI Request 对象获取 app state
):
    """
    执行完整的蒙特卡洛单次模拟
    
    触发一次完整的世界杯模拟，包括：
    1. 小组赛阶段（12个小组，每组4队）
    2. 淘汰赛阶段（32强 → 16强 → 8强 → 半决赛 → 决赛）
    3. 可选：为决赛生成 LLM 战术解释
    
    Args:
        request: 模拟请求参数
        app_state: 应用状态（包含全局服务实例）
        
    Returns:
        SimulationResponse: 完整的模拟结果
        
    Example:
        POST /api/v1/simulation/predict
        {
            "groups": [...],
            "seed": 42,
            "enable_attention_adjustment": true,
            "generate_final_explanation": true
        }
    """
    # 验证小组数量
    if len(request.groups) != 12:
        raise HTTPException(status_code=400, detail="必须提供12个小组")
    
    # 获取全局服务（从 FastAPI app.state）
    feature_model = getattr(req.app.state, 'feature_model', None)
    tactical_kb = getattr(req.app.state, 'tactical_kb', None)
    explainer_agent = getattr(req.app.state, 'explainer_agent', None)
    
    print(f"\nDEBUG: Feature model is {'NOT None' if feature_model else 'None'}")
    print(f"DEBUG: Tactical KB is {'NOT None' if tactical_kb else 'None'}")
    print(f"DEBUG: Explainer Agent is {'NOT None' if explainer_agent else 'None'}")
    print(f"DEBUG: request.generate_final_explanation = {request.generate_final_explanation}")
    
    # 设置随机种子
    if request.seed is not None:
        random.seed(request.seed)
    
    # ==================== 阶段 1: 小组赛 ====================
    print("🏆 Starting group stage simulation...")
    
    # 转换数据格式为 tournament_sim 所需格式
    groups_data = []
    for group in request.groups:
        group_teams = [
            (team.team_id, team.team_name, team.elo_rating)
            for team in group.teams
        ]
        groups_data.append(group_teams)
    
    # 模拟小组赛
    tournament_result = simulate_group_stage(groups_data, seed=request.seed)
    
    # 构建小组赛结果对象
    group_results = []
    all_matches = []
    
    for i, group in enumerate(request.groups):
        # 从 tournament_result 中获取该小组的结果
        group_tournament_result = tournament_result['group_results'][i]
        
        # 模拟该小组的所有比赛（为了展示）
        engine = ProbabilityEngine()
        matches = []
        teams_list = group.teams
        
        for j in range(len(teams_list)):
            for k in range(j + 1, len(teams_list)):
                team_a = teams_list[j]
                team_b = teams_list[k]
                
                score_a, score_b, _ = _simulate_single_match(
                    engine, team_a, team_b, feature_model, request.enable_attention_adjustment
                )
                
                winner_id = team_a.team_id if score_a > score_b else (team_b.team_id if score_b > score_a else -1)
                
                match = MatchResult(
                    team_a_id=team_a.team_id,
                    team_a_name=team_a.team_name,
                    team_b_id=team_b.team_id,
                    team_b_name=team_b.team_name,
                    score_a=score_a,
                    score_b=score_b,
                    winner_id=winner_id
                )
                matches.append(match)
                all_matches.append(match)
        
        # 构建排名
        standings = []
        for standing_data in group_tournament_result['standings']:
            standings.append(StandingEntry(**standing_data))
        
        group_result = GroupStageResult(
            group_name=group.group_name,
            standings=standings,
            qualified_teams=group_tournament_result['qualified_teams'],
            third_place_team=group_tournament_result.get('third_place_team'),
            matches=matches
        )
        group_results.append(group_result)
    
    print(f"✅ Group stage completed. Qualified 32 teams.")
    
    # ==================== 阶段 2: 淘汰赛 ====================
    print("⚽ Starting knockout stage simulation...")
    
    # 注意：这里需要实现完整的淘汰赛逻辑
    # 由于 tournament_sim.py 可能还没有完整的淘汰赛实现，这里提供一个简化版本
    
    knockout_results = []
    qualified_32 = tournament_result['qualified_32']
    
    # 这里应该调用 simulate_knockout_stage 函数
    # 但为了演示，我们创建一个简化的淘汰赛流程
    # TODO: 实现完整的淘汰赛模拟
    
    # ==================== 阶段 2: 淘汰赛模拟 ====================
    print("\n🏆 Starting knockout stage simulation...")
    
    # 构建第三名排名（用于淘汰赛抽签）
    third_places_ranking = []
    for group_result in group_results:
        if group_result.third_place_team is not None:
            # 找到第三名的球队信息
            for standing in group_result.standings:
                if standing.team_id == group_result.third_place_team:
                    third_places_ranking.append({
                        "team_id": standing.team_id,
                        "team_name": standing.team_name,
                        "elo_rating": 1500.0,  # 默认 Elo
                        "points": standing.points,
                        "goal_difference": standing.goal_difference,
                        "goals_for": standing.goals_for
                    })
                    break
    
    # 按积分、净胜球、进球数排序
    third_places_ranking.sort(
        key=lambda x: (x["points"], x["goal_difference"], x["goals_for"]),
        reverse=True
    )
    
    # 调用真正的淘汰赛模拟函数
    knockout_result = simulate_knockout_stage(
        group_results=[{
            "group_name": gr.group_name,
            "standings": [{
                "team_id": s.team_id,
                "team_name": s.team_name,
                "elo_rating": next((t.elo_rating for g in request.groups for t in g.teams if t.team_id == s.team_id), 1500.0)
            } for s in gr.standings]
        } for gr in group_results],
        third_places_ranking=third_places_ranking,
        seed=request.seed
    )
    
    # 转换淘汰赛结果为 API 响应格式
    knockout_results = []
    all_knockout_rounds = [
        knockout_result["round_of_32"],
        knockout_result["round_of_16"],
        knockout_result["quarter_finals"],
        knockout_result["semi_finals"],
        knockout_result["final"]
    ]
    
    for round_data in all_knockout_rounds:
        for match in round_data["matches"]:
            knockout_results.append(KnockoutMatchResult(
                round_name=round_data["round_name"],
                team_a_id=match["team_a_id"],
                team_a_name=match["team_a_name"],
                team_b_id=match["team_b_id"],
                team_b_name=match["team_b_name"],
                score_a=match["score_a"],
                score_b=match["score_b"],
                winner_id=match["winner_id"],
                is_penalty_shootout=match.get("is_penalty_shootout", False),
                explanation=match.get("explanation")
            ))
    
    print(f"✅ Knockout stage complete! Total matches: {len(knockout_results)}")
    
    # ==================== 阶段 3: 决赛 LLM 解释 ====================
    final_explanation = None
    
    print(f"\nDEBUG: request.generate_final_explanation = {request.generate_final_explanation}")
    print(f"DEBUG: explainer_agent is {'NOT None' if explainer_agent else 'None'}")
    
    if request.generate_final_explanation and explainer_agent:
        print("🧠 Generating final match explanation with LLM...")
        
        try:
            # 从淘汰赛结果中获取决赛的两支队伍
            final_match = knockout_result["final"]["matches"][0]
            
            finalist_a_id = final_match["team_a_id"]
            finalist_b_id = final_match["team_b_id"]
            
            # 找到对应的球队信息
            finalist_a = None
            finalist_b = None
            
            for group in request.groups:
                for team in group.teams:
                    if team.team_id == finalist_a_id:
                        finalist_a = team
                    if team.team_id == finalist_b_id:
                        finalist_b = team
            
            if finalist_a and finalist_b:
                # 计算基础胜率
                rating_diff = finalist_b.elo_rating - finalist_a.elo_rating
                base_win_prob = 1 / (1 + 10 ** (rating_diff / 400))
                
                # 使用真实的决赛比分
                predicted_score_a = final_match["score_a"]
                predicted_score_b = final_match["score_b"]
                winner_name = final_match["winner_name"]
                
                print(f"📊 Final match: {finalist_a.team_name} vs {finalist_b.team_name}")
                print(f"⚽ Predicted score: {predicted_score_a}:{predicted_score_b}")
                print(f"🏆 Winner: {winner_name}")
                
                # 调用 LLM Agent 生成解释（使用正确的参数）
                explanation = explainer_agent.explain_match(
                    team_a_name=finalist_a.team_name,
                    team_a_elo=finalist_a.elo_rating,
                    team_b_name=finalist_b.team_name,
                    team_b_elo=finalist_b.elo_rating,
                    score_a=predicted_score_a,
                    score_b=predicted_score_b,
                    winner_name=winner_name,
                    adjustment=0.05,  # 示例调整系数
                    base_win_prob=base_win_prob
                )
                
                # 转换为 Pydantic 模型
                final_explanation = FinalExplanation(**explanation.dict())
                
                print("✅ Final explanation generated successfully!")
            else:
                print(f"⚠️  Could not find finalists in request data (IDs: {finalist_a_id}, {finalist_b_id})")
        
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"❌ Failed to generate explanation: {e}")
            print(f"📋 Error details:\n{error_details}")
            # 不抛出异常，继续返回结果
    
    # ==================== 构建响应 ====================
    # 从淘汰赛结果中确定冠军和亚军
    final_match = knockout_result["final"]["matches"][0]
    champion_id = final_match["winner_id"]
    champion_name = final_match["winner_name"]
    
    # 亚军是决赛中输掉的那一方
    if final_match["team_a_id"] == champion_id:
        runner_up_id = final_match["team_b_id"]
        runner_up_name = final_match["team_b_name"]
    else:
        runner_up_id = final_match["team_a_id"]
        runner_up_name = final_match["team_a_name"]
    
    final_score = f"{final_match['score_a']}:{final_match['score_b']}"
    
    response = SimulationResponse(
        status="success",
        tournament_winner_id=champion_id,
        tournament_winner_name=champion_name,
        runner_up_id=runner_up_id,
        runner_up_name=runner_up_name,
        final_score=final_score,
        group_results=group_results,
        knockout_results=knockout_results,
        final_explanation=final_explanation,
        total_matches=len(all_matches) + len(knockout_results),
        simulation_seed=request.seed,
        attention_adjustment_enabled=request.enable_attention_adjustment
    )
    
    print(f"🎉 Simulation complete! Winner: {champion_name}")
    
    return response


@router.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "ok",
        "service": "simulation",
        "version": "1.0.0"
    }
