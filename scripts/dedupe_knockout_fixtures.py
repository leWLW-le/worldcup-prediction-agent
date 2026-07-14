"""
一次性安全清理脚本：去除淘汰赛阶段（特别是半决赛）的重复 fixture 记录。

安全保证：
- 默认只预览（dry-run），不修改任何数据
- 必须提供 --apply 参数才会实际执行删除
- 使用数据库事务
- 只处理当前届赛事（2026）的 semi_finals
- 不删除历史比赛、不删除球队、不清空预测记录
- 不使用 drop_all

用法：
  python scripts/dedupe_knockout_fixtures.py          # 只预览
  python scripts/dedupe_knockout_fixtures.py --apply   # 实际执行
"""
import argparse
import sys
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.db.database import SessionLocal, DB_BACKEND
import app.models.schemas  # noqa: F401
import app.models.agent_models  # noqa: F401
from app.models.agent_models import Fixture


# 半决赛规范记录
CANONICAL_SEMI_FINALS = {
    frozenset(["France", "Spain"]),
    frozenset(["England", "Argentina"]),
}


def _canonical_pair(home: str, away: str) -> str:
    """生成规范化的球队配对键"""
    return " vs ".join(sorted([home.strip(), away.strip()]))


def _fixture_priority(f: Fixture) -> tuple:
    """
    计算 fixture 的保留优先级。返回值越高越优先保留。

    优先级规则：
    1. 有真实外部 API fixture_id（不以 seed_ 开头）> 种子记录
    2. source_level 越高越好
    3. 数据字段越完整越好
    4. updated_at 越新越好
    """
    source_level_priority = {
        "external_real": 3,
        "verified_cache": 2,
        "manual_verified": 2,
        "unverified_candidate": 1,
        "unavailable": 0,
    }

    # 有真实 API ID（非种子）
    has_real_api_id = (
        f.fixture_id
        and not f.fixture_id.startswith("seed_")
    )

    # source_level 优先级
    sl_priority = source_level_priority.get(f.source_level or "", 0)

    # 数据完整度（非空字段计数）
    completeness = sum(
        1 for v in [
            f.home_team, f.away_team, f.stage, f.status,
            f.match_date, f.home_score, f.away_score,
            f.winner, f.source, f.api_fixture_id,
        ]
        if v is not None
    )

    # 时间戳
    ts = f.updated_at or f.fetched_at or datetime.min

    return (has_real_api_id, sl_priority, completeness, ts)


def main():
    parser = argparse.ArgumentParser(description="Deduplicate knockout fixtures")
    parser.add_argument(
        "--apply", action="store_true",
        help="实际执行删除（默认只预览）",
    )
    args = parser.parse_args()

    is_dry_run = not args.apply

    print("=" * 80)
    if is_dry_run:
        print("Dedup Knockout Fixtures — DRY RUN (no changes)")
    else:
        print("Dedup Knockout Fixtures — APPLY MODE (will delete duplicates)")
    print("=" * 80)
    print(f"Database backend: {DB_BACKEND}")
    print()

    db = SessionLocal()
    try:
        # 1. 查询所有半决赛记录
        semis = (
            db.query(Fixture)
            .filter(Fixture.stage == "semi_finals")
            .order_by(Fixture.id)
            .all()
        )

        print(f"Total semi_finals records: {len(semis)}")
        if len(semis) == 0:
            print("No semi_finals found. Nothing to do.")
            return

        # 2. 按逻辑比赛分组
        groups = defaultdict(list)
        for f in semis:
            pair = _canonical_pair(f.home_team, f.away_team)
            groups[pair].append(f)

        print(f"Logical match groups: {len(groups)}")
        print()

        to_delete = []
        to_keep = []

        for pair, fixtures in sorted(groups.items()):
            print(f"--- {pair} ({len(fixtures)} record(s)) ---")

            # 检查是否是规范比赛
            team_set = frozenset(pair.split(" vs "))
            is_canonical = team_set in CANONICAL_SEMI_FINALS

            if not is_canonical:
                print(f"  WARNING: Not a canonical semi-final match. Keeping all records.")
                to_keep.extend(fixtures)
                continue

            # 按优先级排序，保留最高优先级的记录
            ranked = sorted(fixtures, key=_fixture_priority, reverse=True)
            keeper = ranked[0]
            duplicates = ranked[1:]

            print(f"  KEEP: PK={keeper.id}, fixture_id={keeper.fixture_id}, "
                  f"source={keeper.source}, source_level={keeper.source_level}")
            to_keep.append(keeper)

            for dup in duplicates:
                print(f"  DELETE: PK={dup.id}, fixture_id={dup.fixture_id}, "
                      f"source={dup.source}, source_level={dup.source_level}")
                to_delete.append(dup)

        print()
        print(f"Summary: keep={len(to_keep)}, delete={len(to_delete)}")
        print()

        if not to_delete:
            print("No duplicates found. Database is clean.")
            return

        if is_dry_run:
            print("DRY RUN: No changes made. Run with --apply to execute.")
            return

        # 3. 执行删除（事务保护）
        print("Executing deletion...")
        try:
            delete_ids = [f.id for f in to_delete]
            db.query(Fixture).filter(Fixture.id.in_(delete_ids)).delete(
                synchronize_session="fetch"
            )
            db.commit()
            print(f"Deleted {len(delete_ids)} duplicate record(s).")
        except Exception as e:
            db.rollback()
            print(f"ERROR: Deletion failed, transaction rolled back: {e}")
            raise

        # 4. 验证
        remaining_semis = (
            db.query(Fixture)
            .filter(Fixture.stage == "semi_finals")
            .all()
        )
        print()
        print(f"Post-cleanup semi_finals count: {len(remaining_semis)}")

        if len(remaining_semis) == 2:
            print("OK: Exactly 2 semi-finals remaining.")
            for f in remaining_semis:
                pair = _canonical_pair(f.home_team, f.away_team)
                print(f"  {pair}: PK={f.id}, fixture_id={f.fixture_id}")
        else:
            print(f"WARNING: Expected 2, got {len(remaining_semis)}. Manual review needed.")

        print()
        print("=" * 80)
        print("Dedup complete.")
        print("=" * 80)

    except Exception as e:
        print(f"FATAL: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
