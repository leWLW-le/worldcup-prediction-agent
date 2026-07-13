"""
2026 世界杯 48 队赛制小组赛模拟器

实现 12 个小组（每组 4 队）的单循环比赛模拟，并根据积分规则选出晋级 32 强的球队。
"""

import sys
from pathlib import Path
# 添加项目根目录到 Python 路径（用于直接运行此文件时）
if __name__ == "__main__":
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

import random
from typing import TypedDict
from dataclasses import dataclass, field
from app.services.probability_engine import ProbabilityEngine


@dataclass
class TeamStats:
    """球队统计数据"""
    team_id: int
    team_name: str
    elo_rating: float
    
    # 比赛统计
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0
    
    # 相互交锋记录（用于 tiebreaker）
    head_to_head: dict[int, tuple[int, int]] = field(default_factory=dict)  # {opponent_id: (goals_for, goals_against)}
    
    @property
    def goal_difference(self) -> int:
        """净胜球"""
        return self.goals_for - self.goals_against
    
    def add_match_result(self, opponent_id: int, goals_for: int, goals_against: int):
        """添加比赛结果"""
        self.played += 1
        self.goals_for += goals_for
        self.goals_against += goals_against
        self.head_to_head[opponent_id] = (goals_for, goals_against)
        
        if goals_for > goals_against:
            self.wins += 1
            self.points += 3
        elif goals_for == goals_against:
            self.draws += 1
            self.points += 1
        else:
            self.losses += 1
    
    def get_head_to_head_record(self, opponent_id: int) -> tuple[int, int]:
        """获取与对手的交锋记录"""
        return self.head_to_head.get(opponent_id, (0, 0))


class GroupResult(TypedDict):
    """小组结果"""
    group_name: str
    standings: list[dict]  # 排名列表
    qualified_teams: list[int]  # 晋级的球队ID（前两名）
    third_place_team: int | None  # 第三名球队ID


class TournamentResult(TypedDict):
    """锦标赛结果"""
    qualified_32: list[int]  # 晋级32强的球队ID列表
    group_results: list[GroupResult]  # 各小组结果
    third_places_ranking: list[dict]  # 所有小组第三名的排名


def simulate_group_match(
    engine: ProbabilityEngine,
    team_a_id: int,
    team_a_elo: float,
    team_b_id: int,
    team_b_elo: float
) -> tuple[int, int]:
    """
    模拟一场比赛并返回比分
    
    Args:
        engine: 概率引擎
        team_a_id: A队ID
        team_a_elo: A队Elo评分
        team_b_id: B队ID
        team_b_elo: B队Elo评分
        
    Returns:
        (A队进球数, B队进球数)
    """
    # 获取比分分布
    top_scores = engine.predict_score_distribution(team_a_elo, team_b_elo)
    
    # 根据概率随机选择比分
    rand = random.random()
    cumulative_prob = 0.0
    
    for goals_a, goals_b, prob in top_scores:
        cumulative_prob += prob
        if rand < cumulative_prob:
            return goals_a, goals_b
    
    # 如果随机数超出范围，返回最可能的比分
    return top_scores[0][0], top_scores[0][1]


def simulate_group_stage(
    groups: list[list[tuple[int, str, float]]],
    seed: int | None = None
) -> TournamentResult:
    """
    模拟小组赛阶段
    
    Args:
        groups: 12个小组的列表，每个小组包含4支球队的元组 (team_id, team_name, elo_rating)
        seed: 随机种子（可选，用于复现结果）
        
    Returns:
        TournamentResult: 包含晋级32强的球队名单和各小组结果
    """
    if seed is not None:
        random.seed(seed)
    
    engine = ProbabilityEngine()
    group_results = []
    all_third_places = []
    
    # 模拟每个小组
    for group_idx, group_teams in enumerate(groups):
        group_name = f"Group {chr(65 + group_idx)}"  # Group A, B, C, ...
        
        # 初始化球队统计
        team_stats = {}
        for team_id, team_name, elo in group_teams:
            team_stats[team_id] = TeamStats(
                team_id=team_id,
                team_name=team_name,
                elo_rating=elo
            )
        
        # 单循环比赛：每两队之间进行一场比赛
        teams_list = list(group_teams)
        for i in range(len(teams_list)):
            for j in range(i + 1, len(teams_list)):
                team_a_id, team_a_name, team_a_elo = teams_list[i]
                team_b_id, team_b_name, team_b_elo = teams_list[j]
                
                # 模拟比赛
                goals_a, goals_b = simulate_group_match(
                    engine,
                    team_a_id, team_a_elo,
                    team_b_id, team_b_elo
                )
                
                # 更新统计数据
                team_stats[team_a_id].add_match_result(team_b_id, goals_a, goals_b)
                team_stats[team_b_id].add_match_result(team_a_id, goals_b, goals_a)
        
        # 对小组内球队进行排名
        ranked_teams = rank_teams(list(team_stats.values()))
        
        # 构建排名数据
        standings = []
        for rank, stats in enumerate(ranked_teams, 1):
            standings.append({
                "rank": rank,
                "team_id": stats.team_id,
                "team_name": stats.team_name,
                "played": stats.played,
                "wins": stats.wins,
                "draws": stats.draws,
                "losses": stats.losses,
                "goals_for": stats.goals_for,
                "goals_against": stats.goals_against,
                "goal_difference": stats.goal_difference,
                "points": stats.points
            })
        
        # 确定晋级球队（前两名）
        qualified_teams = [ranked_teams[0].team_id, ranked_teams[1].team_id]
        third_place_team = ranked_teams[2].team_id if len(ranked_teams) >= 3 else None
        
        # 记录小组结果
        group_result: GroupResult = {
            "group_name": group_name,
            "standings": standings,
            "qualified_teams": qualified_teams,
            "third_place_team": third_place_team
        }
        group_results.append(group_result)
        
        # 收集第三名球队信息
        if third_place_team is not None:
            third_stats = ranked_teams[2]
            all_third_places.append({
                "team_id": third_stats.team_id,
                "team_name": third_stats.team_name,
                "group_name": group_name,
                "points": third_stats.points,
                "goal_difference": third_stats.goal_difference,
                "goals_for": third_stats.goals_for,
                "stats": third_stats  # 保留完整统计用于后续比较
            })
    
    # 从12个小组中选出8个成绩最好的第三名
    best_third_places = select_best_third_places(all_third_places)
    
    # 合并晋级32强的球队
    qualified_32 = []
    for result in group_results:
        qualified_32.extend(result["qualified_teams"])
    
    # 添加8个最佳第三名
    for third in best_third_places:
        qualified_32.append(third["team_id"])
    
    # 构建最终结果
    result: TournamentResult = {
        "qualified_32": qualified_32,
        "group_results": group_results,
        "third_places_ranking": [
            {
                "rank": i + 1,
                "team_id": t["team_id"],
                "team_name": t["team_name"],
                "group_name": t["group_name"],
                "points": t["points"],
                "goal_difference": t["goal_difference"],
                "goals_for": t["goals_for"]
            }
            for i, t in enumerate(best_third_places)
        ]
    }
    
    return result


def rank_teams(teams: list[TeamStats]) -> list[TeamStats]:
    """
    根据规则对球队进行排名
    
    排序规则（优先级从高到低）：
    1. 积分
    2. 净胜球
    3. 总进球数
    4. 相互交锋战绩
    
    Args:
        teams: 球队统计列表
        
    Returns:
        按排名排序的球队列表
    """
    def sort_key(team: TeamStats):
        # 主要排序键：积分、净胜球、总进球数（降序）
        primary_key = (-team.points, -team.goal_difference, -team.goals_for)
        return primary_key
    
    # 首先按主要规则排序
    sorted_teams = sorted(teams, key=sort_key)
    
    # 处理积分相同的情况，应用相互交锋战绩作为 tiebreaker
    # 需要检查是否有并列情况
    result = []
    processed = set()
    
    for i, team in enumerate(sorted_teams):
        if team.team_id in processed:
            continue
        
        # 找到所有与当前球队积分、净胜球、进球数相同的球队
        tied_teams = [team]
        for j in range(i + 1, len(sorted_teams)):
            other = sorted_teams[j]
            if (other.points == team.points and 
                other.goal_difference == team.goal_difference and 
                other.goals_for == team.goals_for):
                tied_teams.append(other)
        
        if len(tied_teams) > 1:
            # 使用相互交锋战绩打破平局
            tied_teams = break_tie_by_head_to_head(tied_teams)
        
        for t in tied_teams:
            result.append(t)
            processed.add(t.team_id)
    
    return result


def break_tie_by_head_to_head(teams: list[TeamStats]) -> list[TeamStats]:
    """
    使用相互交锋战绩打破平局
    
    Args:
        teams: 积分相同的球队列表
        
    Returns:
        按相互交锋战绩排序后的球队列表
    """
    if len(teams) <= 1:
        return teams
    
    # 计算每支球队在并列球队中的交锋表现
    head_to_head_stats = {}
    
    for team in teams:
        h2h_points = 0
        h2h_gd = 0
        h2h_gf = 0
        
        for other in teams:
            if other.team_id != team.team_id:
                goals_for, goals_against = team.get_head_to_head_record(other.team_id)
                h2h_gf += goals_for
                h2h_gd += (goals_for - goals_against)
                
                if goals_for > goals_against:
                    h2h_points += 3
                elif goals_for == goals_against:
                    h2h_points += 1
        
        head_to_head_stats[team.team_id] = (h2h_points, h2h_gd, h2h_gf)
    
    # 按相互交锋战绩排序
    def h2h_key(team: TeamStats):
        stats = head_to_head_stats[team.team_id]
        return (-stats[0], -stats[1], -stats[2])  # 交锋积分、净胜球、进球数（降序）
    
    return sorted(teams, key=h2h_key)


def select_best_third_places(third_places: list[dict]) -> list[dict]:
    """
    从12个小组第三名中选出8个成绩最好的
    
    排序规则（与小组排名相同）：
    1. 积分
    2. 净胜球
    3. 总进球数
    
    Args:
        third_places: 所有小组第三名球队的信息列表
        
    Returns:
        8个最佳第三名的列表（已排序）
    """
    # 按积分、净胜球、进球数排序
    def sort_key(third: dict):
        return (-third["points"], -third["goal_difference"], -third["goals_for"])
    
    sorted_thirds = sorted(third_places, key=sort_key)
    
    # 取前8名
    return sorted_thirds[:8]


# ==================== 淘汰赛阶段 ====================

class KnockoutMatch(TypedDict):
    """淘汰赛比赛"""
    round_name: str  # 轮次名称
    match_number: int  # 比赛编号
    team_a_id: int
    team_a_name: str
    team_a_elo: float
    team_b_id: int
    team_b_name: str
    team_b_elo: float
    score_a: int
    score_b: int
    winner_id: int
    winner_name: str
    is_penalty_shootout: bool  # 是否点球大战


class KnockoutRound(TypedDict):
    """淘汰赛轮次"""
    round_name: str
    matches: list[KnockoutMatch]


class KnockoutStageResult(TypedDict):
    """淘汰赛阶段结果"""
    round_of_32: KnockoutRound  # 1/16决赛
    round_of_16: KnockoutRound  # 1/8决赛
    quarter_finals: KnockoutRound  # 1/4决赛
    semi_finals: KnockoutRound  # 半决赛
    final: KnockoutRound  # 决赛
    champion: dict  # 冠军信息


# 2026世界杯32强固定落位对阵表
# 格式：(小组排名标识, 对手小组排名标识)
# 例如：("A1", "B2") 表示 A组第一 vs B组第二
KNOCKOUT_BRACKET = {
    # 1/16决赛 (Round of 32) - 16场比赛
    "round_of_32": [
        ("A1", "B2"), ("C1", "D2"), ("E1", "F2"), ("G1", "H2"),
        ("I1", "J2"), ("K1", "L2"), ("B1", "A2"), ("D1", "C2"),
        ("F1", "E2"), ("H1", "G2"), ("J1", "I2"), ("L1", "K2"),
        # 8个最佳第三名的对阵（根据具体排名决定）
        ("3rd_1", "3rd_8"), ("3rd_2", "3rd_7"), ("3rd_3", "3rd_6"), ("3rd_4", "3rd_5")
    ],
    # 1/8决赛 (Round of 16) - 8场比赛
    "round_of_16": [
        ("R32_1", "R32_2"), ("R32_3", "R32_4"),
        ("R32_5", "R32_6"), ("R32_7", "R32_8"),
        ("R32_9", "R32_10"), ("R32_11", "R32_12"),
        ("R32_13", "R32_14"), ("R32_15", "R32_16")
    ],
    # 1/4决赛 (Quarter-finals) - 4场比赛
    "quarter_finals": [
        ("R16_1", "R16_2"), ("R16_3", "R16_4"),
        ("R16_5", "R16_6"), ("R16_7", "R16_8")
    ],
    # 半决赛 (Semi-finals) - 2场比赛
    "semi_finals": [
        ("QF_1", "QF_2"), ("QF_3", "QF_4")
    ],
    # 决赛 (Final) - 1场比赛
    "final": [
        ("SF_1", "SF_2")
    ]
}


def get_team_info(
    team_id: int,
    group_results: list[GroupResult],
    third_places_ranking: list[dict]
) -> tuple[str, float] | None:
    """
    根据球队ID获取球队信息
    
    Args:
        team_id: 球队ID
        group_results: 小组赛结果
        third_places_ranking: 第三名排名
        
    Returns:
        (team_name, elo_rating) 或 None
    """
    # 先在前两名中查找
    for group_result in group_results:
        for standing in group_result["standings"]:
            if standing["team_id"] == team_id:
                return standing["team_name"], standing.get("elo_rating", 1500.0)
    
    # 再在第三名中查找
    for third in third_places_ranking:
        if third["team_id"] == team_id:
            return third["team_name"], third.get("elo_rating", 1500.0)
    
    return None


def resolve_knockout_matchup(
    matchup: tuple[str, str],
    qualified_teams_map: dict[str, tuple[int, str, float]],
    previous_round_winners: dict[str, tuple[int, str, float]]
) -> tuple[tuple[int, str, float], tuple[int, str, float]]:
    """
    解析淘汰赛对阵，获取两支球队的信息
    
    Args:
        matchup: 对阵标识，如 ("A1", "B2")
        qualified_teams_map: 32强球队映射 {"A1": (id, name, elo), ...}
        previous_round_winners: 上一轮胜者映射 {"R32_1": (id, name, elo), ...}
        
    Returns:
        (team_a_info, team_b_info)
    """
    team_a_key, team_b_key = matchup
    
    # 尝试从上一轮胜者中获取
    if team_a_key.startswith(("R32_", "R16_", "QF_", "SF_")):
        team_a = previous_round_winners.get(team_a_key)
    else:
        team_a = qualified_teams_map.get(team_a_key)
    
    if team_b_key.startswith(("R32_", "R16_", "QF_", "SF_")):
        team_b = previous_round_winners.get(team_b_key)
    else:
        team_b = qualified_teams_map.get(team_b_key)
    
    if not team_a or not team_b:
        raise ValueError(f"无法找到球队: {team_a_key} vs {team_b_key}")
    
    return team_a, team_b


def simulate_knockout_match(
    engine: ProbabilityEngine,
    team_a_id: int,
    team_a_name: str,
    team_a_elo: float,
    team_b_id: int,
    team_b_name: str,
    team_b_elo: float,
    round_name: str,
    match_number: int
) -> KnockoutMatch:
    """
    模拟一场淘汰赛
    
    Args:
        engine: 概率引擎
        team_a_id, team_a_name, team_a_elo: A队信息
        team_b_id, team_b_name, team_b_elo: B队信息
        round_name: 轮次名称
        match_number: 比赛编号
        
    Returns:
        KnockoutMatch: 比赛结果
    """
    # 模拟常规时间比分
    goals_a, goals_b = simulate_group_match(
        engine, team_a_id, team_a_elo, team_b_id, team_b_elo
    )
    
    is_penalty_shootout = False
    
    # 如果平局，进行点球大战
    if goals_a == goals_b:
        is_penalty_shootout = True
        # 点球大战随机决定胜负（简化处理）
        if random.random() < 0.5:
            goals_a += 1  # A队点球获胜
        else:
            goals_b += 1  # B队点球获胜
    
    # 确定胜者
    if goals_a > goals_b:
        winner_id = team_a_id
        winner_name = team_a_name
    else:
        winner_id = team_b_id
        winner_name = team_b_name
    
    return KnockoutMatch(
        round_name=round_name,
        match_number=match_number,
        team_a_id=team_a_id,
        team_a_name=team_a_name,
        team_a_elo=team_a_elo,
        team_b_id=team_b_id,
        team_b_name=team_b_name,
        team_b_elo=team_b_elo,
        score_a=goals_a,
        score_b=goals_b,
        winner_id=winner_id,
        winner_name=winner_name,
        is_penalty_shootout=is_penalty_shootout
    )


def simulate_knockout_stage(
    group_results: list[GroupResult],
    third_places_ranking: list[dict],
    seed: int | None = None
) -> KnockoutStageResult:
    """
    模拟淘汰赛阶段
    
    Args:
        group_results: 小组赛结果
        third_places_ranking: 第三名排名
        seed: 随机种子
        
    Returns:
        KnockoutStageResult: 完整的淘汰赛结果
    """
    if seed is not None:
        random.seed(seed)
    
    engine = ProbabilityEngine()
    
    # 构建32强球队映射
    qualified_teams_map = {}
    
    # 添加小组前两名
    for group_idx, group_result in enumerate(group_results):
        group_letter = chr(65 + group_idx)  # A, B, C, ...
        standings = group_result["standings"]
        
        # 第一名
        first_place = standings[0]
        qualified_teams_map[f"{group_letter}1"] = (
            first_place["team_id"],
            first_place["team_name"],
            first_place.get("elo_rating", 1500.0)
        )
        
        # 第二名
        second_place = standings[1]
        qualified_teams_map[f"{group_letter}2"] = (
            second_place["team_id"],
            second_place["team_name"],
            second_place.get("elo_rating", 1500.0)
        )
    
    # 添加8个最佳第三名
    for i, third in enumerate(third_places_ranking[:8], 1):
        qualified_teams_map[f"3rd_{i}"] = (
            third["team_id"],
            third["team_name"],
            third.get("elo_rating", 1500.0)
        )
    
    # 存储每轮比赛的胜者
    previous_round_winners = {}
    
    # ==================== 1/16决赛 ====================
    round_of_32_matches = []
    for i, matchup in enumerate(KNOCKOUT_BRACKET["round_of_32"], 1):
        team_a, team_b = resolve_knockout_matchup(
            matchup, qualified_teams_map, previous_round_winners
        )
        
        match = simulate_knockout_match(
            engine,
            team_a[0], team_a[1], team_a[2],
            team_b[0], team_b[1], team_b[2],
            "Round of 32",
            i
        )
        
        round_of_32_matches.append(match)
        previous_round_winners[f"R32_{i}"] = (
            match["winner_id"],
            match["winner_name"],
            match["team_a_elo"] if match["winner_id"] == match["team_a_id"] else match["team_b_elo"]
        )
    
    round_of_32 = KnockoutRound(
        round_name="Round of 32",
        matches=round_of_32_matches
    )
    
    # ==================== 1/8决赛 ====================
    round_of_16_matches = []
    for i, matchup in enumerate(KNOCKOUT_BRACKET["round_of_16"], 1):
        team_a, team_b = resolve_knockout_matchup(
            matchup, qualified_teams_map, previous_round_winners
        )
        
        match = simulate_knockout_match(
            engine,
            team_a[0], team_a[1], team_a[2],
            team_b[0], team_b[1], team_b[2],
            "Round of 16",
            i
        )
        
        round_of_16_matches.append(match)
        previous_round_winners[f"R16_{i}"] = (
            match["winner_id"],
            match["winner_name"],
            match["team_a_elo"] if match["winner_id"] == match["team_a_id"] else match["team_b_elo"]
        )
    
    round_of_16 = KnockoutRound(
        round_name="Round of 16",
        matches=round_of_16_matches
    )
    
    # ==================== 1/4决赛 ====================
    quarter_finals_matches = []
    for i, matchup in enumerate(KNOCKOUT_BRACKET["quarter_finals"], 1):
        team_a, team_b = resolve_knockout_matchup(
            matchup, qualified_teams_map, previous_round_winners
        )
        
        match = simulate_knockout_match(
            engine,
            team_a[0], team_a[1], team_a[2],
            team_b[0], team_b[1], team_b[2],
            "Quarter-finals",
            i
        )
        
        quarter_finals_matches.append(match)
        previous_round_winners[f"QF_{i}"] = (
            match["winner_id"],
            match["winner_name"],
            match["team_a_elo"] if match["winner_id"] == match["team_a_id"] else match["team_b_elo"]
        )
    
    quarter_finals = KnockoutRound(
        round_name="Quarter-finals",
        matches=quarter_finals_matches
    )
    
    # ==================== 半决赛 ====================
    semi_finals_matches = []
    for i, matchup in enumerate(KNOCKOUT_BRACKET["semi_finals"], 1):
        team_a, team_b = resolve_knockout_matchup(
            matchup, qualified_teams_map, previous_round_winners
        )
        
        match = simulate_knockout_match(
            engine,
            team_a[0], team_a[1], team_a[2],
            team_b[0], team_b[1], team_b[2],
            "Semi-finals",
            i
        )
        
        semi_finals_matches.append(match)
        previous_round_winners[f"SF_{i}"] = (
            match["winner_id"],
            match["winner_name"],
            match["team_a_elo"] if match["winner_id"] == match["team_a_id"] else match["team_b_elo"]
        )
    
    semi_finals = KnockoutRound(
        round_name="Semi-finals",
        matches=semi_finals_matches
    )
    
    # ==================== 决赛 ====================
    final_matches = []
    for i, matchup in enumerate(KNOCKOUT_BRACKET["final"], 1):
        team_a, team_b = resolve_knockout_matchup(
            matchup, qualified_teams_map, previous_round_winners
        )
        
        match = simulate_knockout_match(
            engine,
            team_a[0], team_a[1], team_a[2],
            team_b[0], team_b[1], team_b[2],
            "Final",
            i
        )
        
        final_matches.append(match)
    
    final = KnockoutRound(
        round_name="Final",
        matches=final_matches
    )
    
    # 确定冠军
    champion_match = final_matches[0]
    champion = {
        "team_id": champion_match["winner_id"],
        "team_name": champion_match["winner_name"],
        "elo_rating": champion_match["team_a_elo"] if champion_match["winner_id"] == champion_match["team_a_id"] else champion_match["team_b_elo"]
    }
    
    return KnockoutStageResult(
        round_of_32=round_of_32,
        round_of_16=round_of_16,
        quarter_finals=quarter_finals,
        semi_finals=semi_finals,
        final=final,
        champion=champion
    )


# 测试代码
if __name__ == "__main__":
    print("=" * 70)
    print("2026 世界杯 48 队小组赛模拟器测试")
    print("=" * 70)
    
    # 创建示例数据：12个小组，每组4支球队
    # 格式：[(team_id, team_name, elo_rating), ...]
    # 2026 美加墨世界杯真实分组
    sample_groups = [
        # Group A: Mexico, South Africa, South Korea, Czech Republic
        [
            (1, "Mexico", 1830.0),
            (2, "South Africa", 1620.0),
            (3, "South Korea", 1700.0),
            (4, "Czech Republic", 1650.0)
        ],
        # Group B: Canada, Bosnia, Qatar, Switzerland
        [
            (5, "Canada", 1710.0),
            (6, "Bosnia", 1640.0),
            (7, "Qatar", 1500.0),
            (8, "Switzerland", 1860.0)
        ],
        # Group C: Brazil, Morocco, Haiti, Scotland
        [
            (9, "Brazil", 2060.0),
            (10, "Morocco", 1820.0),
            (11, "Haiti", 1480.0),
            (12, "Scotland", 1690.0)
        ],
        # Group D: USA, Paraguay, Australia, Turkey
        [
            (13, "USA", 1780.0),
            (14, "Paraguay", 1650.0),
            (15, "Australia", 1700.0),
            (16, "Turkey", 1720.0)
        ],
        # Group E: Germany, Curacao, Ivory Coast, Ecuador
        [
            (17, "Germany", 2000.0),
            (18, "Curacao", 1420.0),
            (19, "Ivory Coast", 1660.0),
            (20, "Ecuador", 1740.0)
        ],
        # Group F: Netherlands, Japan, Sweden, Tunisia
        [
            (21, "Netherlands", 1960.0),
            (22, "Japan", 1750.0),
            (23, "Sweden", 1770.0),
            (24, "Tunisia", 1610.0)
        ],
        # Group G: Belgium, Egypt, Iran, New Zealand
        [
            (25, "Belgium", 1880.0),
            (26, "Egypt", 1680.0),
            (27, "Iran", 1650.0),
            (28, "New Zealand", 1530.0)
        ],
        # Group H: Spain, Cape Verde, Saudi Arabia, Uruguay
        [
            (29, "Spain", 2080.0),
            (30, "Cape Verde", 1520.0),
            (31, "Saudi Arabia", 1560.0),
            (32, "Uruguay", 1820.0)
        ],
        # Group I: France, Senegal, Iraq, Norway
        [
            (33, "France", 2100.0),
            (34, "Senegal", 1720.0),
            (35, "Iraq", 1480.0),
            (36, "Norway", 1800.0)
        ],
        # Group J: Argentina, Algeria, Austria, Jordan
        [
            (37, "Argentina", 2050.0),
            (38, "Algeria", 1600.0),
            (39, "Austria", 1750.0),
            (40, "Jordan", 1440.0)
        ],
        # Group K: Portugal, DR Congo, Uzbekistan, Colombia
        [
            (41, "Portugal", 1980.0),
            (42, "DR Congo", 1460.0),
            (43, "Uzbekistan", 1580.0),
            (44, "Colombia", 1840.0)
        ],
        # Group L: England, Croatia, Ghana, Panama
        [
            (45, "England", 2040.0),
            (46, "Croatia", 1860.0),
            (47, "Ghana", 1640.0),
            (48, "Panama", 1600.0)
        ]
    ]
    
    # 运行模拟
    print(f"\n开始模拟 {len(sample_groups)} 个小组的比赛...")
    print("-" * 70)
    
    result = simulate_group_stage(sample_groups, seed=42)
    
    # 输出结果
    print("\n各小组排名:")
    print("=" * 70)
    
    for group_result in result["group_results"]:
        print(f"\n{group_result['group_name']}:")
        print("-" * 70)
        print(f"{'排名':<6} {'球队':<20} {'场次':<6} {'胜':<4} {'平':<4} {'负':<4} {'进球':<6} {'失球':<6} {'净胜':<6} {'积分':<6}")
        print("-" * 70)
        
        for standing in group_result["standings"]:
            print(f"{standing['rank']:<6} {standing['team_name']:<20} "
                  f"{standing['played']:<6} {standing['wins']:<4} {standing['draws']:<4} "
                  f"{standing['losses']:<4} {standing['goals_for']:<6} {standing['goals_against']:<6} "
                  f"{standing['goal_difference']:<6} {standing['points']:<6}")
        
        print(f"\n晋级球队: {[standing['team_name'] for standing in group_result['standings'][:2]]}")
    
    # 输出最佳第三名
    print("\n\n8个最佳小组第三名:")
    print("=" * 70)
    print(f"{'排名':<6} {'球队':<20} {'小组':<10} {'积分':<6} {'净胜球':<8} {'进球':<6}")
    print("-" * 70)
    
    for ranking in result["third_places_ranking"]:
        print(f"{ranking['rank']:<6} {ranking['team_name']:<20} "
              f"{ranking['group_name']:<10} {ranking['points']:<6} "
              f"{ranking['goal_difference']:<8} {ranking['goals_for']:<6}")
    
    # 输出最终晋级名单
    print("\n\n晋级 32 强的球队名单:")
    print("=" * 70)
    print(f"共 {len(result['qualified_32'])} 支球队")
    print("-" * 70)
    
    # 按小组显示
    for i, group_result in enumerate(result["group_results"]):
        group_name = group_result["group_name"]
        qualified_from_group = [tid for tid in result["qualified_32"][:24] 
                               if tid in group_result["qualified_teams"]]
        
        if qualified_from_group:
            team_names = []
            for standing in group_result["standings"]:
                if standing["team_id"] in qualified_from_group:
                    team_names.append(standing["team_name"])
            print(f"{group_name}: {', '.join(team_names)}")
    
    print("\n8个最佳第三名:")
    third_place_names = []
    for ranking in result["third_places_ranking"]:
        third_place_names.append(f"{ranking['team_name']} ({ranking['group_name']})")
    print(", ".join(third_place_names))
    
    print("\n" + "=" * 70)
    print("模拟完成！")
    print("=" * 70)
    
    # ==================== 淘汰赛阶段 ====================
    print("\n\n" + "=" * 70)
    print("开始模拟淘汰赛阶段")
    print("=" * 70)
    
    knockout_result = simulate_knockout_stage(
        result["group_results"],
        result["third_places_ranking"],
        seed=42
    )
    
    # 输出淘汰赛结果
    print("\n【1/16决赛】Round of 32")
    print("-" * 70)
    for match in knockout_result["round_of_32"]["matches"]:
        shootout_marker = " (点球)" if match["is_penalty_shootout"] else ""
        print(f"{match['team_a_name']} {match['score_a']}-{match['score_b']} {match['team_b_name']}{shootout_marker}")
        print(f"  → 胜者: {match['winner_name']}")
    
    print("\n【1/8决赛】Round of 16")
    print("-" * 70)
    for match in knockout_result["round_of_16"]["matches"]:
        shootout_marker = " (点球)" if match["is_penalty_shootout"] else ""
        print(f"{match['team_a_name']} {match['score_a']}-{match['score_b']} {match['team_b_name']}{shootout_marker}")
        print(f"  → 胜者: {match['winner_name']}")
    
    print("\n【1/4决赛】Quarter-finals")
    print("-" * 70)
    for match in knockout_result["quarter_finals"]["matches"]:
        shootout_marker = " (点球)" if match["is_penalty_shootout"] else ""
        print(f"{match['team_a_name']} {match['score_a']}-{match['score_b']} {match['team_b_name']}{shootout_marker}")
        print(f"  → 胜者: {match['winner_name']}")
    
    print("\n【半决赛】Semi-finals")
    print("-" * 70)
    for match in knockout_result["semi_finals"]["matches"]:
        shootout_marker = " (点球)" if match["is_penalty_shootout"] else ""
        print(f"{match['team_a_name']} {match['score_a']}-{match['score_b']} {match['team_b_name']}{shootout_marker}")
        print(f"  → 胜者: {match['winner_name']}")
    
    print("\n【决赛】Final")
    print("-" * 70)
    final_match = knockout_result["final"]["matches"][0]
    shootout_marker = " (点球)" if final_match["is_penalty_shootout"] else ""
    print(f"{final_match['team_a_name']} {final_match['score_a']}-{final_match['score_b']} {final_match['team_b_name']}{shootout_marker}")
    
    print("\n" + "=" * 70)
    print(f"冠军: {knockout_result['champion']['team_name']}")
    print("=" * 70)
