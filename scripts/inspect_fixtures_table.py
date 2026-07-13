"""
检查 fixtures 表状态

运行方式：
    python scripts/inspect_fixtures_table.py

输出：
1. fixtures 总数
2. source 分布
3. source_level 分布
4. confidence_level 分布
5. status 分布
6. api_fixture_id 去重后数量
7. fixture_id 去重后数量
8. home_team 或 away_team 为空的数量
9. 同一场比赛重复记录数量
10. 最近 updated_at
"""

import sys
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

from sqlalchemy import func
from app.db.database import SessionLocal
from app.models.agent_models import Fixture


def main():
    db = SessionLocal()
    try:
        print("=" * 60)
        print("fixtures 表检查报告")
        print("=" * 60)

        # 1. fixtures 总数
        total = db.query(Fixture).count()
        print(f"\n1. fixtures 总数: {total}")

        # 2. source 分布
        sources = db.query(Fixture.source, func.count(Fixture.id)) \
            .group_by(Fixture.source).all()
        print(f"\n2. source 分布:")
        for src, cnt in sources:
            print(f"   - {src or 'NULL'}: {cnt}")

        # 3. source_level 分布
        levels = db.query(Fixture.source_level, func.count(Fixture.id)) \
            .group_by(Fixture.source_level).all()
        print(f"\n3. source_level 分布:")
        for lvl, cnt in levels:
            print(f"   - {lvl or 'NULL'}: {cnt}")

        # 4. confidence_level 分布
        confs = db.query(Fixture.confidence_level, func.count(Fixture.id)) \
            .group_by(Fixture.confidence_level).all()
        print(f"\n4. confidence_level 分布:")
        for c, cnt in confs:
            print(f"   - {c or 'NULL'}: {cnt}")

        # 5. status 分布
        statuses = db.query(Fixture.status, func.count(Fixture.id)) \
            .group_by(Fixture.status).all()
        print(f"\n5. status 分布:")
        for s, cnt in statuses:
            print(f"   - {s or 'NULL'}: {cnt}")

        # 6. api_fixture_id 去重后数量
        api_ids = db.query(Fixture.api_fixture_id).filter(
            Fixture.api_fixture_id.isnot(None)
        ).distinct().count()
        print(f"\n6. api_fixture_id 去重后数量: {api_ids}")

        # 7. fixture_id 去重后数量
        fx_ids = db.query(Fixture.fixture_id).distinct().count()
        print(f"\n7. fixture_id 去重后数量: {fx_ids}")

        # 8. home_team 或 away_team 为空的数量
        empty_teams = db.query(Fixture).filter(
            (Fixture.home_team == "") | (Fixture.away_team == "") |
            (Fixture.home_team == None) | (Fixture.away_team == None)
        ).count()
        print(f"\n8. home_team 或 away_team 为空的数量: {empty_teams}")

        # 9. 同一场比赛重复记录数量
        dupes = db.query(Fixture.fixture_id, func.count(Fixture.id)) \
            .group_by(Fixture.fixture_id) \
            .having(func.count(Fixture.id) > 1).all()
        dupe_count = sum(c - 1 for _, c in dupes)
        print(f"\n9. 重复记录数量: {dupe_count}")
        if dupes:
            for fid, cnt in dupes[:5]:
                print(f"   - fixture_id={fid}: {cnt} 条")

        # 10. 最近 updated_at
        last = db.query(Fixture.updated_at).order_by(Fixture.updated_at.desc()).first()
        print(f"\n10. 最近 updated_at: {last[0] if last and last[0] else '无'}")

        # 重点判断
        print(f"\n{'=' * 60}")
        print("重点判断")
        print("=" * 60)

        fd_real = db.query(Fixture).filter(
            Fixture.source == "football_data",
            Fixture.source_level == "external_real",
            Fixture.api_fixture_id.isnot(None)
        ).count()
        print(f"\n- football_data + external_real + 有 api_fixture_id: {fd_real} 条")

        fd_real_all = db.query(Fixture).filter(
            Fixture.source == "football_data",
            Fixture.source_level == "external_real"
        ).count()
        print(f"- football_data + external_real（含无 api_fixture_id）: {fd_real_all} 条")

        if fd_real >= 104:
            print(f"\n[结论] canonical fixtures 应只使用 {fd_real} 条 football_data external_real 数据")
        elif fd_real > 0:
            print(f"\n[结论] football_data external_real 仅 {fd_real} 条，不足 104 条，需要兜底")
        else:
            print(f"\n[结论] 无 football_data external_real 数据")

    finally:
        db.close()


if __name__ == "__main__":
    main()
