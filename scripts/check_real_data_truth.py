"""
真实数据来源验收脚本

必须以 fixtures 表为准：
1. fixtures_count > 0 且 source_level=external_real：真实实时数据通过
2. fixtures_count > 0 且 source_level=verified_cache：真实缓存数据通过，但不是实时刷新
3. fixtures_count = 0：真实数据不通过，source_level=unavailable

禁止出现：fixtures_count = 0 但真实数据验收通过
"""
import sys
import os
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# 确保项目根目录在 sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载 .env 文件
load_dotenv(project_root / ".env")


# ==================== 数据源分类规则 ====================

USER_MESSAGES = {
    "external_real": "比赛数据已更新。",
    "verified_cache": "暂时无法刷新，已使用最近一次真实缓存。",
    "manual_verified": "已使用已审核比赛数据。",
    "local_fallback": "当前数据未完全同步，结果仅供参考。",
    "llm_candidate": "当前缺少真实比赛数据，不能作为正式结果。",
    "unavailable": "当前比赛数据不足，请稍后重试。",
}


def check_fixtures_table():
    """检查 fixtures 表（使用 canonical 数据）"""
    try:
        from app.services.fixture_repository import FixtureRepository
        repo = FixtureRepository()
        
        # 使用 canonical 状态（不是表总状态）
        canonical_status = repo.get_canonical_status()
        # 也获取表总状态用于参考
        table_status = repo.get_status()
        
        fixtures_count = canonical_status.get("fixtures_count", 0)
        source = canonical_status.get("source", "unavailable")
        source_level = canonical_status.get("source_level", "unavailable")
        is_external_realtime = canonical_status.get("is_external_realtime", False)
        last_updated = canonical_status.get("last_updated")
        
        return {
            "table_exists": True,
            "fixtures_count": fixtures_count,
            "table_total_count": table_status.get("fixtures_count", 0),
            "source_distribution": table_status.get("source_distribution", {}),
            "source_level_distribution": table_status.get("source_level_distribution", {}),
            "confidence_distribution": table_status.get("confidence_distribution", {}),
            "needs_review_count": table_status.get("needs_review_count", 0),
            "source": source,
            "source_level": source_level,
            "is_external_realtime": is_external_realtime,
            "last_updated": last_updated,
        }
    except Exception as e:
        print(f"  [警告] 读取 fixtures 表失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            "table_exists": False,
            "fixtures_count": 0,
            "table_total_count": 0,
            "source_distribution": {},
            "source_level_distribution": {},
            "confidence_distribution": {},
            "needs_review_count": 0,
            "source": "unavailable",
            "source_level": "unavailable",
            "is_external_realtime": False,
            "last_updated": None,
        }


def main():
    print("=" * 60)
    print("真实数据来源验收")
    print("=" * 60)
    print()

    # 1. 检查 fixtures 表（唯一数据源）
    fixtures_info = check_fixtures_table()

    fixtures_count = fixtures_info["fixtures_count"]
    table_total_count = fixtures_info.get("table_total_count", fixtures_count)
    source = fixtures_info["source"]
    source_level = fixtures_info["source_level"]
    is_external_realtime = fixtures_info["is_external_realtime"]
    last_updated = fixtures_info["last_updated"]
    source_dist = fixtures_info["source_distribution"]
    source_level_dist = fixtures_info["source_level_distribution"]
    confidence_dist = fixtures_info["confidence_distribution"]
    needs_review_count = fixtures_info["needs_review_count"]

    # 2. 生成 user_message
    user_message = USER_MESSAGES.get(source_level, "当前比赛数据不足，请稍后重试。")

    # 3. 输出结果
    print(f"--- fixtures 表状态 ---")
    print(f"- fixtures 表存在: {fixtures_info['table_exists']}")
    print(f"- fixtures 表总数: {table_total_count}")
    print(f"- canonical fixtures_count: {fixtures_count}")
    print(f"- source 分布: {source_dist}")
    print(f"- source_level 分布: {source_level_dist}")
    print(f"- confidence_level 分布: {confidence_dist}")
    print(f"- needs_review_count: {needs_review_count}")
    print(f"- source: {source}")
    print(f"- source_level: {source_level}")
    print(f"- is_external_realtime: {is_external_realtime}")
    print(f"- last_updated: {last_updated or '无'}")
    print()

    print(f"--- 数据来源判定 ---")
    print(f"- 当前数据来源: {source}")
    print(f"- 数据级别: {source_level}")
    print(f"- 是否外部实时真实数据: {'是' if is_external_realtime else '否'}")
    print(f"- 页面应显示提示: {user_message}")
    print()

    # 4. 验收判断
    print(f"--- 验收结论 ---")
    if fixtures_count > 0 and source_level == "external_real":
        print("[OK] 真实实时数据通过")
        passed = True
    elif fixtures_count > 0 and source_level == "verified_cache":
        print("[OK] 真实缓存数据通过，但不是实时刷新")
        passed = True
    elif fixtures_count == 0:
        print("[FAIL] 真实数据不通过: fixtures 表为空")
        passed = False
    else:
        print(f"[FAIL] 真实数据不通过: source_level={source_level}")
        passed = False

    # 返回结果供综合验收使用
    return {
        "source": source,
        "source_level": source_level,
        "is_external_realtime": is_external_realtime,
        "fixtures_count": fixtures_count,
        "last_updated": last_updated,
        "user_message": user_message,
        "passed": passed,
    }


if __name__ == "__main__":
    result = main()
    print()
    print("=" * 60)
    if result["passed"]:
        print("[OK] 数据来源验收通过")
    else:
        print("[FAIL] 数据来源验收不通过")
    print("=" * 60)
    
    sys.exit(0 if result["passed"] else 1)
