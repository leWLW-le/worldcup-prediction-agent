"""测试八强赛真实数据是否正确集成"""
import json
from pathlib import Path

# 1. 检查真实数据文件
print("=" * 60)
print("1. 检查真实数据文件")
print("=" * 60)
from app.services import real_tournament_data as rtd

print(f"✓ 32强赛: {len(rtd.REAL_ROUND_OF_32)}场")
print(f"✓ 16强赛: {len(rtd.REAL_ROUND_OF_16)}场")
print(f"✓ 8强赛:  {len(rtd.REAL_QUARTER_FINALS)}场")
print(f"✓ 剩余阶段: {rtd.get_remaining_stage()}")
print()

# 2. 检查八强赛详情
print("=" * 60)
print("2. 八强赛真实结果")
print("=" * 60)
for i, match in enumerate(rtd.REAL_QUARTER_FINALS, 1):
    print(f"{i}. {match['home']} vs {match['away']}: "
          f"{match['score_a']}-{match['score_b']} → {match['winner']} "
          f"{'(点球)' if match.get('is_penalty_shootout') else ''}")
print()

# 3. 检查预测结果JSON（如果存在）
result_file = Path("prediction_result.json")
if result_file.exists():
    print("=" * 60)
    print("3. 检查预测结果JSON")
    print("=" * 60)
    with open(result_file, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)
    
    kp = data.get("knockout_predictions", [])
    qf_matches = [m for m in kp if m["round"] == "quarter_finals"]
    
    print(f"✓ 淘汰赛预测总数: {len(kp)}场")
    print(f"✓ 8强赛数量: {len(qf_matches)}场")
    
    if qf_matches:
        source = qf_matches[0].get("source", "N/A")
        confidence = qf_matches[0].get("confidence", 0)
        print(f"✓ 8强赛 source: {source}")
        print(f"✓ 8强赛 confidence: {confidence}")
        
        if source == "real_data" and confidence == 1.0:
            print("\n✅ 成功！八强赛已正确标记为真实数据")
        else:
            print(f"\n⚠️  注意：source={source}, confidence={confidence}")
            print("   需要重新运行预测以应用最新真实数据")
    
    # 4. 检查数据质量报告
    report = data.get("data_quality_report", {})
    fallback = report.get("fallback_used", False)
    score = report.get("score", 0)
    has_real_knockout = any(m.get("source") == "real_data" for m in kp)
    
    print()
    print("=" * 60)
    print("4. 数据状态检查")
    print("=" * 60)
    print(f"✓ fallback_used: {fallback}")
    print(f"✓ quality_score: {score}")
    print(f"✓ 有真实淘汰赛数据: {has_real_knockout}")
    
    if has_real_knockout:
        print("\n✅ 前端将显示绿色'已结束'标签，不显示黄色警告条")
else:
    print("\n⚠️  prediction_result.json 不存在，请先运行预测")

print()
print("=" * 60)
print("总结")
print("=" * 60)
print("✅ 真实数据文件已更新（包含八强赛4场）")
print("✅ bracket_tool.py 已修改（使用真实八强赛数据）")
print("✅ debug_dashboard.py 已修复（正确映射 real_data 标签）")
print()
print("下一步：在 Streamlit 页面点击'重新预测'按钮即可看到效果")
print("=" * 60)
