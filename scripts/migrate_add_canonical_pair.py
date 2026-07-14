"""
迁移脚本：为 fixtures 表添加 canonical_pair 列和唯一约束

严格迁移顺序（全部使用参数化原生 SQL，不依赖 ORM）：
  a. 检查 fixtures 表是否存在
  b. 检查 canonical_pair 列是否已存在
  c. 不存在时添加允许 NULL 的 canonical_pair 列
  d. 根据现有 home_team, away_team 回填 canonical_pair
  e. 检查并列出所有阶段的重复逻辑比赛
  f. dry-run 只输出保留和删除计划，不修改数据
  g. --apply 时在单个事务内执行去重
  h. 确认所有有效记录 canonical_pair 非空
  i. 创建唯一索引（PG: UNIQUE CONSTRAINT; SQLite: CREATE UNIQUE INDEX）
  j. 使用原生 SQL 验证结果

支持 SQLite 和 PostgreSQL。
幂等：重复运行安全。

用法：
  python scripts/migrate_add_canonical_pair.py           # 预览（dry-run）
  python scripts/migrate_add_canonical_pair.py --apply   # 执行迁移
"""

import sys
import io
import os
from pathlib import Path
from datetime import datetime

# Windows 控制台编码修复
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

# 确保项目根目录在 sys.path 中
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import text
from app.db.database import Base, engine, SessionLocal, DB_BACKEND

# ── 导入 compute_canonical_pair 但不导入 Fixture ORM 模型 ──
# 避免 ORM 在列不存在时 SELECT 失败
from app.models.agent_models import compute_canonical_pair

# source_level 优先级
SOURCE_LEVEL_PRIORITY = {
    "external_real": 3,
    "verified_cache": 2,
    "manual_verified": 2,
    "unverified_candidate": 1,
    "unavailable": 0,
}


# ════════════════════════════════════════════════════════════
# 工具函数（全部使用原生 SQL）
# ════════════════════════════════════════════════════════════

def _table_exists(session, table_name: str) -> bool:
    """检查表是否存在"""
    if DB_BACKEND == "sqlite":
        row = session.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=:t"
        ), {"t": table_name}).fetchone()
        return row is not None
    else:
        row = session.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = :t"
        ), {"t": table_name}).fetchone()
        return row is not None


def _column_exists(session, table_name: str, column_name: str) -> bool:
    """检查列是否存在"""
    if DB_BACKEND == "sqlite":
        rows = session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        return any(row[1] == column_name for row in rows)
    else:
        row = session.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ), {"t": table_name, "c": column_name}).fetchone()
        return row is not None


def _unique_index_exists(session, index_name: str) -> bool:
    """检查唯一索引/约束是否存在"""
    if DB_BACKEND == "sqlite":
        row = session.execute(text(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=:n"
        ), {"n": index_name}).fetchone()
        return row is not None
    else:
        row = session.execute(text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE constraint_name = :n AND constraint_type = 'UNIQUE'"
        ), {"n": index_name}).fetchone()
        return row is not None


def _query_all_fixtures(session):
    """原生 SQL 查询所有 fixtures（不依赖 canonical_pair 列）"""
    return session.execute(text(
        "SELECT id, fixture_id, home_team, away_team, stage, source, source_level, "
        "updated_at, fetched_at FROM fixtures"
    )).fetchall()


def _query_fixtures_by_stage(session, stage: str):
    """原生 SQL 按阶段查询 fixtures"""
    return session.execute(text(
        "SELECT id, fixture_id, home_team, away_team, stage, source, source_level, "
        "updated_at, fetched_at FROM fixtures WHERE stage = :stage"
    ), {"stage": stage}).fetchall()


def _row_rank(row):
    """排名越高越优先保留。row: (id, fixture_id, home, away, stage, source, source_level, updated_at, fetched_at)"""
    fid = str(row[1] or '')
    has_real_id = not fid.startswith("seed_") if fid else False
    sl = SOURCE_LEVEL_PRIORITY.get(row[6] or '', 0)
    updated = row[7] or row[8]  # updated_at or fetched_at
    # 处理字符串日期
    if isinstance(updated, str):
        try:
            updated = datetime.fromisoformat(updated)
        except Exception:
            updated = datetime.min
    return (has_real_id, sl, updated or datetime.min)


def _find_duplicates(session):
    """找出所有阶段的逻辑重复记录。

    返回: {canonical_pair: [rows...]} 只包含有重复的组。
    """
    rows = _query_all_fixtures(session)
    groups = {}
    for row in rows:
        home = row[2] or ""
        away = row[3] or ""
        stage = row[4] or ""
        cp = compute_canonical_pair(home, away)
        key = (stage, cp)
        groups.setdefault(key, []).append(row)

    # 只返回有重复的组
    return {k: v for k, v in groups.items() if len(v) > 1}


# ════════════════════════════════════════════════════════════
# 迁移步骤
# ════════════════════════════════════════════════════════════

def step_a_check_table(session) -> bool:
    """a. 检查 fixtures 表是否存在"""
    print("\n[a] Check fixtures table exists")
    exists = _table_exists(session, "fixtures")
    if exists:
        count = session.execute(text("SELECT COUNT(*) FROM fixtures")).scalar()
        print(f"    OK: fixtures table exists ({count} rows)")
    else:
        print("    SKIP: fixtures table does not exist, nothing to migrate")
    return exists


def step_b_check_column(session) -> bool:
    """b. 检查 canonical_pair 列是否已存在"""
    print("\n[b] Check canonical_pair column")
    exists = _column_exists(session, "fixtures", "canonical_pair")
    if exists:
        print("    Already exists")
    else:
        print("    Not found — needs to be added")
    return exists


def step_c_add_column(session, dry_run: bool) -> bool:
    """c. 添加允许 NULL 的 canonical_pair 列"""
    print("\n[c] Add canonical_pair column (nullable)")
    if _column_exists(session, "fixtures", "canonical_pair"):
        print("    Already exists, skipped")
        return True

    if dry_run:
        print("    [DRY-RUN] Would execute: ALTER TABLE fixtures ADD COLUMN canonical_pair VARCHAR(200)")
        return True

    try:
        session.execute(text(
            "ALTER TABLE fixtures ADD COLUMN canonical_pair VARCHAR(200)"
        ))
        session.commit()
        print("    Added canonical_pair VARCHAR(200) NULL")
        return True
    except Exception as e:
        print(f"    ERROR: {e}")
        session.rollback()
        return False


def step_d_backfill(session, dry_run: bool) -> int:
    """d. 回填 canonical_pair"""
    print("\n[d] Backfill canonical_pair values")
    rows = _query_all_fixtures(session)
    null_count = sum(1 for r in rows if True)  # 列可能还不存在，先都计算
    updated = 0

    # 先检查哪些已经有值
    if _column_exists(session, "fixtures", "canonical_pair"):
        already_set = session.execute(text(
            "SELECT COUNT(*) FROM fixtures WHERE canonical_pair IS NOT NULL"
        )).scalar()
        need_update = len(rows) - already_set
        print(f"    Total: {len(rows)}, already set: {already_set}, need update: {need_update}")
    else:
        need_update = len(rows)
        print(f"    Column not yet available, would compute {need_update} values")

    for row in rows:
        home = row[2] or ""
        away = row[3] or ""
        cp = compute_canonical_pair(home, away)

        if dry_run:
            if need_update <= 20:  # 只详细输出少量记录
                print(f"    [DRY-RUN] id={row[0]} {row[1]}: {home} vs {away} -> {cp}")
        else:
            session.execute(
                text("UPDATE fixtures SET canonical_pair = :cp WHERE id = :id"),
                {"cp": cp, "id": row[0]}
            )
        updated += 1

    if need_update <= 20:
        pass  # 已逐行输出
    else:
        print(f"    {'[DRY-RUN] Would update' if dry_run else 'Updated'} {updated} record(s)")

    if not dry_run and updated > 0:
        session.commit()

    return updated


def step_e_list_duplicates(session) -> dict:
    """e. 检查并列出重复逻辑比赛"""
    print("\n[e] Check for duplicate logical matches")
    dupes = _find_duplicates(session)

    if not dupes:
        print("    No duplicates found")
        return dupes

    for (stage, cp), rows in dupes.items():
        print(f"\n    Stage={stage}, Pair={cp}")
        ranked = sorted(rows, key=_row_rank, reverse=True)
        for i, r in enumerate(ranked):
            tag = "KEEP" if i == 0 else "DELETE"
            print(f"      [{tag}] id={r[0]} fixture_id={r[1]} "
                  f"source={r[5]} source_level={r[6]}")

    total_dup = sum(len(v) - 1 for v in dupes.values())
    print(f"\n    Total duplicate groups: {len(dupes)}, records to delete: {total_dup}")
    return dupes


def step_f_dryrun_plan(dupes: dict):
    """f. dry-run 输出保留和删除计划"""
    if not dupes:
        print("\n[f] Dry-run plan: nothing to delete")
        return

    print("\n[f] Dry-run plan (no data modified):")
    for (stage, cp), rows in dupes.items():
        ranked = sorted(rows, key=_row_rank, reverse=True)
        keeper = ranked[0]
        print(f"    {stage} | {cp}")
        print(f"      KEEP   id={keeper[0]} fixture_id={keeper[1]} "
              f"(real_api={not str(keeper[1] or '').startswith('seed_')}, "
              f"source_level={keeper[6]})")
        for r in ranked[1:]:
            print(f"      DELETE id={r[0]} fixture_id={r[1]} "
                  f"(real_api={not str(r[1] or '').startswith('seed_')}, "
                  f"source_level={r[6]})")


def step_g_apply_dedup(session, dupes: dict) -> int:
    """g. --apply 时在单个事务内执行去重"""
    print("\n[g] Apply deduplication (single transaction)")

    if not dupes:
        print("    Nothing to delete")
        return 0

    to_delete_ids = []
    for (stage, cp), rows in dupes.items():
        ranked = sorted(rows, key=_row_rank, reverse=True)
        for r in ranked[1:]:
            to_delete_ids.append(r[0])

    try:
        for did in to_delete_ids:
            session.execute(text("DELETE FROM fixtures WHERE id = :id"), {"id": did})
        session.commit()
        print(f"    Deleted {len(to_delete_ids)} duplicate(s) in transaction")
        return len(to_delete_ids)
    except Exception as e:
        session.rollback()
        print(f"    ERROR (rolled back): {e}")
        raise


def step_h_verify_no_null(session) -> bool:
    """h. 确认所有记录 canonical_pair 非空"""
    print("\n[h] Verify no NULL canonical_pair")
    null_count = session.execute(text(
        "SELECT COUNT(*) FROM fixtures WHERE canonical_pair IS NULL"
    )).scalar()
    total = session.execute(text("SELECT COUNT(*) FROM fixtures")).scalar()
    print(f"    Total: {total}, NULL canonical_pair: {null_count}")
    if null_count == 0:
        print("    OK: all records have canonical_pair")
        return True
    else:
        print(f"    WARNING: {null_count} records still have NULL canonical_pair")
        return False


def step_i_create_unique_index(session, dry_run: bool) -> bool:
    """i. 创建唯一索引

    PostgreSQL: ALTER TABLE ADD CONSTRAINT ... UNIQUE
    SQLite: CREATE UNIQUE INDEX (如果不存在)
    """
    print("\n[i] Create unique index on (stage, canonical_pair)")
    index_name = "uq_fixture_stage_pair"

    if _unique_index_exists(session, index_name):
        print(f"    Already exists: {index_name}")
        return True

    if dry_run:
        if DB_BACKEND == "postgresql":
            print(f"    [DRY-RUN] Would execute: "
                  f"ALTER TABLE fixtures ADD CONSTRAINT {index_name} UNIQUE (stage, canonical_pair)")
        else:
            print(f"    [DRY-RUN] Would execute: "
                  f"CREATE UNIQUE INDEX {index_name} ON fixtures (stage, canonical_pair)")
        return True

    try:
        if DB_BACKEND == "postgresql":
            session.execute(text(
                f"ALTER TABLE fixtures ADD CONSTRAINT {index_name} "
                f"UNIQUE (stage, canonical_pair)"
            ))
        else:
            # SQLite: CREATE UNIQUE INDEX
            session.execute(text(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} "
                f"ON fixtures (stage, canonical_pair)"
            ))
        session.commit()
        print(f"    Created: {index_name} on (stage, canonical_pair)")
        return True
    except Exception as e:
        print(f"    ERROR: {e}")
        session.rollback()
        return False


def step_j_verify(session, dry_run: bool):
    """j. 使用原生 SQL 验证结果"""
    print("\n[j] Final verification")

    total = session.execute(text("SELECT COUNT(*) FROM fixtures")).scalar()
    print(f"    Total fixtures: {total}")

    col_exists = _column_exists(session, "fixtures", "canonical_pair")

    if col_exists:
        semis = session.execute(text(
            "SELECT fixture_id, home_team, away_team, canonical_pair, source "
            "FROM fixtures WHERE stage = 'semi_finals'"
        )).fetchall()
        null_cp = session.execute(text(
            "SELECT COUNT(*) FROM fixtures WHERE canonical_pair IS NULL"
        )).scalar()

        print(f"    Semi-final fixtures: {len(semis)}")
        print(f"    NULL canonical_pair: {null_cp}")

        for s in semis:
            print(f"      {s[0]}: {s[1]} vs {s[2]} (cp={s[3]}, source={s[4]})")

        ok = True
        if len(semis) != 2:
            print(f"    FAIL: expected 2 semi-finals, got {len(semis)}")
            ok = False
        if null_cp > 0:
            print(f"    FAIL: {null_cp} records with NULL canonical_pair")
            ok = False
        if ok:
            print("    PASS: 2 semi-finals, all canonical_pair set")
        return ok
    else:
        # 列还不存在（dry-run 模式）
        semis = session.execute(text(
            "SELECT fixture_id, home_team, away_team, source "
            "FROM fixtures WHERE stage = 'semi_finals'"
        )).fetchall()
        print(f"    Semi-final fixtures: {len(semis)} (canonical_pair column not yet created)")
        for s in semis:
            print(f"      {s[0]}: {s[1]} vs {s[2]} (source={s[3]})")

        if dry_run:
            print("    [DRY-RUN] Verification deferred to --apply")
            return True
        else:
            print("    FAIL: canonical_pair column missing after apply")
            return False


# ════════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════════

def main():
    dry_run = "--apply" not in sys.argv

    print("=" * 60)
    print("Migration: canonical_pair column + unique index")
    print(f"Backend : {DB_BACKEND}")
    print(f"Mode    : {'APPLY' if not dry_run else 'DRY-RUN (no data modified)'}")
    print("=" * 60)

    session = SessionLocal()
    try:
        # a. 检查表
        if not step_a_check_table(session):
            print("\nNothing to migrate.")
            return

        # b. 检查列
        col_exists = step_b_check_column(session)

        # c. 添加列
        if not col_exists:
            if not step_c_add_column(session, dry_run):
                print("\nMigration failed at step [c]")
                return

        # d. 回填
        step_d_backfill(session, dry_run)

        # e. 列出重复
        dupes = step_e_list_duplicates(session)

        # f. dry-run 计划
        if dry_run:
            step_f_dryrun_plan(dupes)

        # g. 执行去重
        if not dry_run and dupes:
            step_g_apply_dedup(session, dupes)

        # h. 验证无 NULL
        if not dry_run:
            step_h_verify_no_null(session)

        # i. 创建唯一索引
        step_i_create_unique_index(session, dry_run)

        # j. 最终验证
        step_j_verify(session, dry_run)

        print("\n" + "=" * 60)
        if dry_run:
            print("DRY-RUN complete. No data was modified.")
            print("Run with --apply to execute migration.")
        else:
            print("Migration complete!")
        print("=" * 60)

    except Exception as e:
        session.rollback()
        print(f"\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()
