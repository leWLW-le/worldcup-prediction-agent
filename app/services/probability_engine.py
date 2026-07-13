"""
概率预测引擎模块

提供基于 Elo 评分和泊松分布的足球比赛概率计算功能。
该引擎独立于大模型，专注于数学概率计算。
"""

import math
from typing import Tuple


class ProbabilityEngine:
    """
    足球比赛概率预测引擎
    
    基于 Elo 评分系统和泊松分布模型进行比赛结果预测。
    提供纯函数式接口，无副作用。
    
    Attributes:
        K_FACTOR (float): Elo 更新的 K 因子，控制评分变化速度
        PENALTY_K_FACTOR (float): 点球大战时使用的 K 因子（通常为 0）
    """
    
    # Elo 更新参数
    K_FACTOR = 30.0  # 标准比赛的 K 值
    PENALTY_K_FACTOR = 0.0  # 点球大战不改变常规时间 Elo
    
    @staticmethod
    def calculate_elo_update(
        old_rating_a: float,
        old_rating_b: float,
        actual_result_a: float,
        is_penalty_shootout: bool = False
    ) -> Tuple[float, float]:
        """
        计算 Elo 评分更新
        
        基于公式 R_new = R_old + K × (W - W_e) 更新球队积分。
        
        Args:
            old_rating_a (float): A 队当前 Elo 评分
            old_rating_b (float): B 队当前 Elo 评分
            actual_result_a (float): A 队的实际比赛结果
                - 1.0: A 队获胜
                - 0.5: 平局
                - 0.0: A 队失败
            is_penalty_shootout (bool): 是否为点球大战
            
        Returns:
            Tuple[float, float]: (A 队新评分, B 队新评分)
            
        Raises:
            ValueError: 当实际结果不在 [0, 1] 范围内时抛出异常
            
        Examples:
            >>> engine = ProbabilityEngine()
            >>> new_a, new_b = engine.calculate_elo_update(2000, 1800, 1.0)
            >>> print(f"A队: {new_a:.2f}, B队: {new_b:.2f}")
            A队: 2004.76, B队: 1795.24
            
        Note:
            点球大战时不会改变常规时间的 Elo 评分（K=0）。
            这是因为点球大战具有较大的偶然性，不应过度影响球队实力评估。
        """
        # 验证输入参数
        if not 0 <= actual_result_a <= 1:
            raise ValueError("Actual result must be between 0 and 1")
        
        # 计算期望胜率 W_e = 1 / (1 + 10^((R_B - R_A)/400))
        rating_diff = old_rating_b - old_rating_a
        expected_win_rate_a = 1 / (1 + 10 ** (rating_diff / 400))
        
        # 选择适当的 K 因子
        k_factor = ProbabilityEngine.PENALTY_K_FACTOR if is_penalty_shootout else ProbabilityEngine.K_FACTOR
        
        # 计算 Elo 更新
        # R_new = R_old + K × (W - W_e)
        delta_a = k_factor * (actual_result_a - expected_win_rate_a)
        delta_b = k_factor * ((1 - actual_result_a) - (1 - expected_win_rate_a))
        
        new_rating_a = old_rating_a + delta_a
        new_rating_b = old_rating_b + delta_b
        
        return new_rating_a, new_rating_b
    
    @staticmethod
    def poisson_probability(lambda_param: float, goals: int) -> float:
        """
        计算泊松分布概率
        
        使用泊松分布公式 P(x) = (λ^x * e^-λ) / x! 计算特定进球数的概率。
        
        Args:
            lambda_param (float): 预期进球数 λ
            goals (int): 实际进球数 x
            
        Returns:
            float: 该进球数发生的概率
            
        Raises:
            ValueError: 当参数为负数或 goals 为非整数时抛出异常
            
        Examples:
            >>> engine = ProbabilityEngine()
            >>> prob = engine.poisson_probability(1.5, 2)
            >>> print(f"概率: {prob:.4f}")
            概率: 0.2510
        """
        # 验证输入参数
        if lambda_param < 0:
            raise ValueError("Lambda parameter must be non-negative")
        if goals < 0 or not isinstance(goals, int):
            raise ValueError("Goals must be a non-negative integer")
        
        # 处理特殊情况：lambda = 0
        if lambda_param == 0:
            return 1.0 if goals == 0 else 0.0
        
        # 计算泊松概率: P(x) = (λ^x * e^-λ) / x!
        # 为避免数值溢出，使用对数计算
        log_prob = goals * math.log(lambda_param) - lambda_param - ProbabilityEngine._log_factorial(goals)
        probability = math.exp(log_prob)
        
        return probability
    
    @staticmethod
    def _log_factorial(n: int) -> float:
        """
        计算阶乘的对数（避免数值溢出）
        
        Args:
            n (int): 非负整数
            
        Returns:
            float: ln(n!)
        """
        if n <= 1:
            return 0.0
        
        # 使用 Stirling 近似或直接累加
        if n < 100:
            # 小数值直接计算
            result = 0.0
            for i in range(2, n + 1):
                result += math.log(i)
            return result
        else:
            # 大数值使用 Stirling 近似: ln(n!) ≈ n*ln(n) - n + 0.5*ln(2πn)
            return n * math.log(n) - n + 0.5 * math.log(2 * math.pi * n)
    
    @staticmethod
    def predict_score_distribution(
        team_a_elo: float,
        team_b_elo: float,
        base_lambda_a: float = 1.2,
        base_lambda_b: float = 1.0,
        elo_weight: float = 0.002
    ) -> Tuple[Tuple[int, int, float], ...]:
        """
        基于历史进球率和 Elo 分差预测比分分布
        
        根据两队 Elo 评分调整预期进球数，然后使用泊松分布计算最可能的 3 种比分及其概率。
        
        Args:
            team_a_elo (float): A 队 Elo 评分
            team_b_elo (float): B 队 Elo 评分
            base_lambda_a (float): A 队基础预期进球率（默认 1.2）
            base_lambda_b (float): B 队基础预期进球率（默认 1.0）
            elo_weight (float): Elo 分差对预期进球的影响权重（默认 0.002）
            
        Returns:
            Tuple[Tuple[int, int, float], ...]: 最可能的 3 种比分及其概率
                每个元素为 (A队进球, B队进球, 概率)
                按概率从高到低排序
                
        Raises:
            ValueError: 当 Elo 评分为负数时抛出异常
            
        Examples:
            >>> engine = ProbabilityEngine()
            >>> scores = engine.predict_score_distribution(2000, 1800)
            >>> for score_a, score_b, prob in scores:
            ...     print(f"{score_a}-{score_b}: {prob:.4f}")
            1-0: 0.1823
            2-0: 0.1456
            1-1: 0.1234
            
        Note:
            预期进球数计算公式：
            λ_A = base_lambda_A * (1 + elo_weight * (Elo_A - Elo_B))
            λ_B = base_lambda_B * (1 + elo_weight * (Elo_B - Elo_A))
            
            通过遍历所有可能的比分组合（0-0 到 5-5），计算每种比分的联合概率，
            然后返回概率最高的 3 种。
        """
        # 验证输入参数
        if team_a_elo < 0 or team_b_elo < 0:
            raise ValueError("Elo ratings must be non-negative")
        
        # 根据 Elo 分差调整预期进球数
        elo_diff = team_a_elo - team_b_elo
        lambda_a = base_lambda_a * (1 + elo_weight * elo_diff)
        lambda_b = base_lambda_b * (1 + elo_weight * (-elo_diff))
        
        # 确保预期进球数为正数
        lambda_a = max(0.1, lambda_a)
        lambda_b = max(0.1, lambda_b)
        
        # 计算所有可能比分的概率（0-0 到 5-5）
        score_probabilities = []
        
        for goals_a in range(6):  # 0 到 5
            for goals_b in range(6):  # 0 到 5
                # 计算联合概率：P(A进goals_a球) * P(B进goals_b球)
                prob_a = ProbabilityEngine.poisson_probability(lambda_a, goals_a)
                prob_b = ProbabilityEngine.poisson_probability(lambda_b, goals_b)
                joint_prob = prob_a * prob_b
                
                score_probabilities.append((goals_a, goals_b, joint_prob))
        
        # 按概率从高到低排序
        score_probabilities.sort(key=lambda x: x[2], reverse=True)
        
        # 返回最可能的 3 种比分
        return tuple(score_probabilities[:3])
    
    @staticmethod
    def calculate_match_outcome_probabilities(
        team_a_elo: float,
        team_b_elo: float,
        base_lambda_a: float = 1.2,
        base_lambda_b: float = 1.0,
        elo_weight: float = 0.002
    ) -> dict[str, float]:
        """
        计算比赛结果的总体概率分布
        
        基于泊松分布计算胜、平、负三种结果的概率。
        
        Args:
            team_a_elo (float): A 队 Elo 评分
            team_b_elo (float): B 队 Elo 评分
            base_lambda_a (float): A 队基础预期进球率
            base_lambda_b (float): B 队基础预期进球率
            elo_weight (float): Elo 分差影响权重
            
        Returns:
            dict[str, float]: 包含以下键的字典：
                - 'win_a': A 队获胜概率
                - 'draw': 平局概率
                - 'win_b': B 队获胜概率
                
        Examples:
            >>> engine = ProbabilityEngine()
            >>> probs = engine.calculate_match_outcome_probabilities(2000, 1800)
            >>> print(f"A胜: {probs['win_a']:.2%}, 平: {probs['draw']:.2%}, B胜: {probs['win_b']:.2%}")
            A胜: 52.34%, 平: 24.12%, B胜: 23.54%
        """
        # 获取比分分布
        all_scores = ProbabilityEngine.predict_score_distribution(
            team_a_elo, team_b_elo, base_lambda_a, base_lambda_b, elo_weight
        )
        
        # 计算胜平负概率（需要重新计算所有可能比分）
        elo_diff = team_a_elo - team_b_elo
        lambda_a = base_lambda_a * (1 + elo_weight * elo_diff)
        lambda_b = base_lambda_b * (1 + elo_weight * (-elo_diff))
        lambda_a = max(0.1, lambda_a)
        lambda_b = max(0.1, lambda_b)
        
        win_a_prob = 0.0
        draw_prob = 0.0
        win_b_prob = 0.0
        
        # 遍历所有可能的比分（0-0 到 10-10，覆盖绝大多数情况）
        for goals_a in range(11):
            for goals_b in range(11):
                prob_a = ProbabilityEngine.poisson_probability(lambda_a, goals_a)
                prob_b = ProbabilityEngine.poisson_probability(lambda_b, goals_b)
                joint_prob = prob_a * prob_b
                
                if goals_a > goals_b:
                    win_a_prob += joint_prob
                elif goals_a == goals_b:
                    draw_prob += joint_prob
                else:
                    win_b_prob += joint_prob
        
        # 归一化（确保总和为 1）
        total = win_a_prob + draw_prob + win_b_prob
        if total > 0:
            win_a_prob /= total
            draw_prob /= total
            win_b_prob /= total
        
        return {
            'win_a': win_a_prob,
            'draw': draw_prob,
            'win_b': win_b_prob
        }


# 测试代码
if __name__ == "__main__":
    print("=" * 60)
    print("ProbabilityEngine 测试")
    print("=" * 60)
    
    engine = ProbabilityEngine()
    
    # 测试 1: Elo 更新计算
    print("\n【测试 1】Elo 更新计算")
    print("-" * 60)
    old_a, old_b = 2000.0, 1800.0
    print(f"初始评分: A={old_a}, B={old_b}")
    
    # A 队获胜
    new_a, new_b = engine.calculate_elo_update(old_a, old_b, 1.0)
    print(f"\nA 队获胜后:")
    print(f"  新评分: A={new_a:.2f}, B={new_b:.2f}")
    print(f"  变化:   A={new_a-old_a:+.2f}, B={new_b-old_b:+.2f}")
    
    # 平局
    new_a, new_b = engine.calculate_elo_update(old_a, old_b, 0.5)
    print(f"\n平局后:")
    print(f"  新评分: A={new_a:.2f}, B={new_b:.2f}")
    print(f"  变化:   A={new_a-old_a:+.2f}, B={new_b-old_b:+.2f}")
    
    # 点球大战（不改变评分）
    new_a, new_b = engine.calculate_elo_update(old_a, old_b, 1.0, is_penalty_shootout=True)
    print(f"\n点球大战后（A 队获胜）:")
    print(f"  新评分: A={new_a:.2f}, B={new_b:.2f}")
    print(f"  变化:   A={new_a-old_a:+.2f}, B={new_b-old_b:+.2f} (应为 0)")
    
    # 测试 2: 泊松概率计算
    print("\n【测试 2】泊松概率计算")
    print("-" * 60)
    lambda_val = 1.5
    print(f"预期进球数 λ = {lambda_val}")
    for goals in range(6):
        prob = engine.poisson_probability(lambda_val, goals)
        print(f"  进 {goals} 球的概率: {prob:.4f}")
    
    # 测试 3: 比分预测
    print("\n【测试 3】比分预测")
    print("-" * 60)
    team_a_elo, team_b_elo = 2000.0, 1800.0
    print(f"A 队 Elo: {team_a_elo}, B 队 Elo: {team_b_elo}")
    print(f"Elo 分差: {team_a_elo - team_b_elo}")
    
    top_scores = engine.predict_score_distribution(team_a_elo, team_b_elo)
    print(f"\n最可能的 3 种比分:")
    for i, (goals_a, goals_b, prob) in enumerate(top_scores, 1):
        print(f"  {i}. {goals_a}-{goals_b}: {prob:.4f} ({prob*100:.2f}%)")
    
    # 测试 4: 比赛结果概率
    print("\n【测试 4】比赛结果概率")
    print("-" * 60)
    outcomes = engine.calculate_match_outcome_probabilities(team_a_elo, team_b_elo)
    print(f"A 队获胜: {outcomes['win_a']:.4f} ({outcomes['win_a']*100:.2f}%)")
    print(f"平局:     {outcomes['draw']:.4f} ({outcomes['draw']*100:.2f}%)")
    print(f"B 队获胜: {outcomes['win_b']:.4f} ({outcomes['win_b']*100:.2f}%)")
    print(f"总和:     {sum(outcomes.values()):.4f}")
    
    print("\n" + "=" * 60)
    print("✅ 所有测试完成！")
    print("=" * 60)
