"""
同步外部 fixtures 数据

运行方式：
    python scripts/sync_external_fixtures.py --season 2026

功能：
调用 DataSourceManager.refresh_fixtures() 从外部 API 刷新比赛数据并写入 fixtures 表
"""

import argparse
import sys
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载 .env 文件
load_dotenv(project_root / ".env")

from app.services.data_source_manager import DataSourceManager


def main():
    parser = argparse.ArgumentParser(description="同步外部 fixtures 数据")
    parser.add_argument("--season", type=int, default=2026, help="世界杯赛季，默认 2026")
    args = parser.parse_args()
    
    print("=" * 70)
    print(f"开始同步 {args.season} 年世界杯 fixtures 数据")
    print("=" * 70)
    
    # 创建数据源管理器
    mgr = DataSourceManager()
    
    # 检查 API key 配置
    print("\n📌 API Key 配置:")
    if mgr.football_data_key:
        masked = f"{mgr.football_data_key[:4]}...{mgr.football_data_key[-4:]}" if len(mgr.football_data_key) > 8 else "***"
        print(f"  ✓ FOOTBALL_DATA_API: {masked}")
    else:
        print(f"  ✗ FOOTBALL_DATA_API: 未配置")
    
    if mgr.api_football_key:
        masked = f"{mgr.api_football_key[:4]}...{mgr.api_football_key[-4:]}" if len(mgr.api_football_key) > 8 else "***"
        print(f"  ✓ API_FOOTBALL: {masked}")
    else:
        print(f"  ✗ API_FOOTBALL: 未配置")
    
    # 执行刷新
    print(f"\n 正在刷新 fixtures 数据...")
    result = mgr.refresh_fixtures(season=args.season)
    
    # 输出结果
    print("\n" + "=" * 70)
    print("同步结果")
    print("=" * 70)
    
    # API 状态
    print(f"\n📊 API 状态:")
    print(f"  football-data.org: {result['football_data_status']}")
    print(f"  API-Football:      {result['api_football_status']}")
    
    # 数据来源
    print(f"\n📦 数据来源:")
    print(f"  source:       {result['source'] or 'N/A'}")
    print(f"  source_level: {result['source_level'] or 'N/A'}")
    
    # upsert 统计
    print(f"\n📝 Upsert 统计:")
    print(f"  inserted: {result['inserted']}")
    print(f"  updated:  {result['updated']}")
    print(f"  skipped:  {result['skipped']}")
    
    # fixtures 表状态
    print(f"\n📈 Fixtures 表状态:")
    print(f"  fixtures_count:   {result['fixtures_count']}")
    print(f"  last_updated:     {result['last_updated'] or 'N/A'}")
    print(f"  needs_review:     {result['needs_review_count']}")
    print(f"  is_external_real: {'✓' if result['is_external_realtime'] else '✗'}")
    
    # 用户消息
    print(f"\n 消息:")
    print(f"  {result['message']}")
    
    # 验收判断
    print("\n" + "=" * 70)
    print("验收结果")
    print("=" * 70)
    
    success = True
    
    if result['fixtures_count'] == 0:
        print("❌ fixtures_count = 0 (失败)")
        success = False
    else:
        print(f"✅ fixtures_count = {result['fixtures_count']} (通过)")
    
    if result['source'] not in ['football_data', 'api_football']:
        print(f"❌ source = {result['source']} (期望: football_data 或 api_football)")
        success = False
    else:
        print(f"✅ source = {result['source']} (通过)")
    
    if result['source_level'] != 'external_real':
        print(f"❌ source_level = {result['source_level']} (期望: external_real)")
        success = False
    else:
        print(f"✅ source_level = {result['source_level']} (通过)")
    
    if success:
        print("\n✅ 同步成功！")
        return 0
    else:
        print("\n❌ 同步失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
