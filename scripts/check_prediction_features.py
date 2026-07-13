"""
check_prediction_features.py
检查冠军预测特征层完整性
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} - {detail}")


def main():
    global PASS, FAIL
    print("=" * 50)
    print("Prediction Features 检查")
    print("=" * 50)

    # 1. team_ratings 是否加载
    from app.services.team_rating_service import load_team_ratings
    ratings = load_team_ratings()
    check("team_ratings 加载", len(ratings) > 0, f"count={len(ratings)}")

    # 2. recent_form 是否计算
    from app.services.fixture_repository import FixtureRepository
    from app.services.recent_form_service import compute_recent_form
    repo = FixtureRepository()
    canonical = repo.get_canonical_fixtures()
    fixtures = canonical.get("fixtures", [])
    recent_form = compute_recent_form(fixtures)
    check("recent_form 计算", len(recent_form) > 0, f"teams={len(recent_form)}")

    # 3. attack_defense_stats 是否计算
    from app.services.team_stats_service import compute_attack_defense_stats
    atk_def = compute_attack_defense_stats(fixtures, recent_form)
    check("attack_defense_stats 计算", len(atk_def) > 0, f"teams={len(atk_def)}")
    if atk_def:
        sample = list(atk_def.values())[0]
        check("attack_score 存在", "attack_score" in sample)
        check("defense_score 存在", "defense_score" in sample)

    # 4. path_difficulty 是否计算
    from app.agents.worldcup_agent import WorldCupPredictionAgent
    agent = WorldCupPredictionAgent(seed=42)
    state = agent.run(season=2026, mode="workflow", use_llm=True)

    from app.services.path_difficulty_service import compute_path_difficulty
    path_diff = compute_path_difficulty(state.knockout_predictions, ratings)
    check("path_difficulty 计算", len(path_diff) > 0, f"teams={len(path_diff)}")

    # 5. team_features 是否生成（enhanced）
    enhanced = state.enhanced_features if hasattr(state, 'enhanced_features') else {}
    if not enhanced:
        enhanced = getattr(state, 'enhanced_team_features', {})
    check("team_features 生成", len(enhanced) > 0, f"teams={len(enhanced)}")

    # 6. champion_prediction 使用 team_features
    if enhanced:
        sample_team = list(enhanced.values())[0]
        has_index = "team_strength_index" in sample_team
        check("team_features 包含 team_strength_index", has_index)
    else:
        check("team_features 包含 team_strength_index", False, "no features")

    # 7. top_contenders 是否包含 feature_breakdown
    top_c = state.top_contenders
    check("top_contenders 存在", len(top_c) > 0, f"count={len(top_c)}")
    if top_c:
        has_fb = "feature_breakdown" in top_c[0] or "team_strength_index" in top_c[0]
        check("top_contenders 包含特征数据", has_fb)

    # 8. champion_explanation 是否基于 feature_breakdown
    explanation = state.champion_explanation
    check("champion_explanation 存在", bool(explanation))
    if explanation:
        check("champion_explanation 有 content", bool(explanation.get("content")))
        check("champion_explanation 有 source", bool(explanation.get("source")))

    # 9. champion 不是来自旧 fallback
    champion = state.predicted_champion
    check("champion 不是 Unknown", champion and champion != "Unknown", f"champion={champion}")

    # 10. champion_probability 由新特征计算
    prob = state.champion_probability
    check("champion_probability 存在", prob is not None and prob > 0, f"prob={prob}")

    print(f"\n{'=' * 50}")
    print(f"结果: {PASS} 通过, {FAIL} 失败")
    print(f"{'=' * 50}")

    if FAIL > 0:
        sys.exit(1)
    print("[OK] Prediction features 检查全部通过")


if __name__ == "__main__":
    main()
