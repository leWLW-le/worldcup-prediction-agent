"""
快速修复：将 final_agent_result.json 的 champion 字段对齐 Monte Carlo Top1。
不需要重新运行完整预测，只修正 champion/probability/explanation 字段。

运行: python scripts/fix_champion_from_monte_carlo.py
"""
import json
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def main():
    sim_path = DATA_DIR / "simulation_distribution.json"
    result_path = DATA_DIR / "final_agent_result.json"

    if not sim_path.exists():
        print("ERROR: simulation_distribution.json not found")
        return 1
    if not result_path.exists():
        print("ERROR: final_agent_result.json not found")
        return 1

    # 1. 读取 Monte Carlo 数据
    with open(sim_path, encoding="utf-8") as f:
        sim_data = json.load(f)
    mc_champion_dict = sim_data.get("champion", {})
    if not mc_champion_dict:
        print("ERROR: simulation_distribution.json has no champion data")
        return 1

    mc_top1_team = max(mc_champion_dict, key=mc_champion_dict.get)
    mc_top1_prob = mc_champion_dict[mc_top1_team]
    print(f"Monte Carlo Top1: {mc_top1_team} = {mc_top1_prob*100:.2f}%")

    # 2. 读取当前 final_agent_result.json
    with open(result_path, encoding="utf-8") as f:
        result = json.load(f)

    old_champion = result.get("champion", "")
    old_prob = result.get("champion_probability", 0)
    print(f"旧 champion: {old_champion} = {old_prob}")

    # 3. 保存 bracket 路径冠军
    if old_champion and old_champion != mc_top1_team:
        result["representative_path_champion"] = {
            "name": old_champion,
            "source": "single_bracket_path",
        }
        print(f"保存 bracket 路径冠军: {old_champion}")

    # 4. 覆盖 champion 字段
    result["champion"] = mc_top1_team
    result["predicted_champion"] = mc_top1_team
    result["champion_probability"] = round(mc_top1_prob, 4)

    # 5. 确保 top5 排序正确（Monte Carlo 概率降序）
    sorted_mc = sorted(mc_champion_dict.items(), key=lambda x: -x[1])
    top5 = []
    for team, prob in sorted_mc[:5]:
        top5.append({"team": team, "probability": round(prob, 4)})
    result["top5"] = top5

    # 6. 更新 explanation 标题
    explanation = result.get("explanation", {})
    if isinstance(explanation, dict):
        old_title = explanation.get("title", "")
        new_title = f"为什么预测 {mc_top1_team} 夺冠？"
        explanation["title"] = new_title
        # 更新内容中的冠军名引用
        content = explanation.get("content", "")
        if content and old_champion and old_champion != mc_top1_team:
            content = content.replace(
                f"为什么预测 {old_champion} 夺冠",
                f"为什么预测 {mc_top1_team} 夺冠",
            )
            explanation["content"] = content
        result["explanation"] = explanation

    # 7. 更新时间戳
    result["generated_at"] = datetime.utcnow().isoformat()
    result["monte_carlo_override"] = True

    # 8. 写回文件
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n修复完成:")
    print(f"  champion: {old_champion} → {mc_top1_team}")
    print(f"  champion_probability: {old_prob} → {round(mc_top1_prob, 4)}")
    print(f"  top5[0]: {top5[0]['team']} = {top5[0]['probability']*100:.2f}%")
    print(f"  explanation title: {explanation.get('title', 'N/A')}")

    # 9. 验证
    assert result["champion"] == mc_top1_team
    assert result["predicted_champion"] == mc_top1_team
    assert result["top5"][0]["team"] == mc_top1_team
    print("\n✅ 所有断言通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
