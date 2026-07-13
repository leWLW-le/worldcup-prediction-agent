"""查找 API-Football 中世界杯的正确 league ID"""
import os, sys
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

import requests

api_key = os.environ.get("API_FOOTBALL") or os.environ.get("API_FOOTBALL_KEY")
if not api_key:
    print("No API key found")
    sys.exit(1)

headers = {"x-apisports-key": api_key}

# 1. 搜索 "World Cup" 相关的联赛
print("=" * 60)
print("搜索 World Cup 联赛...")
print("=" * 60)

resp = requests.get("https://v3.football.api-sports.io/leagues", headers=headers, params={"search": "World Cup"}, timeout=10)
print(f"HTTP: {resp.status_code}")
data = resp.json()

if "response" in data:
    leagues = data["response"]
    print(f"找到 {len(leagues)} 个结果")
    for item in leagues:
        league = item.get("league", {})
        lid = league.get("id")
        name = league.get("name")
        country = item.get("country", {}).get("name", "N/A")
        season = item.get("seasons", [])
        latest_seasons = [s.get("year") for s in season[-5:]] if season else []
        print(f"  ID={lid} | {name} | {country} | 最近赛季: {latest_seasons}")
else:
    print(f"响应异常: {str(data)[:300]}")

# 2. 也试试 league=1 看看到底是什么联赛
print("\n" + "=" * 60)
print("检查 league=1 是什么...")
print("=" * 60)

resp2 = requests.get("https://v3.football.api-sports.io/leagues", headers=headers, params={"id": 1}, timeout=10)
print(f"HTTP: {resp2.status_code}")
data2 = resp2.json()

if "response" in data2:
    for item in data2["response"]:
        league = item.get("league", {})
        print(f"  ID={league.get('id')} | {league.get('name')} | {item.get('country', {}).get('name', 'N/A')}")
        seasons = item.get("seasons", [])
        latest = [s.get("year") for s in seasons[-5:]] if seasons else []
        print(f"  最近赛季: {latest}")
else:
    print(f"响应异常: {str(data2)[:300]}")
