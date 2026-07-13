"""
测试 football-data.org API

环境变量：
- FOOTBALL_DATA_API (优先)
- FOOTBALL_DATA_API_KEY (兼容)

请求：
- GET https://api.football-data.org/v4/competitions/WC/matches
- GET https://api.football-data.org/v4/competitions/WC/teams
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
    """获取 API key，优先使用 FOOTBALL_DATA_API，兼容 FOOTBALL_DATA_API_KEY"""
    key = os.environ.get("FOOTBALL_DATA_API")
    if not key:
        key = os.environ.get("FOOTBALL_DATA_API_KEY")
    return key


def test_matches(api_key):
    """测试 matches 接口"""
    print("\n" + "=" * 60)
    print("1. 测试 Matches 接口")
    print("=" * 60)
    
    url = "https://api.football-data.org/v4/competitions/WC/matches"
    headers = {"X-Auth-Token": api_key}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        print(f"HTTP 状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            matches = data.get("matches", [])
            print(f"✓ 成功")
            print(f"Matches 数量: {len(matches)}")
            
            # 显示前3条示例
            if len(matches) > 0:
                print("\n前3条比赛示例:")
                for i, match in enumerate(matches[:3], 1):
                    home = match.get("homeTeam", {}).get("name", "N/A")
                    away = match.get("awayTeam", {}).get("name", "N/A")
                    status = match.get("status", "N/A")
                    score = f"{match.get('score', {}).get('fullTime', {}).get('home', '-')}:{match.get('score', {}).get('fullTime', {}).get('away', '-')}"
                    print(f"  {i}. {home} vs {away} | Status: {status} | Score: {score}")
            
            return True, len(matches), None
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
    
    url = "https://api.football-data.org/v4/competitions/WC/teams"
    headers = {"X-Auth-Token": api_key}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        print(f"HTTP 状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            teams = data.get("teams", [])
            print(f"✓ 成功")
            print(f"Teams 数量: {len(teams)}")
            
            # 显示前3条示例
            if len(teams) > 0:
                print("\n前3个球队示例:")
                for i, team in enumerate(teams[:3], 1):
                    name = team.get("name", "N/A")
                    code = team.get("tla", "N/A")
                    print(f"  {i}. {name} ({code})")
            
            return True, len(teams), None
        else:
            print(f"✗ 失败")
            error_msg = response.text[:200] if response.text else "No error message"
            print(f"错误信息: {error_msg}")
            return False, 0, f"HTTP {response.status_code}: {error_msg}"
            
    except Exception as e:
        print(f"✗ 异常: {e}")
        return False, 0, str(e)


if __name__ == "__main__":
    print("=" * 60)
    print("Football-Data.org API 测试")
    print("=" * 60)
    
    # 检查 API key
    api_key = get_api_key()
    if not api_key:
        print("❌ 错误: 未找到环境变量 FOOTBALL_DATA_API 或 FOOTBALL_DATA_API_KEY")
        print("请设置环境变量后重试")
        sys.exit(1)
    
    # 隐藏显示 key（只显示前4位和后4位）
    masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
    print(f"\nAPI Key: {masked_key} ✓")
    
    # 测试 matches
    matches_success, matches_count, matches_error = test_matches(api_key)
    
    # 测试 teams
    teams_success, teams_count, teams_error = test_teams(api_key)
    
    # 总结
    print("\n" + "=" * 60)
    print("测试结果总结")
    print("=" * 60)
    print(f"FOOTBALL_DATA_API: {'✓ 读取成功' if api_key else '✗ 未配置'}")
    print(f"Matches 接口: {'✓ 成功' if matches_success else '✗ 失败'} ({matches_count} 条)")
    print(f"Teams 接口: {'✓ 成功' if teams_success else '✗ 失败'} ({teams_count} 条)")
    
    if matches_error:
        print(f"Matches 错误: {matches_error}")
    if teams_error:
        print(f"Teams 错误: {teams_error}")
    
    # 退出码
    if matches_success and teams_success:
        print("\n✅ 所有测试通过！")
        sys.exit(0)
    else:
        print("\n❌ 部分测试失败")
        sys.exit(1)
