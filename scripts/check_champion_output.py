"""
check_champion_output.py
检查冠军预测输出完整性
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
    print("Champion Output 检查")
    print("=" * 50)

    from app.agents.worldcup_agent import WorldCupPredictionAgent
    agent = WorldCupPredictionAgent(seed=42)
    state = agent.run(season=2026, mode="workflow", use_llm=True)
    result = state.to_dict()

    # 1. champion 存在
    champion = result.get("predicted_champion") or result.get("champion", "")
    check("champion 存在", bool(champion), f"champion={champion}")
    check("champion 不是 Unknown", champion != "Unknown", f"champion={champion}")

    # 2. champion_probability
    prob = result.get("champion_probability")
    check("champion_probability 存在", prob is not None, f"prob={prob}")
    if prob is not None:
        check("champion_probability > 0", prob > 0, f"prob={prob}")
        check("champion_probability <= 100", prob <= 100, f"prob={prob}")

    # 3. champion_explanation
    explanation = result.get("champion_explanation", {})
    check("champion_explanation 存在", bool(explanation))
    if explanation:
        check("explanation 有 title", bool(explanation.get("title")))
        check("explanation 有 content", bool(explanation.get("content")))
        check("explanation 有 source", bool(explanation.get("source")))
        check("explanation source 是 llm 或 fallback",
              explanation.get("source") in ("llm", "fallback"),
              f"source={explanation.get('source')}")

    # 4. top_contenders
    top_c = result.get("top_contenders", [])
    check("top_contenders 存在", len(top_c) > 0, f"count={len(top_c)}")
    if top_c:
        check("top_contenders[0] 有 team", bool(top_c[0].get("team")))
        check("top_contenders[0] 有 team_strength_index", top_c[0].get("team_strength_index") is not None)
        check("top_contenders[0] 有 recent_form_score", top_c[0].get("recent_form_score") is not None)
        check("top_contenders[0] 有 attack_score", top_c[0].get("attack_score") is not None)
        check("top_contenders[0] 有 defense_score", top_c[0].get("defense_score") is not None)
        check("top_contenders[0] 有 path_advantage_score", top_c[0].get("path_advantage_score") is not None)
        check("top_contenders[0] 有 key_reasons", bool(top_c[0].get("key_reasons")))

    # 5. bracket_payload
    bp = result.get("bracket_payload", {})
    check("bracket_payload 存在", bool(bp))

    # 6. enhanced_features
    enhanced = result.get("enhanced_features", {})
    if not enhanced:
        enhanced = result.get("enhanced_team_features", {})
    check("enhanced_features 存在", bool(enhanced), f"keys={list(enhanced.keys())[:5] if enhanced else 'empty'}")

    # 7. visualization_payload
    vp = result.get("visualization_payload", {})
    check("visualization_payload 存在", bool(vp))
    if vp:
        vp_champ = vp.get("champion", {})
        check("visualization_payload.champion 存在", bool(vp_champ))

    # 8. data_status
    ds = result.get("data_status", {})
    check("data_status 存在", bool(ds))
    if ds:
        check("data_status 有 user_message", bool(ds.get("user_message")))

    print(f"\n冠军: {champion}")
    print(f"概率: {prob}%")
    print(f"解释来源: {explanation.get('source', 'N/A')}")
    print(f"热门球队数: {len(top_c)}")

    print(f"\n{'=' * 50}")
    print(f"结果: {PASS} 通过, {FAIL} 失败")
    print(f"{'=' * 50}")

    if FAIL > 0:
        sys.exit(1)
    print("[OK] Champion output 检查全部通过")


if __name__ == "__main__":
    main()
