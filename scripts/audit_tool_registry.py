"""
工具注册审计脚本

检查 ToolRegistry 中所有工具的注册状态、schema 完整性、返回格式统一性。

运行：python scripts/audit_tool_registry.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.tool_registry import ToolRegistry
from app.agents.tool_schemas import TOOL_SCHEMAS
from app.agents.tool_adapters import ADAPTER_TOOLS
from app.agents.agent_state import AgentState


def main():
    print("=" * 60)
    print("工具注册验收")
    print("=" * 60)

    registry = ToolRegistry(seed=42)

    # 核心 11 个工具列表
    CORE_11_TOOLS = [
        "get_cached_fixtures",
        "refresh_real_fixtures",
        "get_worldcup_teams",
        "load_historical_matches",
        "check_data_quality",
        "build_team_features",
        "predict_group_stage",
        "predict_knockout_bracket",
        "predict_champion",
        "build_visualization_payload",
        "generate_final_explanation",
    ]

    # 1. 打印所有已注册工具
    tool_names = registry.get_tool_names()
    print(f"\n- 已注册工具数量：{len(tool_names)}")
    for name in sorted(tool_names):
        print(f"  - {name}")

    # 2. 检查核心 11 个工具是否全部注册
    missing_core = [t for t in CORE_11_TOOLS if t not in tool_names]
    print(f"\n- 核心工具缺失：{missing_core if missing_core else '无'}")

    # 3. 检查 schema 完整性
    schemas = registry.get_schema()
    schema_names = {s["name"] for s in schemas}

    missing_schema = [name for name in tool_names if name not in schema_names]
    print(f"- 缺少 schema 的工具：{missing_schema if missing_schema else '无'}")

    # 4. 检查每个 schema 的必要字段
    required_fields = ["name", "description", "parameters", "returns"]
    incomplete_schemas = []
    for schema in schemas:
        missing = [f for f in required_fields if f not in schema]
        if missing:
            incomplete_schemas.append((schema["name"], missing))

    if incomplete_schemas:
        print(f"- Schema 不完整：")
        for name, missing in incomplete_schemas:
            print(f"    {name}: 缺少 {missing}")

    # 5. 检查 adapter 函数是否都存在
    missing_adapters = [name for name in tool_names if name not in ADAPTER_TOOLS]
    print(f"- callable 异常工具：{missing_adapters if missing_adapters else '无'}")

    # 6. 检查每个工具是否能被 AgentExecutor 调用（返回统一格式）
    print(f"\n返回格式检查：")
    state = AgentState(season=2026)
    format_errors = []

    for name in tool_names:
        try:
            result = registry.call(name, state=state)
            if not isinstance(result, dict):
                format_errors.append((name, "返回不是 dict"))
                continue
            required_keys = {"success", "data", "error_type", "message", "state_updates"}
            missing_keys = required_keys - set(result.keys())
            if missing_keys:
                format_errors.append((name, f"缺少字段: {missing_keys}"))
        except Exception as e:
            format_errors.append((name, f"异常: {e}"))

    print(f"- 返回格式异常工具：{[e[0] for e in format_errors] if format_errors else '无'}")

    # 7. 总结
    print("\n" + "=" * 60)
    print("验收结果")
    print("=" * 60)
    print(f"  已注册工具数量：{len(tool_names)}")
    print(f"  核心工具缺失：{missing_core if missing_core else '无'}")
    print(f"  缺少 schema 的工具：{missing_schema if missing_schema else '无'}")
    print(f"  callable 异常工具：{missing_adapters if missing_adapters else '无'}")
    print(f"  返回格式异常工具：{[e[0] for e in format_errors] if format_errors else '无'}")

    all_pass = (
        not missing_core
        and not missing_schema
        and not incomplete_schemas
        and not missing_adapters
        and not format_errors
    )

    if all_pass:
        print("\n  验收结果：通过 [OK]")
    else:
        print("\n  验收结果：不通过 [FAIL]")

    return all_pass


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
