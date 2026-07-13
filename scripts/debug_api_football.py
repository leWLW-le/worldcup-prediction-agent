"""深入检查 API-Football 返回的原始数据"""
import os, sys, json
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

import requests

api_key = os.environ.get("API_FOOTBALL") or os.environ.get("API_FOOTBALL_KEY")
headers = {"x-apisports-key": api_key}

# 1. 直接请求 fixtures
print("=" * 60)
print("1. 请求 fixtures?league=1&season=2026")
print("=" * 60)

resp = requests.get("https://v3.football.api-sports.io/fixtures", 
                     headers=headers, 
                     params={"league": 1, "season": 2026}, 
                     timeout=15)
print(f"HTTP: {resp.status_code}")
print(f"Raw response (前500字): {resp.text[:500]}")

# 2. 试试不同的参数组合
print("\n" + "=" * 60)
print("2. 尝试不同参数: league=1&season=2025")
print("=" * 60)

resp2 = requests.get("https://v3.football.api-sports.io/fixtures", 
                      headers=headers, 
                      params={"league": 1, "season": 2025}, 
                      timeout=15)
print(f"HTTP: {resp2.status_code}")
data2 = resp2.json()
print(f"fixtures 数量: {len(data2.get('response', []))}")
if data2.get("response"):
    for fx in data2["response"][:3]:
        teams = fx.get("teams", {})
        print(f"  {teams.get('home',{}).get('name')} vs {teams.get('away',{}).get('name')}")

# 3. 试试 current=true
print("\n" + "=" * 60)
print("3. 尝试 current=true")
print("=" * 60)

resp3 = requests.get("https://v3.football.api-sports.io/fixtures", 
                      headers=headers, 
                      params={"league": 1, "season": 2026, "next": 5}, 
                      timeout=15)
print(f"HTTP: {resp3.status_code}")
data3 = resp3.json()
print(f"fixtures 数量: {len(data3.get('response', []))}")
if data3.get("response"):
    for fx in data3["response"][:5]:
        teams = fx.get("teams", {})
        fixture_info = fx.get("fixture", {})
        print(f"  {teams.get('home',{}).get('name')} vs {teams.get('away',{}).get('name')} | {fixture_info.get('date')}")

# 4. 试试 all 参数
print("\n" + "=" * 60)
print("4. 尝试 last=5 (最近5场)")
print("=" * 60)

resp4 = requests.get("https://v3.football.api-sports.io/fixtures", 
                      headers=headers, 
                      params={"league": 1, "season": 2026, "last": 5}, 
                      timeout=15)
print(f"HTTP: {resp4.status_code}")
data4 = resp4.json()
print(f"fixtures 数量: {len(data4.get('response', []))}")
if data4.get("response"):
    for fx in data4["response"][:5]:
        teams = fx.get("teams", {})
        fixture_info = fx.get("fixture", {})
        status = fixture_info.get("status", {}).get("short", "N/A")
        goals = fx.get("goals", {})
        print(f"  {teams.get('home',{}).get('name')} vs {teams.get('away',{}).get('name')} | {status} | {goals.get('home')}-{goals.get('away')}")

# 5. 检查 API 配额
print("\n" + "=" * 60)
print("5. 检查 API 配额/限制")
print("=" * 60)
print(f"X-RateLimit-Remaining: {resp.headers.get('x-ratelimit-remaining', 'N/A')}")
print(f"X-RateLimit-Limit: {resp.headers.get('x-ratelimit-limit', 'N/A')}")
print(f"Content-Type: {resp.headers.get('content-type', 'N/A')}")
