"""
测试 API-Football (api-sports.io)

环境变量：
- API_FOOTBALL (优先)
- API_FOOTBALL_KEY (兼容)

请求：
- GET https://v3.football.api-sports.io/fixtures?league=1&season=2026
- GET https://v3.football.api-sports.io/teams?league=1&season=2026
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载 .env 文件
load_dotenv(project_root / ".env")

import requests


def get_api_key():
    """获取 API key，优先使用 API_FOOTBALL，兼容 API_FOOTBALL_KEY"""
    key = os.environ.get("API_FOOTBALL")
    if not key:
        key = os.environ.get("API_FOOTBALL_KEY")
    return key


def test_fixtures(api_key):
    """测试 fixtures 接口"""
    print("\n" + "=" * 60)
    print("1. 测试 Fixtures 接口")
    print("=" * 60)
    
    url = "https://v3.football.api-sports.io/fixtures"
    params = {"league": 1, "season": 2026}
    headers = {"x-apisports-key": api_key}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        print(f"HTTP 状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            # 检查 API 是否返回错误信息
            api_errors = data.get("errors", {})
            if api_errors:
                print(f"✗ API 返回错误")
                for key, msg in api_errors.items():
                    print(f"  {key}: {msg}")
                return False, 0, str(api_errors)
            
            # 检查 API-Sports 的响应格式
            if isinstance(data, dict) and "response" in data:
                fixtures = data["response"]
                print(f"✓ 成功")
                print(f"Fixtures 数量: {len(fixtures)}")
                
                # 显示前3条示例
                if len(fixtures) > 0:
                    print("\n前3条比赛示例:")
                    for i, fixture in enumerate(fixtures[:3], 1):
                        teams = fixture.get("teams", {})
                        home = teams.get("home", {}).get("name", "N/A")
                        away = teams.get("away", {}).get("name", "N/A")
                        status = fixture.get("fixture", {}).get("status", {}).get("short", "N/A")
                        goals = fixture.get("goals", {})
                        score = f"{goals.get('home', '-')}:{goals.get('away', '-')}"
                        print(f"  {i}. {home} vs {away} | Status: {status} | Score: {score}")
                
                return True, len(fixtures), None
            else:
                print(f"✗ 响应格式异常")
                error_msg = str(data)[:200]
                print(f"错误信息: {error_msg}")
                return False, 0, f"Invalid response format: {error_msg}"
        else:
            print(f"✗ 失败")
            error_msg = response.text[:200] if response.text else "No error message"
            print(f"错误信息: {error_msg}")
            return False, 0, f"HTTP {response.status_code}: {error_msg}"
            
    except Exception as e:
        print(f"✗ 异常: {e}")
        return False, 0, str(e)


def test_teams(api_key):
    """测试 teams 接口"""
    print("\n" + "=" * 60)
    print("2. 测试 Teams 接口")
    print("=" * 60)
    
    url = "https://v3.football.api-sports.io/teams"
    params = {"league": 1, "season": 2026}
    headers = {"x-apisports-key": api_key}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        print(f"HTTP 状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            # 检查 API-Sports 的响应格式
            if isinstance(data, dict) and "response" in data:
                teams = data["response"]
                print(f"✓ 成功")
                print(f"Teams 数量: {len(teams)}")
                
                # 显示前3条示例
                if len(teams) > 0:
                    print("\n前3个球队示例:")
                    for i, team_data in enumerate(teams[:3], 1):
                        team = team_data.get("team", {})
                        name = team.get("name", "N/A")
                        code = team.get("code", "N/A")
                        print(f"  {i}. {name} ({code})")
                
                return True, len(teams), None
            else:
                print(f"✗ 响应格式异常")
                error_msg = str(data)[:200]
                print(f"错误信息: {error_msg}")
                return False, 0, f"Invalid response format: {error_msg}"
        else:
            print(f" 失败")
            error_msg = response.text[:200] if response.text else "No error message"
            print(f"错误信息: {error_msg}")
            return False, 0, f"HTTP {response.status_code}: {error_msg}"
            
    except Exception as e:
        print(f" 异常: {e}")
        return False, 0, str(e)


if __name__ == "__main__":
    print("=" * 60)
    print("API-Football (api-sports.io) 测试")
    print("=" * 60)
    
    # 检查 API key
    api_key = get_api_key()
    if not api_key:
        print(" 错误: 未找到环境变量 API_FOOTBALL 或 API_FOOTBALL_KEY")
        print("请设置环境变量后重试")
        sys.exit(1)
    
    # 隐藏显示 key（只显示前4位和后4位）
    masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
    print(f"\nAPI Key: {masked_key} ✓")
    
    # 测试 fixtures
    fixtures_success, fixtures_count, fixtures_error = test_fixtures(api_key)
    
    # 测试 teams
    teams_success, teams_count, teams_error = test_teams(api_key)
    
    # 总结
    print("\n" + "=" * 60)
    print("测试结果总结")
    print("=" * 60)
    print(f"API_FOOTBALL: {'✓ 读取成功' if api_key else '✗ 未配置'}")
    print(f"Fixtures 接口: {'✓ 成功' if fixtures_success else '✗ 失败'} ({fixtures_count} 条)")
    print(f"Teams 接口: {'✓ 成功' if teams_success else '✗ 失败'} ({teams_count} 条)")
    
    if fixtures_error:
        print(f"Fixtures 错误: {fixtures_error}")
    if teams_error:
        print(f"Teams 错误: {teams_error}")
    
    # 退出码
    if fixtures_success and teams_success:
        print("\n✅ 所有测试通过！")
        sys.exit(0)
    else:
        print("\n❌ 部分测试失败")
        sys.exit(1)
