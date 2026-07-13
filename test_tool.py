"""测试 football_data_tool"""
from app.tools.football_data_tool import FootballDataTool

tool = FootballDataTool()
result = tool.get_worldcup_matches()

print(f"Success: {result['success']}")
print(f"Count: {len(result.get('data', []))}")

matches = result.get('data', [])
if matches:
    print(f"First match: {matches[0]}")
    print(f"Last match: {matches[-1]}")
    
    # 检查是否有 None 球队
    none_count = 0
    for m in matches:
        if not m.get('home_team') or not m.get('away_team'):
            none_count += 1
            print(f"Found None team: {m}")
    print(f"Matches with None teams: {none_count}")
else:
    print("No matches found")
