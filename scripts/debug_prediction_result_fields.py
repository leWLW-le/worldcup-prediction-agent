"""
调试脚本：打印 run-prediction 返回结构

运行方式：
    cd J:\project\worldcup
    .venv\Scripts\python.exe scripts\debug_prediction_result_fields.py
"""

import sys
import json
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")


def main():
    print("=" * 60)
    print("debug_prediction_result_fields")
    print("=" * 60)

    from app.agents.worldcup_agent import WorldCupPredictionAgent

    agent = WorldCupPredictionAgent(seed=42)
    print("\n运行 agent (mode=llm_planner_safe, use_llm=True) ...")
    state = agent.run(season=2026, mode="llm_planner_safe", use_llm=True)
    result = state.to_dict()

    print(f"\n--- result 顶层 keys ---")
    for k in sorted(result.keys()):
        v = result[k]
        vtype = type(v).__name__
        if isinstance(v, str):
            print(f"  {k}: {vtype} = \"{v}\"")
        elif isinstance(v, (int, float, bool)):
            print(f"  {k}: {vtype} = {v}")
        elif isinstance(v, list):
            print(f"  {k}: {vtype} (len={len(v)})")
        elif isinstance(v, dict):
            print(f"  {k}: {vtype} (keys={list(v.keys())[:8]})")
        elif v is None:
            print(f"  {k}: None")
        else:
            print(f"  {k}: {vtype}")

    print(f"\n--- 重点字段 ---")
    print(f"1. result['champion'] = {result.get('champion')!r}")
    print(f"2. result['predicted_champion'] = {result.get('predicted_champion')!r}")
    print(f"3. result['champion_probability'] = {result.get('champion_probability')!r}")
    print(f"4. result['predicted_runner_up'] = {result.get('predicted_runner_up')!r}")

    # bracket_payload (不在 to_dict 中，从 visualization_payload 看)
    viz = result.get("visualization_payload", {})
    print(f"5. viz['champion'] = {viz.get('champion')!r}")
    print(f"6. viz['final_prediction'] = {viz.get('final_prediction')!r}")

    # favorites / top_contenders (power_ranking)
    ranking = viz.get("power_ranking", [])
    if ranking:
        print(f"7. favorites 第一名 = {ranking[0].get('team')}, power_score = {ranking[0].get('power_score')}")
    else:
        print(f"7. favorites: 无数据")

    # final match
    fm = viz.get("final_match")
    if fm:
        print(f"8. final match winner = {fm.get('winner')}, source = {fm.get('source')}")
    else:
        print(f"8. final match: 无")

    # knockout_predictions 中的决赛
    kp = result.get("knockout_predictions", [])
    final_matches = [m for m in kp if m.get("round") == "final"]
    if final_matches:
        f = final_matches[0]
        print(f"9. knockout final: winner={f.get('winner')}, source={f.get('source')}")
    else:
        print(f"9. knockout 中无决赛 (共 {len(kp)} 场淘汰赛)")

    # data_status
    ds = result.get("data_status", {})
    print(f"10. data_status.source_level = {ds.get('source_level')!r}")
    print(f"    data_status.fixtures_count = {ds.get('fixtures_count')!r}")
    print(f"    data_status.user_message = {ds.get('user_message')!r}")

    # mode & status
    print(f"11. mode = {result.get('mode')!r}")
    print(f"    status = {result.get('status')!r}")

    print("\n" + "=" * 60)
    print("debug 完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
