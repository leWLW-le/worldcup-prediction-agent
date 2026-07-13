"""
数据库迁移脚本：为 fixtures 表添加可信度字段（SQLite 兼容版本）

运行方式：
    python scripts/migrate_fixtures_schema.py
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.db.database import engine, SessionLocal
from sqlalchemy import inspect, text


def check_columns_exist():
    """检查 fixtures 表是否已有新字段"""
    inspector = inspect(engine)
    columns = [c['name'] for c in inspector.get_columns('fixtures')]
    
    required_columns = ['confidence_level', 'evidence_count', 'evidence_sources']
    missing = [col for col in required_columns if col not in columns]
    
    return missing


def migrate_table():
    """使用 ALTER TABLE 添加列（SQLite 3.25+ 支持）"""
    db = SessionLocal()
    try:
        # 检查 SQLite 版本
        version_result = db.execute(text("SELECT sqlite_version()")).fetchone()
        print(f"📌 SQLite 版本: {version_result[0]}")
        
        # 尝试添加缺失的列
        missing = check_columns_exist()
        
        if not missing:
            print("✅ 所有字段已存在，无需迁移")
            return True
        
        for col in missing:
            try:
                if col == 'confidence_level':
                    db.execute(text("ALTER TABLE fixtures ADD COLUMN confidence_level VARCHAR(50)"))
                    print(f"  ✅ 添加列: {col}")
                elif col == 'evidence_count':
                    db.execute(text("ALTER TABLE fixtures ADD COLUMN evidence_count INTEGER DEFAULT 0"))
                    print(f"  ✅ 添加列: {col}")
                elif col == 'evidence_sources':
                    db.execute(text("ALTER TABLE fixtures ADD COLUMN evidence_sources TEXT"))
                    print(f"  ✅ 添加列: {col}")
            except Exception as e:
                print(f"  ️  列 {col} 可能已存在或添加失败: {e}")
        
        db.commit()
        return True
        
    except Exception as e:
        print(f"❌ 迁移失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("开始迁移 fixtures 表结构...")
    print("=" * 60)
    
    try:
        success = migrate_table()
        
        if success:
            # 验证
            missing_after = check_columns_exist()
            if not missing_after:
                print("\n✅ 迁移成功！所有字段已存在")
                sys.exit(0)
            else:
                print(f"\n⚠️  仍有缺失字段: {missing_after}")
                print("   这可能是因为 SQLite 版本过低或不支持某些操作")
                print("   建议手动检查数据库结构")
                sys.exit(1)
        else:
            print("\n❌ 迁移失败")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
