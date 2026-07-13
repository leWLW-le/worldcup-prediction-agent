# test_api.py - 测试修复后的 API 客户端（缓存机制验证）
from app.data.api_fetcher import FootballAPIClients
from app.core.config import get_settings
import json

def run_test():
    settings = get_settings()
    client = FootballAPIClients(api_key=settings.API_FOOTBALL_KEY)
    
    print("=" * 60)
    print("API-Sports 缓存机制验证")
    print("=" * 60)
    
    # 阿根廷国家队 ID = 26，赛季 = 2024
    team_id = 26
    season = 2024
    
    print(f"\n[第 1 次请求] 阿根廷队 (ID: {team_id}) {season} 赛季战绩...")
    print(f"  预期: 调用 API，消耗 1 次额度")
    
    result1 = client.fetch_team_recent_form(team_id, season=season)
    
    print(f"\n  结果来源: {result1.get('source')}")
    print(f"  球队名称: {result1.get('team_name')}")
    print(f"  近期战绩: {result1.get('form')}")
    
    if result1.get('recent_matches'):
        print(f"\n  最近 5 场比赛:")
        for m in result1['recent_matches'][:5]:
            print(f"    {m['date']} | vs {m['opponent']} | {m['score']} | {m['result']} | {m['competition']}")
    
    status1 = client.get_cache_status()
    print(f"\n  API 消耗: today_api_calls = {status1['today_api_calls']}")
    
    print(f"\n[第 2 次请求] 同样的参数...")
    print(f"  预期: 命中缓存，API 消耗不变")
    
    result2 = client.fetch_team_recent_form(team_id, season=season)
    
    print(f"\n  结果来源: {result2.get('source')}")
    
    status2 = client.get_cache_status()
    print(f"\n  API 消耗: today_api_calls = {status2['today_api_calls']}")
    
    print("\n" + "=" * 60)
    if status2['today_api_calls'] == status1['today_api_calls']:
        print("✓ 缓存机制验证通过！第 2 次请求没有消耗 API 额度")
    else:
        print("✗ 缓存机制验证失败！第 2 次请求仍然消耗了 API 额度")
    print("=" * 60)

if __name__ == "__main__":
    run_test()
