"""
只读诊断脚本：列出淘汰赛阶段（特别是半决赛）的所有 fixture 记录。
用于排查重复数据问题。

安全保证：
- 只读，不修改任何数据
- 不输出 DATABASE_URL、密码或其他密钥
"""
import sys
import os
from pathlib import Path

project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.db.database import SessionLocal, DB_BACKEND
import app.models.schemas  # noqa: F401
import app.models.agent_models  # noqa: F401
from app.models.agent_models import Fixture


def _fmt(val, width=20):
    s = str(val) if val is not None else "NULL"
    return s[:width].ljust(width)


def main():
    print("=" * 100)
    print("Knockout Fixtures Diagnostic (read-only)")
    print("=" * 100)
    print(f"Database backend: {DB_BACKEND}")
    print()

    db = SessionLocal()
    try:
        # 1. 总览
        total = db.query(Fixture).count()
        print(f"Total fixtures in DB: {total}")
        print()

        # 2. 按 stage 分组统计
        from sqlalchemy import func
        stage_counts = (
            db.query(Fixture.stage, func.count(Fixture.id))
            .group_by(Fixture.stage)
            .all()
        )
        print("Stage distribution:")
        for stage, count in sorted(stage_counts, key=lambda x: -(x[1] or 0)):
            print(f"  {stage or 'NULL'}: {count}")
        print()

        # 3. 列出所有淘汰赛 fixture（非 group_stage）
        knockout_stages = [
            "semi_finals", "quarter_finals", "round_of_16",
            "round_of_32", "final", "third_place",
        ]
        knockout_fixtures = (
            db.query(Fixture)
            .filter(Fixture.stage.in_(knockout_stages))
            .order_by(Fixture.stage, Fixture.match_date)
            .all()
        )

        print(f"Knockout fixtures (non-group_stage): {len(knockout_fixtures)}")
        print()

        header = (
            f"{'PK':>5}  "
            f"{_fmt('fixture_id', 25)} "
            f"{_fmt('api_fixture_id', 18)} "
            f"{_fmt('stage', 18)} "
            f"{_fmt('home_team', 15)} "
            f"{_fmt('away_team', 15)} "
            f"{_fmt('status', 10)} "
            f"{_fmt('source', 20)} "
            f"{_fmt('source_level', 22)} "
            f"{'updated_at'}"
        )
        print(header)
        print("-" * len(header))

        for f in knockout_fixtures:
            line = (
                f"{f.id:>5}  "
                f"{_fmt(f.fixture_id, 25)} "
                f"{_fmt(f.api_fixture_id, 18)} "
                f"{_fmt(f.stage, 18)} "
                f"{_fmt(f.home_team, 15)} "
                f"{_fmt(f.away_team, 15)} "
                f"{_fmt(f.status, 10)} "
                f"{_fmt(f.source, 20)} "
                f"{_fmt(f.source_level, 22)} "
                f"{f.updated_at}"
            )
            print(line)

        print()

        # 4. 半决赛专项统计
        semis = db.query(Fixture).filter(Fixture.stage == "semi_finals").all()
        print(f"=== Semi-finals count: {len(semis)} ===")
        if len(semis) != 2:
            print(f"  WARNING: Expected 2, got {len(semis)}!")

        # 按逻辑比赛分组
        logical_pairs = {}
        for f in semis:
            pair = " vs ".join(sorted([f.home_team, f.away_team]))
            logical_pairs.setdefault(pair, []).append(f)

        print()
        print("Logical match grouping:")
        for pair, fixtures in sorted(logical_pairs.items()):
            print(f"  {pair}: {len(fixtures)} record(s)")
            for f in fixtures:
                print(
                    f"    PK={f.id}, fixture_id={f.fixture_id}, "
                    f"source={f.source}, source_level={f.source_level}, "
                    f"status={f.status}"
                )

        print()
        print("=" * 100)
        print("Diagnostic complete (read-only, no data modified)")
        print("=" * 100)

    finally:
        db.close()


if __name__ == "__main__":
    main()
