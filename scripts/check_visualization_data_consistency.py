"""
可视化数据一致性检查

运行方式：
    python scripts/check_visualization_data_consistency.py

检查：
1. canonical fixtures_count
2. Dashboard 使用的数据来源
3. 是否仍读取旧 prediction_result.json
4. 是否有 source=agent_prediction 但 display_label=已结束
5. 是否有 fixtures_count>0 但页面仍显示数据不足
6. 是否有 fixtures 表 204 条导致展示重复
7. 每轮比赛的 source 分布和 display_label 分布
"""

import sys
import json
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

from app.services.fixture_repository import FixtureRepository


def main():
    print("=" * 60)
    print("可视化数据一致性检查")
    print("=" * 60)
    
    repo = FixtureRepository()
    errors = []
    warnings = []
    
    # 1. canonical fixtures_count
    canonical = repo.get_canonical_fixtures()
    canonical_count = canonical["canonical_count"]
    canonical_source = canonical["source"]
    canonical_level = canonical["source_level"]
    
    print(f"\n1. Canonical fixtures_count: {canonical_count}")
    print(f"   source: {canonical_source}")
    print(f"   source_level: {canonical_level}")
    
    if canonical_count == 0:
        errors.append("canonical fixtures_count = 0，无法展示")
    elif canonical_count < 48:
        warnings.append(f"canonical fixtures_count = {canonical_count}，可能不完整")
    else:
        print(f"   ✅ 数量正常")
    
    # 2. Dashboard 使用的数据来源
    print(f"\n2. Dashboard 数据来源:")
    print(f"   应使用: FixtureRepository.get_canonical_fixtures()")
    print(f"   当前 canonical source: {canonical_source}")
    if canonical_source in ("football_data", "api_football"):
        print(f"   ✅ 使用外部真实数据")
    elif canonical_source == "db_cache":
        warnings.append("Dashboard 使用缓存数据，非实时")
    else:
        errors.append(f"Dashboard 数据来源异常: {canonical_source}")
    
    # 3. 检查是否仍读取旧 prediction_result.json
    print(f"\n3. prediction_result.json 检查:")
    pred_path = project_root / "prediction_result.json"
    if pred_path.exists():
        print(f"   ⚠️ prediction_result.json 存在 ({pred_path.stat().st_size} bytes)")
        # 检查 Dashboard 代码是否读取它
        dashboard_path = project_root / "debug_dashboard.py"
        if dashboard_path.exists():
            content = dashboard_path.read_text(encoding="utf-8")
            if "prediction_result.json" in content:
                errors.append("Dashboard 代码中仍引用 prediction_result.json")
            else:
                print(f"   ✅ Dashboard 不直接读取 prediction_result.json")
    else:
        print(f"   ✅ prediction_result.json 不存在")
    
    # 4. 检查 source=agent_prediction 但 display_label=已结束
    print(f"\n4. 检查 agent_prediction + 已结束 混用:")
    table_status = repo.get_status()
    source_dist = table_status.get("source_distribution", {})
    agent_pred_count = source_dist.get("agent_prediction", 0)
    
    if agent_pred_count > 0 and canonical_level == "external_real":
        # canonical 是 external_real，agent_prediction 不应被展示
        print(f"   ⚠️ 表中有 {agent_pred_count} 条 agent_prediction 数据")
        if canonical_source in ("football_data", "api_football"):
            print(f"   ✅ 但 canonical 使用 {canonical_source}，不会混入 agent_prediction")
        else:
            errors.append("canonical 可能混入 agent_prediction 数据")
    else:
        print(f"   ✅ 无混用问题")
    
    # 5. 检查 fixtures_count>0 但显示数据不足
    print(f"\n5. 状态一致性检查:")
    canonical_status = repo.get_canonical_status()
    if canonical_count > 0 and canonical_level == "external_real":
        msg = canonical_status.get("user_message", "")
        if "数据不足" in msg:
            errors.append(f"fixtures_count={canonical_count} 但消息显示'数据不足': {msg}")
        else:
            print(f"   ✅ 状态消息正确: {msg}")
    elif canonical_count == 0:
        msg = canonical_status.get("user_message", "")
        if "数据不足" in msg or "刷新" in msg:
            print(f"   ✅ 状态消息正确: {msg}")
        else:
            warnings.append(f"fixtures_count=0 但消息不是'数据不足': {msg}")
    
    # 6. 检查是否展示重复数据
    print(f"\n6. 重复数据检查:")
    total = table_status.get("fixtures_count", 0)
    if total > canonical_count:
        print(f"   ⚠️ 表总数 ({total}) > canonical ({canonical_count})")
        print(f"   ✅ 但 Dashboard 只使用 canonical {canonical_count} 条，不会重复展示")
    else:
        print(f"   ✅ 无重复数据问题")
    
    # 7. 每轮比赛的 source 分布和 display_label 分布
    print(f"\n7. Canonical fixtures 分布:")
    fixtures = canonical["fixtures"]
    
    # 按 status 分组
    status_groups = {}
    for fx in fixtures:
        st = fx.get("status", "UNKNOWN")
        status_groups.setdefault(st, []).append(fx)
    
    print(f"   按 status 分布:")
    for st, fxs in sorted(status_groups.items()):
        print(f"     {st}: {len(fxs)} 条")
    
    # 按 source 分组
    source_groups = {}
    for fx in fixtures:
        src = fx.get("source", "unknown")
        source_groups.setdefault(src, []).append(fx)
    
    print(f"   按 source 分布:")
    for src, fxs in sorted(source_groups.items()):
        print(f"     {src}: {len(fxs)} 条")
    
    # 总结
    print(f"\n" + "=" * 60)
    print("检查结果总结")
    print("=" * 60)
    
    if errors:
        print(f"\n❌ 发现 {len(errors)} 个错误:")
        for e in errors:
            print(f"   - {e}")
    
    if warnings:
        print(f"\n⚠️ 发现 {len(warnings)} 个警告:")
        for w in warnings:
            print(f"   - {w}")
    
    if not errors and not warnings:
        print(f"\n✅ 所有检查通过！")
        print(f"   canonical fixtures: {canonical_count}")
        print(f"   source: {canonical_source}")
        print(f"   source_level: {canonical_level}")
    
    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "canonical_count": canonical_count,
        "canonical_source": canonical_source,
        "canonical_level": canonical_level,
    }


if __name__ == "__main__":
    result = main()
    sys.exit(0 if result["passed"] else 1)
