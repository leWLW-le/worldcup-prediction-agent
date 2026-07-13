"""检查并修复八强赛数据"""
import json
from pathlib import Path

# 读取当前的预测结果
result_file = Path("prediction_result.json")
if result_file.exists():
    with open(result_file, encoding='utf-8-sig') as f:
        data = json.load(f)
    
    print("=" * 60)
    print("当前 prediction_result.json 中的八强赛数据:")
    print("=" * 60)
    
    knockout_predictions = data.get('knockout_predictions', [])
    qf_matches = [m for m in knockout_predictions if m['round'] == 'quarter_finals']
    
    print(f"八强赛数量: {len(qf_matches)}场\n")
    for i, match in enumerate(qf_matches, 1):
        print(f"{i}. {match['home_team']} vs {match['away_team']}")
        print(f"   比分: {match.get('predicted_score')}")
        print(f"   source: {match.get('source')}")
        print(f"   confidence: {match.get('confidence')}")
        print()
    
    # 检查是否需要修复
    needs_fix = any(m.get('source') != 'real_data' for m in qf_matches)
    
    if needs_fix:
        print("⚠️  检测到八强赛 source 字段不正确，正在修复...")
        
        # 导入真实数据
        from app.services import real_tournament_data as rtd
        
        # 创建八强赛的映射字典（key: home_away组合）
        real_qf_map = {}
        for match in rtd.REAL_QUARTER_FINALS:
            key = f"{match['home']}_{match['away']}"
            real_qf_map[key] = match
        
        # 修复 knockout_predictions 中的八强赛数据
        for pred in knockout_predictions:
            if pred['round'] == 'quarter_finals':
                key = f"{pred['home_team']}_{pred['away_team']}"
                if key in real_qf_map:
                    real_match = real_qf_map[key]
                    pred['source'] = 'real_data'
                    pred['confidence'] = 1.0
                    pred['predicted_score'] = f"{real_match['score_a']}-{real_match['score_b']}"
                    pred['predicted_home_score'] = real_match['score_a']
                    pred['predicted_away_score'] = real_match['score_b']
                    pred['winner'] = real_match['winner']
                    pred['is_penalty_shootout'] = real_match.get('is_penalty_shootout', False)
        
        # 保存修复后的数据
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print("✅ 修复完成！已更新 prediction_result.json")
        print("\n修复后的八强赛数据:")
        print("=" * 60)
        qf_matches_fixed = [m for m in knockout_predictions if m['round'] == 'quarter_finals']
        for i, match in enumerate(qf_matches_fixed, 1):
            print(f"{i}. ✅ {match['home_team']} vs {match['away_team']}: {match['predicted_score']}")
            print(f"   source: {match['source']}, confidence: {match['confidence']}")
    else:
        print("✅ 八强赛数据已经是正确的 (source=real_data)")
else:
    print("❌ prediction_result.json 文件不存在")
