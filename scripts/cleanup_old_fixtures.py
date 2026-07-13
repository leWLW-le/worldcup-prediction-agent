"""
清理旧 fixtures 数据

运行方式：
    python scripts/cleanup_old_fixtures.py [--dry-run]

功能：
1. 备份当前数据库
2. 如果 football_data external_real 已有足够数据，则只保留 canonical 数据
3. 旧数据在查询层排除，不直接删除

策略：查询层排除（推荐），不物理删除
"""

import sys
import shutil
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

from app.services.fixture_repository import FixtureRepository


def main():
    import argparse
    parser = argparse.ArgumentParser(description="清理旧 fixtures 数据")
    parser.add_argument("--dry-run", action="store_true", help="只检查不操作")
    args = parser.parse_args()
    
    print("=" * 60)
    print("fixtures 数据清理")
    print("=" * 60)
    
    repo = FixtureRepository()
    
    # 1. 查看表总状态
    table_status = repo.get_status()
    print(f"\n表总状态:")
    print(f"  fixtures 总数: {table_status['fixtures_count']}")
    print(f"  source 分布: {table_status['source_distribution']}")
    print(f"  source_level 分布: {table_status['source_level_distribution']}")
    
    # 2. 查看 canonical 状态
    canonical_status = repo.get_canonical_status()
    print(f"\nCanonical 状态:")
    print(f"  canonical fixtures_count: {canonical_status['fixtures_count']}")
    print(f"  source: {canonical_status['source']}")
    print(f"  source_level: {canonical_status['source_level']}")
    
    # 3. 判断是否需要清理
    total = table_status["fixtures_count"]
    canonical = canonical_status["fixtures_count"]
    
    if total == canonical:
        print(f"\n✅ 表数据全部为 canonical，无需清理")
        return
    
    print(f"\n⚠️ 表总数 ({total}) > canonical 数量 ({canonical})")
    print(f"   差异: {total - canonical} 条旧数据")
    
    # 4. 备份数据库
    db_path = project_root / "worldcup.db"
    if db_path.exists():
        backup_path = project_root / f"worldcup_backup_{Path(db_path).stat().st_mtime}.db"
        if not args.dry_run:
            shutil.copy2(db_path, backup_path)
            print(f"\n✅ 数据库已备份到: {backup_path}")
        else:
            print(f"\n[dry-run] 将备份到: {backup_path}")
    
    # 5. 清理策略
    print(f"\n清理策略:")
    print(f"  ✅ 查询层排除旧数据（已实现）")
    print(f"  ✅ FixtureRepository.get_canonical_fixtures() 只返回 canonical 数据")
    print(f"  ✅ Dashboard 和 API 只使用 canonical 状态")
    print(f"  ℹ️  旧数据保留在表中，不影响 canonical 查询")
    
    if args.dry_run:
        print(f"\n[dry-run] 未执行任何操作")
    else:
        print(f"\n✅ 清理完成（查询层排除）")


if __name__ == "__main__":
    main()
