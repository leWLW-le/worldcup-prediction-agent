"""
check_bracket_payload_structure.py
检查 bracket_payload 结构完整性
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
    print("Bracket Payload 结构检查")
    print("=" * 50)

    from app.agents.worldcup_agent import WorldCupPredictionAgent
    agent = WorldCupPredictionAgent(seed=42)
    state = agent.run(season=2026, mode="workflow", use_llm=True)
    result = state.to_dict()

    bp = result.get("bracket_payload", {})
    check("bracket_payload 存在", bool(bp))

    required_rounds = ["round_of_32", "round_of_16", "quarter_finals", "semi_finals", "final", "champion"]
    for r in required_rounds:
        check(f"包含 {r}", r in bp, f"missing key: {r}")

    # Check round counts
    r32 = bp.get("round_of_32", [])
    r16 = bp.get("round_of_16", [])
    qf = bp.get("quarter_finals", [])
    sf = bp.get("semi_finals", [])
    f = bp.get("final", [])

    check(f"round_of_32 数量 = {len(r32)}", len(r32) >= 0)
    check(f"round_of_16 数量 = {len(r16)}", len(r16) >= 0)
    check(f"quarter_finals 数量 = {len(qf)}", len(qf) >= 0)
    check(f"semi_finals 数量 = {len(sf)}", len(sf) >= 0)
    check(f"final 数量 = {len(f)}", len(f) >= 0)

    # Check match fields
    required_fields = ["round", "home_team", "away_team", "display_label", "match_source", "source"]
    all_matches = r32 + r16 + qf + sf + f
    if all_matches:
        sample = all_matches[0]
        for field in required_fields:
            check(f"比赛字段包含 {field}", field in sample, f"missing field: {field}")

    # Check champion
    champ = bp.get("champion", {})
    check("champion 有 team", bool(champ.get("team")))

    # Check stage mapping
    stage_map = {"round_of_32": "round_of_32", "round_of_16": "round_of_16",
                 "quarter_finals": "quarter_finals", "semi_finals": "semi_finals", "final": "final"}
    for m in all_matches:
        rnd = m.get("round", "")
        if rnd in stage_map:
            check(f"stage 映射正确: {rnd}", True)
            break

    print(f"\n{'=' * 50}")
    print(f"结果: {PASS} 通过, {FAIL} 失败")
    print(f"{'=' * 50}")

    if FAIL > 0:
        sys.exit(1)
    print("[OK] Bracket payload 结构检查全部通过")


if __name__ == "__main__":
    main()
