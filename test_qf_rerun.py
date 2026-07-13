"""重新运行预测并验证八强赛是否正确显示为真实数据"""
import requests
import json

print("=" * 60)
print("1. 调用 FastAPI 重新运行预测")
print("=" * 60)

try:
    r = requests.post(
        'http://localhost:8000/api/v1/agent/run-prediction',
        json={'season': 2026, 'mode': 'workflow', 'use_llm': False},
        timeout=180
    )
    print(f"✓ 状态码: {r.status_code}")
    
    if r.status_code != 200:
        print(f"❌ API返回错误: {r.text}")
        exit(1)
    
    result = r.json()
    
except Exception as e:
    print(f"❌ API调用失败: {e}")
    print("请确保 FastAPI 服务正在运行 (python main.py)")
    exit(1)

print("\n" + "=" * 60)
print("2. 检查八强赛数据")
print("=" * 60)

knockout_predictions = result.get('knockout_predictions', [])
qf_matches = [m for m in knockout_predictions if m['round'] == 'quarter_finals']

print(f"✓ 八强赛数量: {len(qf_matches)}场")
print()

for i, match in enumerate(qf_matches, 1):
    source = match.get('source', 'N/A')
    confidence = match.get('confidence', 0)
    score = match.get('predicted_score', '')
    home = match.get('home_team', '')
    away = match.get('away_team', '')
    
    status_icon = "✅" if source == "real_data" else "⚠️"
    print(f"{i}. {status_icon} {home} vs {away}: {score}")
    print(f"   source={source}, confidence={confidence:.4f}")

# 验证所有八强赛都是 real_data
all_real = all(m.get('source') == 'real_data' for m in qf_matches)

print("\n" + "=" * 60)
if all_real:
    print("✅ 成功！所有八强赛都标记为 'real_data'（已结束）")
else:
    print("⚠️  警告：仍有八强赛标记为 'agent_prediction'")
print("=" * 60)
