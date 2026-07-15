"""
基于 PyTorch 的注意力特征加权网络模块

提供轻量级的深度学习特征融合能力，用于增强传统 Elo 评分系统的预测准确度。
该模块通过注意力机制动态评估不同特征对比赛结果的影响权重。
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, Tuple

# 显式使用 CPU 设备（部署环境无 GPU）
DEVICE = torch.device("cpu")


class FeatureAttentionMixer(nn.Module):
    """
    特征注意力混合器
    
    使用多层感知机（MLP）结合注意力机制，对两支球队的多维特征进行加权融合，
    输出一个调整系数用于修正基础的 Elo 胜率预测。
    
    Architecture:
        Input (8 features) → MLP Layer 1 (64) → ReLU → Dropout
                          → MLP Layer 2 (32) → ReLU → Dropout
                          → Attention Layer (16) → Softmax
                          → Output Layer (1) → Tanh → Adjustment (-0.1 to +0.1)
    
    Input Features (per team pair):
        - elo_diff: Elo 分差 (A队 - B队)
        - value_diff: 核心球员身价总和差值 (百万欧元)
        - form_diff: 近期胜率差值 (最近5场)
        - injury_diff: 伤病折损率差值 (0-1)
    
    Output:
        adjustment: 调整系数，范围 [-0.1, +0.1]
            - 正值表示 A 队优势增强
            - 负值表示 B 队优势增强
    
    Attributes:
        input_dim (int): 输入特征维度（默认 8，每队 4 个特征）
        hidden_dim_1 (int): 第一层隐藏层维度
        hidden_dim_2 (int): 第二层隐藏层维度
        attention_dim (int): 注意力层维度
        dropout_rate (float): Dropout 比率
    """
    
    def __init__(
        self,
        input_dim: int = 8,
        hidden_dim_1: int = 64,
        hidden_dim_2: int = 32,
        attention_dim: int = 16,
        dropout_rate: float = 0.3
    ):
        """
        初始化特征注意力混合器
        
        Args:
            input_dim: 输入特征维度（两队特征拼接后的总维度）
            hidden_dim_1: 第一层隐藏层神经元数量
            hidden_dim_2: 第二层隐藏层神经元数量
            attention_dim: 注意力机制的维度
            dropout_rate: Dropout 正则化比率（0-1）
        """
        super(FeatureAttentionMixer, self).__init__()
        
        # 保存配置参数
        self.input_dim = input_dim
        self.hidden_dim_1 = hidden_dim_1
        self.hidden_dim_2 = hidden_dim_2
        self.attention_dim = attention_dim
        self.dropout_rate = dropout_rate
        
        # 第一层 MLP: input_dim → hidden_dim_1
        self.fc1 = nn.Linear(input_dim, hidden_dim_1)
        self.bn1 = nn.BatchNorm1d(hidden_dim_1)
        self.dropout1 = nn.Dropout(dropout_rate)
        
        # 第二层 MLP: hidden_dim_1 → hidden_dim_2
        self.fc2 = nn.Linear(hidden_dim_1, hidden_dim_2)
        self.bn2 = nn.BatchNorm1d(hidden_dim_2)
        self.dropout2 = nn.Dropout(dropout_rate)
        
        # 注意力层: hidden_dim_2 → attention_dim
        self.attention_fc = nn.Linear(hidden_dim_2, attention_dim)
        self.attention_weight = nn.Linear(attention_dim, 1)
        
        # 输出层: hidden_dim_2 → 1
        self.output_fc = nn.Linear(hidden_dim_2, 1)
        
        # 初始化权重
        self._initialize_weights()
    
    def _initialize_weights(self):
        """
        使用 Kaiming 初始化方法初始化网络权重
        
        这有助于加速训练收敛并避免梯度消失/爆炸问题。
        """
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.kaiming_normal_(m.weight, mode='fan_in', nonlinearity='relu')
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)
    
    def forward(self, team_a_features: torch.Tensor, team_b_features: torch.Tensor) -> torch.Tensor:
        """
        前向传播
        
        Args:
            team_a_features: A 队特征向量，形状为 (batch_size, 4)
                包含: [elo_rating, player_value, recent_form, injury_rate]
            team_b_features: B 队特征向量，形状为 (batch_size, 4)
                包含: [elo_rating, player_value, recent_form, injury_rate]
        
        Returns:
            torch.Tensor: 调整系数，形状为 (batch_size, 1)，范围 [-0.1, +0.1]
        
        Examples:
            >>> model = FeatureAttentionMixer()
            >>> # 模拟批量数据（batch_size=2）
            >>> team_a = torch.tensor([[2000.0, 500.0, 0.8, 0.1],
            ...                        [1900.0, 450.0, 0.6, 0.2]])
            >>> team_b = torch.tensor([[1800.0, 400.0, 0.6, 0.15],
            ...                        [1850.0, 420.0, 0.7, 0.1]])
            >>> adjustment = model(team_a, team_b)
            >>> print(adjustment.shape)  # torch.Size([2, 1])
            >>> print(adjustment)  # 值在 [-0.1, +0.1] 范围内
        """
        # 计算特征差值（A队 - B队）
        feature_diff = team_a_features - team_b_features  # (batch_size, 4)
        
        # 拼接原始特征和差值特征
        combined_features = torch.cat([team_a_features, team_b_features, feature_diff], dim=1)
        # 实际输入维度: 4 + 4 + 4 = 12（如果 input_dim=8，则只取前8维）
        if combined_features.shape[1] > self.input_dim:
            combined_features = combined_features[:, :self.input_dim]
        
        # 第一层 MLP + BatchNorm + ReLU + Dropout
        x = self.fc1(combined_features)
        x = self.bn1(x)
        x = F.relu(x)
        x = self.dropout1(x)
        
        # 第二层 MLP + BatchNorm + ReLU + Dropout
        x = self.fc2(x)
        x = self.bn2(x)
        x = F.relu(x)
        x = self.dropout2(x)
        
        # 注意力机制
        # Step 1: 投影到注意力空间
        attention_input = self.attention_fc(x)  # (batch_size, attention_dim)
        attention_input = F.relu(attention_input)
        
        # Step 2: 计算注意力权重
        attention_scores = self.attention_weight(attention_input)  # (batch_size, 1)
        attention_weights = F.softmax(attention_scores, dim=1)  # (batch_size, 1)
        
        # Step 3: 应用注意力权重到特征上
        attended_features = x * attention_weights  # (batch_size, hidden_dim_2)
        
        # 输出层
        output = self.output_fc(attended_features)  # (batch_size, 1)
        
        # 使用 Tanh 激活函数将输出限制在 [-1, 1] 范围
        output = torch.tanh(output)
        
        # 缩放到 [-0.1, +0.1] 范围
        adjustment = output * 0.1
        
        return adjustment
    
    def get_attention_weights(
        self,
        team_a_features: torch.Tensor,
        team_b_features: torch.Tensor
    ) -> torch.Tensor:
        """
        获取注意力权重（用于可解释性分析）
        
        Args:
            team_a_features: A 队特征向量
            team_b_features: B 队特征向量
        
        Returns:
            torch.Tensor: 注意力权重，形状为 (batch_size, attention_dim)
        """
        feature_diff = team_a_features - team_b_features
        combined_features = torch.cat([team_a_features, team_b_features, feature_diff], dim=1)
        if combined_features.shape[1] > self.input_dim:
            combined_features = combined_features[:, :self.input_dim]
        
        # 前向传播到注意力层
        x = self.fc1(combined_features)
        x = self.bn1(x)
        x = F.relu(x)
        x = self.dropout1(x)
        
        x = self.fc2(x)
        x = self.bn2(x)
        x = F.relu(x)
        x = self.dropout2(x)
        
        # 计算注意力权重
        attention_input = self.attention_fc(x)
        attention_input = F.relu(attention_input)
        attention_weights = F.softmax(self.attention_weight(attention_input), dim=1)
        
        return attention_weights


class FeatureAttentionMixerV2(nn.Module):
    """
    V2 特征注意力混合器 — 扩展特征版本

    接受 67 维组合特征 (25 home + 25 away + 17 diff)，
    截断到 input_dim=50，输出三分类 logits (home_win, draw, away_win)。

    Architecture:
        Combined Features (67) → truncate → (50)
        → FC1 (50→128) → BN → ReLU → Dropout
        → FC2 (128→64) → BN → ReLU → Dropout
        → Attention (64→16) → Softmax weighting
        → Output (64→3)
    """

    # 每队 25 个特征（从 MatchFeatureBuilder.TEAM_FEATURE_COLS 中选取）
    TEAM_FEATURE_NAMES = [
        'elo_rating', 'elo_change_1year', 'elo_change_3year',
        'world_cup_experience', 'major_tournament_points',
        'wins_5', 'draws_5', 'losses_5',
        'goals_for_5', 'goals_against_5', 'win_rate_5',
        'wins_10', 'draws_10', 'losses_10',
        'goals_for_10', 'goals_against_10', 'win_rate_10',
        'attack_score', 'avg_goals_scored', 'shots_estimate',
        'big_win_rate', 'scoring_consistency',
        'defense_score', 'avg_goals_conceded', 'clean_sheet_rate',
    ]

    # 差值特征名（17个，用于 combined 向量中的 diff 部分）
    DIFF_FEATURE_NAMES = [
        'elo_rating', 'elo_change_1year', 'elo_change_3year',
        'world_cup_experience', 'major_tournament_points',
        'wins_5', 'draws_5', 'losses_5',
        'goals_for_5', 'goals_against_5', 'win_rate_5',
        'wins_10', 'draws_10', 'losses_10',
        'goals_for_10', 'goals_against_10', 'win_rate_10',
    ]

    def __init__(
        self,
        team_dim: int = 25,
        input_dim: int = 50,
        hidden_dim_1: int = 128,
        hidden_dim_2: int = 64,
        attention_dim: int = 16,
        dropout_rate: float = 0.4
    ):
        super(FeatureAttentionMixerV2, self).__init__()

        self.team_dim = team_dim
        self.input_dim = input_dim
        self.hidden_dim_1 = hidden_dim_1
        self.hidden_dim_2 = hidden_dim_2
        self.attention_dim = attention_dim
        self.dropout_rate = dropout_rate

        # 组合向量: [home(25), away(25), diff(17)] = 67, 截断到 input_dim
        combined_dim = team_dim * 2 + 17  # 67

        self.fc1 = nn.Linear(min(combined_dim, input_dim), hidden_dim_1)
        self.bn1 = nn.BatchNorm1d(hidden_dim_1)
        self.dropout1 = nn.Dropout(dropout_rate)

        self.fc2 = nn.Linear(hidden_dim_1, hidden_dim_2)
        self.bn2 = nn.BatchNorm1d(hidden_dim_2)
        self.dropout2 = nn.Dropout(dropout_rate)

        # 注意力层
        self.attention_fc = nn.Linear(hidden_dim_2, attention_dim)
        self.attention_weight = nn.Linear(attention_dim, 1)

        # 输出层: 三分类 logits
        self.output_fc = nn.Linear(hidden_dim_2, 3)

        self._initialize_weights()

    def _initialize_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.kaiming_normal_(m.weight, mode='fan_in', nonlinearity='relu')
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)

    def forward(self, combined_features: torch.Tensor) -> torch.Tensor:
        """
        前向传播

        Args:
            combined_features: 组合特征 (batch, 67) = [home(25), away(25), diff(17)]

        Returns:
            logits: (batch, 3) — [home_win, draw, away_win] 未归一化的 logits
        """
        # 截断到 input_dim
        x = combined_features
        if x.shape[1] > self.input_dim:
            x = x[:, :self.input_dim]

        # Layer 1
        x = self.fc1(x)
        x = self.bn1(x)
        x = F.relu(x)
        x = self.dropout1(x)

        # Layer 2
        x = self.fc2(x)
        x = self.bn2(x)
        x = F.relu(x)
        x = self.dropout2(x)

        # Attention
        attn = self.attention_fc(x)
        attn = F.relu(attn)
        attn = self.attention_weight(attn)
        attn = F.softmax(attn, dim=1)
        x = x * attn

        # Output: 3-class logits
        logits = self.output_fc(x)
        return logits


def verify_checkpoint_compatibility(checkpoint, model_class, **model_kwargs) -> dict:
    """
    探测 checkpoint 架构并与目标模型类对比，验证兼容性。

    Args:
        checkpoint: torch.load 返回的对象（state_dict 或含 state_dict 的 dict）
        model_class: 目标模型类（如 FeatureAttentionMixerV2）
        **model_kwargs: 传给模型类构造函数的参数

    Returns:
        dict: {
            "compatible": bool,
            "checkpoint_keys": list,
            "model_keys": list,
            "missing_keys": list,      # 模型有但 checkpoint 没有
            "unexpected_keys": list,   # checkpoint 有但模型没有
            "shape_mismatches": list,  # key 相同但 shape 不同
            "mismatches": str,         # 汇总描述
            "total_params": int,       # checkpoint 总参数数
        }
    """
    # 提取 state_dict
    if isinstance(checkpoint, dict):
        if "state_dict" in checkpoint:
            sd_ckpt = checkpoint["state_dict"]
        elif "model_state_dict" in checkpoint:
            sd_ckpt = checkpoint["model_state_dict"]
        else:
            sd_ckpt = checkpoint
    else:
        sd_ckpt = checkpoint.state_dict()

    # 实例化目标模型
    model = model_class(**model_kwargs)
    sd_model = model.state_dict()

    ckpt_keys = set(sd_ckpt.keys())
    model_keys = set(sd_model.keys())

    missing = sorted(model_keys - ckpt_keys)
    unexpected = sorted(ckpt_keys - model_keys)

    # 检查 shape 匹配
    shape_mismatches = []
    common = sorted(ckpt_keys & model_keys)
    for k in common:
        ckpt_shape = tuple(sd_ckpt[k].shape)
        model_shape = tuple(sd_model[k].shape)
        if ckpt_shape != model_shape:
            shape_mismatches.append(f"{k}: checkpoint={ckpt_shape} vs model={model_shape}")

    total_params = sum(v.numel() for v in sd_ckpt.values())
    compatible = len(missing) == 0 and len(unexpected) == 0 and len(shape_mismatches) == 0

    mismatches_parts = []
    if missing:
        mismatches_parts.append(f"missing_keys={missing}")
    if unexpected:
        mismatches_parts.append(f"unexpected_keys={unexpected}")
    if shape_mismatches:
        mismatches_parts.append(f"shape_mismatches={shape_mismatches}")

    return {
        "compatible": compatible,
        "checkpoint_keys": sorted(ckpt_keys),
        "model_keys": sorted(model_keys),
        "missing_keys": missing,
        "unexpected_keys": unexpected,
        "shape_mismatches": shape_mismatches,
        "mismatches": "; ".join(mismatches_parts) if mismatches_parts else "none",
        "total_params": total_params,
    }


class FocalLoss(nn.Module):
    """
    Focal Loss — 解决类别不平衡问题
    降低易分类样本的权重，聚焦于难分类样本
    """

    def __init__(self, alpha=None, gamma=2.0, reduction='mean'):
        super(FocalLoss, self).__init__()
        self.gamma = gamma
        self.reduction = reduction
        self.alpha = alpha  # optional per-class weight tensor

    def forward(self, logits, targets):
        ce_loss = F.cross_entropy(logits, targets, reduction='none')
        pt = torch.exp(-ce_loss)
        focal_loss = ((1 - pt) ** self.gamma) * ce_loss

        if self.alpha is not None:
            alpha_t = self.alpha.gather(0, targets)
            focal_loss = alpha_t * focal_loss

        if self.reduction == 'mean':
            return focal_loss.mean()
        elif self.reduction == 'sum':
            return focal_loss.sum()
        return focal_loss


def build_combined_tensor(home_feats_df, away_feats_df, diff_feats_df):
    """
    从 home/away/diff 三个 DataFrame 构建 combined tensor

    combined = [home(25), away(25), diff(17)] = 67 维

    Args:
        home_feats_df: DataFrame of home team features (n, 25)
        away_feats_df: DataFrame of away team features (n, 25)
        diff_feats_df: DataFrame of diff features (n, 17)

    Returns:
        torch.Tensor (n, 67)
    """
    import pandas as pd

    home_vals = torch.tensor(home_feats_df.values, dtype=torch.float32)
    away_vals = torch.tensor(away_feats_df.values, dtype=torch.float32)
    diff_vals = torch.tensor(diff_feats_df.values, dtype=torch.float32)

    combined = torch.cat([home_vals, away_vals, diff_vals], dim=1)
    return combined


# ============================================================
# 以下为原始测试代码（保持不变）
# ============================================================

def normalize_features(features_dict: Dict[str, float]) -> torch.Tensor:
    """
    将特征字典归一化为张量
    
    Args:
        features_dict: 包含以下键的字典：
            - elo_rating: Elo 评分（通常 1000-2500）
            - player_value: 核心球员身价总和（百万欧元，通常 100-1000）
            - recent_form: 近期胜率（0-1，最近5场胜率）
            - injury_rate: 伤病折损率（0-1，0表示无伤病，1表示全部主力受伤）
    
    Returns:
        torch.Tensor: 归一化后的特征向量，形状为 (1, 4)
    
    Examples:
        >>> features = {
        ...     'elo_rating': 2000.0,
        ...     'player_value': 500.0,
        ...     'recent_form': 0.8,
        ...     'injury_rate': 0.1
        ... }
        >>> tensor = normalize_features(features)
        >>> print(tensor.shape)  # torch.Size([1, 4])
    """
    # 定义归一化参数（基于历史数据统计）
    normalization_params = {
        'elo_rating': {'mean': 1700.0, 'std': 300.0},
        'player_value': {'mean': 400.0, 'std': 200.0},
        'recent_form': {'mean': 0.5, 'std': 0.2},
        'injury_rate': {'mean': 0.15, 'std': 0.1}
    }
    
    # 提取特征值
    raw_features = [
        features_dict['elo_rating'],
        features_dict['player_value'],
        features_dict['recent_form'],
        features_dict['injury_rate']
    ]
    
    # Z-score 归一化
    normalized = []
    for i, value in enumerate(raw_features):
        param_key = list(normalization_params.keys())[i]
        mean = normalization_params[param_key]['mean']
        std = normalization_params[param_key]['std']
        normalized_value = (value - mean) / std
        normalized.append(normalized_value)
    
    # 转换为张量
    return torch.tensor([normalized], dtype=torch.float32)


def integrate_with_probability_engine(
    engine,
    team_a_elo: float,
    team_b_elo: float,
    team_a_features: Dict[str, float],
    team_b_features: Dict[str, float],
    model: FeatureAttentionMixer,
    base_win_prob_a: float
) -> float:
    """
    将注意力网络的输出与 ProbabilityEngine 结合
    
    使用注意力模型输出的调整系数修正基础的 Elo 胜率预测。
    
    Args:
        engine: ProbabilityEngine 实例
        team_a_elo: A 队 Elo 评分
        team_b_elo: B 队 Elo 评分
        team_a_features: A 队完整特征字典
        team_b_features: B 队完整特征字典
        model: 训练好的 FeatureAttentionMixer 模型
        base_win_prob_a: 基础 A 队胜率（来自 ProbabilityEngine）
    
    Returns:
        float: 调整后的 A 队胜率
    
    Examples:
        >>> from app.services.probability_engine import ProbabilityEngine
        >>> 
        >>> # 初始化引擎和模型
        >>> engine = ProbabilityEngine()
        >>> model = FeatureAttentionMixer()
        >>> model.eval()  # 设置为评估模式
        >>> 
        >>> # 准备特征
        >>> team_a_features = {
        ...     'elo_rating': 2000.0,
        ...     'player_value': 500.0,
        ...     'recent_form': 0.8,
        ...     'injury_rate': 0.1
        ... }
        >>> team_b_features = {
        ...     'elo_rating': 1800.0,
        ...     'player_value': 400.0,
        ...     'recent_form': 0.6,
        ...     'injury_rate': 0.15
        ... }
        >>> 
        >>> # 获取基础胜率
        >>> outcomes = engine.calculate_match_outcome_probabilities(2000.0, 1800.0)
        >>> base_win_prob_a = outcomes['win_a']
        >>> 
        >>> # 应用注意力调整
        >>> adjusted_prob = integrate_with_probability_engine(
        ...     engine, 2000.0, 1800.0,
        ...     team_a_features, team_b_features,
        ...     model, base_win_prob_a
        ... )
        >>> print(f"基础胜率: {base_win_prob_a:.4f}")
        >>> print(f"调整后胜率: {adjusted_prob:.4f}")
    """
    # 确保模型处于评估模式
    model.eval()
    
    # 归一化特征
    team_a_tensor = normalize_features(team_a_features)
    team_b_tensor = normalize_features(team_b_features)
    
    # 禁用梯度计算（推理阶段）
    with torch.inference_mode():
        # 获取调整系数
        adjustment = model(team_a_tensor, team_b_tensor)
        adjustment_value = adjustment.item()  # 转换为 Python 浮点数
    
    # 应用调整：调整系数影响胜率
    # adjustment 范围: [-0.1, +0.1]
    # 正值增加 A 队胜率，负值减少 A 队胜率
    adjusted_win_prob_a = base_win_prob_a + adjustment_value
    
    # 确保概率在合理范围内 [0.05, 0.95]
    adjusted_win_prob_a = max(0.05, min(0.95, adjusted_win_prob_a))
    
    return adjusted_win_prob_a


# 测试代码
if __name__ == "__main__":
    print("=" * 70)
    print("FeatureAttentionMixer 测试")
    print("=" * 70)
    
    # 测试 1: 模型初始化和前向传播
    print("\n【测试 1】模型初始化和前向传播")
    print("-" * 70)
    
    model = FeatureAttentionMixer()
    print(f"模型结构:")
    print(model)
    print(f"\n模型参数量: {sum(p.numel() for p in model.parameters()):,}")
    
    # 模拟批量数据
    batch_size = 3
    team_a_features = torch.tensor([
        [2000.0, 500.0, 0.8, 0.1],   # 强队：高Elo、高身价、状态好、伤病少
        [1900.0, 450.0, 0.6, 0.2],   # 中等队
        [1700.0, 350.0, 0.5, 0.15]   # 弱队
    ])
    team_b_features = torch.tensor([
        [1800.0, 400.0, 0.6, 0.15],  # 对手1
        [1850.0, 420.0, 0.7, 0.1],   # 对手2
        [1750.0, 380.0, 0.55, 0.12]  # 对手3
    ])
    
    print(f"\n输入形状: A={team_a_features.shape}, B={team_b_features.shape}")
    
    # 前向传播
    adjustments = model(team_a_features, team_b_features)
    print(f"输出形状: {adjustments.shape}")
    print(f"调整系数:")
    for i in range(batch_size):
        print(f"  比赛 {i+1}: {adjustments[i].item():+.4f}")
    
    # 测试 2: 特征归一化
    print("\n【测试 2】特征归一化")
    print("-" * 70)
    
    test_features = {
        'elo_rating': 2000.0,
        'player_value': 500.0,
        'recent_form': 0.8,
        'injury_rate': 0.1
    }
    
    normalized = normalize_features(test_features)
    print(f"原始特征: {test_features}")
    print(f"归一化后: {normalized}")
    print(f"形状: {normalized.shape}")
    
    # 测试 3: 与 ProbabilityEngine 集成
    print("\n【测试 3】与 ProbabilityEngine 集成")
    print("-" * 70)
    
    # 导入 ProbabilityEngine
    import sys
    from pathlib import Path
    if __name__ == "__main__":
        project_root = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(project_root))
    
    from app.services.probability_engine import ProbabilityEngine
    
    engine = ProbabilityEngine()
    model.eval()  # 设置为评估模式
    
    # 定义两支球队的完整特征
    team_a_full_features = {
        'elo_rating': 2000.0,
        'player_value': 500.0,
        'recent_form': 0.8,
        'injury_rate': 0.1
    }
    
    team_b_full_features = {
        'elo_rating': 1800.0,
        'player_value': 400.0,
        'recent_form': 0.6,
        'injury_rate': 0.15
    }
    
    # 获取基础胜率
    outcomes = engine.calculate_match_outcome_probabilities(
        team_a_full_features['elo_rating'],
        team_b_full_features['elo_rating']
    )
    
    base_win_prob_a = outcomes['win_a']
    print(f"A 队 Elo: {team_a_full_features['elo_rating']}")
    print(f"B 队 Elo: {team_a_full_features['elo_rating']}")
    print(f"\n基础预测结果:")
    print(f"  A 队胜率: {base_win_prob_a:.4f} ({base_win_prob_a*100:.2f}%)")
    print(f"  平局概率: {outcomes['draw']:.4f} ({outcomes['draw']*100:.2f}%)")
    print(f"  B 队胜率: {outcomes['win_b']:.4f} ({outcomes['win_b']*100:.2f}%)")
    
    # 应用注意力调整
    adjusted_win_prob_a = integrate_with_probability_engine(
        engine,
        team_a_full_features['elo_rating'],
        team_b_full_features['elo_rating'],
        team_a_full_features,
        team_b_full_features,
        model,
        base_win_prob_a
    )
    
    print(f"\n注意力调整:")
    adjustment_value = adjusted_win_prob_a - base_win_prob_a
    print(f"  调整系数: {adjustment_value:+.4f}")
    print(f"  调整后 A 队胜率: {adjusted_win_prob_a:.4f} ({adjusted_win_prob_a*100:.2f}%)")
    print(f"  变化: {adjustment_value*100:+.2f}%")
    
    # 测试 4: 注意力权重可视化
    print("\n【测试 4】注意力权重分析")
    print("-" * 70)
    
    with torch.no_grad():
        attention_weights = model.get_attention_weights(
            normalize_features(team_a_full_features),
            normalize_features(team_b_full_features)
        )
    
    print(f"注意力权重分布:")
    print(f"  形状: {attention_weights.shape}")
    print(f"  权重值: {attention_weights.numpy()}")
    print(f"  最大值位置: {attention_weights.argmax().item()}")
    
    # 测试 5: 边界情况测试
    print("\n【测试 5】边界情况测试")
    print("-" * 70)
    
    # 完全相同的球队
    identical_features = {
        'elo_rating': 1800.0,
        'player_value': 400.0,
        'recent_form': 0.6,
        'injury_rate': 0.12
    }
    
    adj_identical = model(
        normalize_features(identical_features),
        normalize_features(identical_features)
    )
    print(f"相同球队调整系数: {adj_identical.item():+.4f} (应接近 0)")
    
    # 极端差异
    strong_team = {
        'elo_rating': 2200.0,
        'player_value': 800.0,
        'recent_form': 0.95,
        'injury_rate': 0.05
    }
    
    weak_team = {
        'elo_rating': 1400.0,
        'player_value': 150.0,
        'recent_form': 0.2,
        'injury_rate': 0.3
    }
    
    adj_extreme = model(
        normalize_features(strong_team),
        normalize_features(weak_team)
    )
    print(f"极端差异调整系数: {adj_extreme.item():+.4f} (应为正值)")
    
    print("\n" + "=" * 70)
    print("所有测试完成！")
    print("=" * 70)
