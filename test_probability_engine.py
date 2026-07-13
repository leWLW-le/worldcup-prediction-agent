"""
ProbabilityEngine 单元测试

测试概率预测引擎的核心功能。
"""

import unittest
from app.services.probability_engine import ProbabilityEngine


class TestProbabilityEngine(unittest.TestCase):
    """ProbabilityEngine 测试类"""
    
    def setUp(self):
        """设置测试环境"""
        self.engine = ProbabilityEngine()
    
    # ==================== Elo 更新测试 ====================
    
    def test_elo_update_win_stronger_team(self):
        """测试强队获胜时的 Elo 更新"""
        old_a, old_b = 2000.0, 1800.0
        new_a, new_b = self.engine.calculate_elo_update(old_a, old_b, 1.0)
        
        # A 队应该获得分数，B 队应该失去分数
        self.assertGreater(new_a, old_a)
        self.assertLess(new_b, old_b)
        
        # 总分应该保持不变
        self.assertAlmostEqual(old_a + old_b, new_a + new_b, places=5)
    
    def test_elo_update_draw(self):
        """测试平局时的 Elo 更新"""
        old_a, old_b = 2000.0, 1800.0
        new_a, new_b = self.engine.calculate_elo_update(old_a, old_b, 0.5)
        
        # 弱队应该获得分数（因为平局对弱队更有利）
        self.assertLess(new_a, old_a)
        self.assertGreater(new_b, old_b)
    
    def test_elo_update_penalty_shootout(self):
        """测试点球大战不改变 Elo 评分"""
        old_a, old_b = 2000.0, 1800.0
        new_a, new_b = self.engine.calculate_elo_update(
            old_a, old_b, 1.0, is_penalty_shootout=True
        )
        
        # 点球大战不应该改变评分
        self.assertEqual(new_a, old_a)
        self.assertEqual(new_b, old_b)
    
    def test_elo_update_invalid_result(self):
        """测试无效的实际结果应抛出异常"""
        with self.assertRaises(ValueError):
            self.engine.calculate_elo_update(2000.0, 1800.0, 1.5)
        
        with self.assertRaises(ValueError):
            self.engine.calculate_elo_update(2000.0, 1800.0, -0.1)
    
    def test_elo_expected_win_rate_calculation(self):
        """测试期望胜率计算的正确性"""
        # 当两队评分相同时，期望胜率应为 0.5
        new_a, new_b = self.engine.calculate_elo_update(1800.0, 1800.0, 0.5)
        # 平局时，如果期望胜率是 0.5，则实际结果也是 0.5，评分不应变化
        self.assertAlmostEqual(new_a, 1800.0, places=5)
        self.assertAlmostEqual(new_b, 1800.0, places=5)
    
    # ==================== 泊松分布测试 ====================
    
    def test_poisson_probability_sum_to_one(self):
        """测试泊松分布在所有可能值上的概率和接近 1"""
        lambda_val = 1.5
        total_prob = sum(
            self.engine.poisson_probability(lambda_val, k) 
            for k in range(20)
        )
        # 前 20 个值的概率和应该非常接近 1
        self.assertAlmostEqual(total_prob, 1.0, places=3)
    
    def test_poisson_probability_zero_lambda(self):
        """测试 lambda=0 时的边界情况"""
        # lambda=0 时，只有 0 球的概率为 1
        self.assertEqual(self.engine.poisson_probability(0.0, 0), 1.0)
        self.assertEqual(self.engine.poisson_probability(0.0, 1), 0.0)
        self.assertEqual(self.engine.poisson_probability(0.0, 5), 0.0)
    
    def test_poisson_probability_invalid_params(self):
        """测试无效参数应抛出异常"""
        with self.assertRaises(ValueError):
            self.engine.poisson_probability(-1.0, 2)
        
        with self.assertRaises(ValueError):
            self.engine.poisson_probability(1.5, -1)
    
    def test_poisson_probability_most_likely_value(self):
        """测试最可能的进球数接近 lambda"""
        # 对于整数 lambda，最可能的值是 lambda 和 lambda-1
        # 这里测试 lambda=4，最可能的值应该是 4
        lambda_val = 4.0
        probs = {
            k: self.engine.poisson_probability(lambda_val, k) 
            for k in range(10)
        }
        most_likely = max(probs, key=probs.get)
        # 允许最可能值在 [lambda-1, lambda] 范围内
        self.assertIn(most_likely, [3, 4])
    
    # ==================== 比分预测测试 ====================
    
    def test_predict_score_distribution_returns_three(self):
        """测试返回恰好 3 种比分"""
        scores = self.engine.predict_score_distribution(2000.0, 1800.0)
        self.assertEqual(len(scores), 3)
    
    def test_predict_score_distribution_sorted(self):
        """测试比分按概率从高到低排序"""
        scores = self.engine.predict_score_distribution(2000.0, 1800.0)
        probs = [score[2] for score in scores]
        self.assertEqual(probs, sorted(probs, reverse=True))
    
    def test_predict_score_distribution_probabilities_sum(self):
        """测试返回的比分概率合理"""
        scores = self.engine.predict_score_distribution(2000.0, 1800.0)
        # 每个概率应该在 0 到 1 之间
        for _, _, prob in scores:
            self.assertGreater(prob, 0)
            self.assertLessEqual(prob, 1)
    
    def test_predict_score_distribution_higher_elo_advantage(self):
        """测试高 Elo 队伍更可能获胜"""
        scores = self.engine.predict_score_distribution(2000.0, 1500.0)
        # 第一个比分应该是 A 队领先
        self.assertGreater(scores[0][0], scores[0][1])
    
    def test_predict_score_distribution_invalid_elo(self):
        """测试无效 Elo 评分应抛出异常"""
        with self.assertRaises(ValueError):
            self.engine.predict_score_distribution(-100.0, 1800.0)
    
    # ==================== 比赛结果概率测试 ====================
    
    def test_match_outcome_probabilities_sum_to_one(self):
        """测试胜平负概率和为 1"""
        outcomes = self.engine.calculate_match_outcome_probabilities(2000.0, 1800.0)
        total = sum(outcomes.values())
        self.assertAlmostEqual(total, 1.0, places=5)
    
    def test_match_outcome_all_positive(self):
        """测试所有概率都为正数"""
        outcomes = self.engine.calculate_match_outcome_probabilities(2000.0, 1800.0)
        for prob in outcomes.values():
            self.assertGreater(prob, 0)
    
    def test_match_outcome_keys_exist(self):
        """测试返回的字典包含正确的键"""
        outcomes = self.engine.calculate_match_outcome_probabilities(2000.0, 1800.0)
        self.assertIn('win_a', outcomes)
        self.assertIn('draw', outcomes)
        self.assertIn('win_b', outcomes)
    
    def test_match_outcome_equal_teams(self):
        """测试实力相当的队伍胜平负概率接近均等"""
        outcomes = self.engine.calculate_match_outcome_probabilities(1800.0, 1800.0)
        # 平局概率应该相对较高
        self.assertGreater(outcomes['draw'], 0.2)
        # 胜负概率应该比较接近（允许一定误差）
        self.assertAlmostEqual(outcomes['win_a'], outcomes['win_b'], places=0)
    
    def test_match_outcome_elo_advantage(self):
        """测试高 Elo 队伍获胜概率更高"""
        outcomes = self.engine.calculate_match_outcome_probabilities(2000.0, 1500.0)
        # A 队获胜概率应该最高
        self.assertGreater(outcomes['win_a'], outcomes['draw'])
        self.assertGreater(outcomes['win_a'], outcomes['win_b'])
    
    # ==================== 综合测试 ====================
    
    def test_consistency_between_methods(self):
        """测试不同方法之间的一致性"""
        team_a_elo, team_b_elo = 2000.0, 1800.0
        
        # 获取比分分布
        scores = self.engine.predict_score_distribution(team_a_elo, team_b_elo)
        
        # 获取胜平负概率
        outcomes = self.engine.calculate_match_outcome_probabilities(team_a_elo, team_b_elo)
        
        # 从比分分布推断 A 队获胜概率（粗略估计）
        win_a_from_scores = sum(prob for a, b, prob in scores if a > b)
        
        # 两者应该有一定的相关性（虽然不完全相等）
        # 这里只是做一个合理性检查
        self.assertGreater(win_a_from_scores, 0)
    
    def test_realistic_scenario(self):
        """测试真实场景：巴西 vs 德国"""
        brazil_elo = 2100.0
        germany_elo = 2000.0
        
        # Elo 更新
        new_brazil, new_germany = self.engine.calculate_elo_update(
            brazil_elo, germany_elo, 1.0
        )
        self.assertGreater(new_brazil, brazil_elo)
        
        # 比分预测
        scores = self.engine.predict_score_distribution(brazil_elo, germany_elo)
        self.assertEqual(len(scores), 3)
        
        # 胜平负概率
        outcomes = self.engine.calculate_match_outcome_probabilities(brazil_elo, germany_elo)
        self.assertAlmostEqual(sum(outcomes.values()), 1.0, places=5)
        # 巴西作为更强的队伍，获胜概率应该更高
        self.assertGreater(outcomes['win_a'], outcomes['win_b'])


if __name__ == '__main__':
    print("=" * 70)
    print("运行 ProbabilityEngine 单元测试")
    print("=" * 70)
    unittest.main(verbosity=2)
