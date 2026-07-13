"""
工具注册中心

注册所有 Agent 可用工具，提供统一的调用接口。
支持：has_tool(name)、get_schema()、call(name, **kwargs)

工具来源：
- tool_adapters.py 中的 adapter 函数（统一返回格式）
- 每个工具都有完整的 ToolSpec: name, description, parameters, returns, callable
"""

import logging
from typing import Any, Dict, List, Optional

from app.agents.tool_schemas import TOOL_SCHEMAS, get_schema_by_name
from app.agents.tool_adapters import ADAPTER_TOOLS

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册中心"""

    def __init__(self, seed: int | None = 42):
        self.seed = seed
        self._tool_map: Dict[str, callable] = {}
        self._schema_map: Dict[str, dict] = {}
        self._register_all_tools()

    def _register_all_tools(self):
        """注册所有工具（从 adapter 层）"""
        # 注册 schema
        for schema in TOOL_SCHEMAS:
            self._schema_map[schema["name"]] = schema

        # 注册 adapter 工具函数
        for name, fn in ADAPTER_TOOLS.items():
            self._tool_map[name] = fn

    def has_tool(self, name: str) -> bool:
        """检查工具是否存在"""
        return name in self._tool_map

    def get_schema(self) -> List[Dict[str, Any]]:
        """返回所有工具的 schema"""
        return list(self._schema_map.values())

    def get_tool_names(self) -> List[str]:
        """返回所有工具名称"""
        return list(self._tool_map.keys())

    def call(self, name: str, state=None, **kwargs) -> Dict[str, Any]:
        """
        调用工具。

        Args:
            name: 工具名称
            state: AgentState（所有 adapter 都需要访问状态）
            **kwargs: 工具参数

        Returns:
            统一格式：
            {
                "success": bool,
                "data": Any,
                "error_type": str|None,
                "message": str,
                "state_updates": dict,
            }
        """
        if name not in self._tool_map:
            return {
                "success": False,
                "data": None,
                "error_type": "tool_not_found",
                "message": f"工具 '{name}' 不存在。可用工具: {list(self._tool_map.keys())}",
                "state_updates": {},
            }
        try:
            return self._tool_map[name](state=state, **kwargs)
        except Exception as e:
            logger.error(f"[ToolRegistry] 工具 '{name}' 执行异常: {e}", exc_info=True)
            return {
                "success": False,
                "data": None,
                "error_type": "exception",
                "message": str(e),
                "state_updates": {},
            }
