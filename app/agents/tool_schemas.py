"""
工具 Function Calling Schema 定义

为每个工具定义 function calling schema，供 LLM Planner 使用。
每个 schema 包含：name, description, parameters, returns
"""

TOOL_SCHEMAS = [
    {
        "name": "get_cached_fixtures",
        "description": "读取数据库/缓存中的世界杯赛程和比分。优先使用缓存，避免重复调用外部 API。返回赛程列表、数据来源和数量。",
        "parameters": {
            "type": "object",
            "properties": {
                "season": {
                    "type": "integer",
                    "description": "世界杯赛季，例如 2026",
                }
            },
            "required": [],
        },
        "returns": {"fixtures": "list", "source": "str", "count": "int"},
    },
    {
        "name": "refresh_real_fixtures",
        "description": "尝试从 API-Sports 刷新真实赛程和比分。如果 API 限流，返回 rate_limited，不会重复重试。仅在缓存无数据时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "season": {
                    "type": "integer",
                    "description": "世界杯赛季，例如 2026",
                }
            },
            "required": [],
        },
        "returns": {"fixtures": "list", "error_type": "str|null", "source": "str"},
    },
    {
        "name": "get_worldcup_teams",
        "description": "获取世界杯参赛球队列表。优先使用缓存，缓存无数据时调用 API。返回球队信息。",
        "parameters": {
            "type": "object",
            "properties": {
                "season": {
                    "type": "integer",
                    "description": "世界杯赛季，例如 2026",
                }
            },
            "required": [],
        },
        "returns": {"teams": "list", "count": "int"},
    },
    {
        "name": "load_historical_matches",
        "description": "从本地 CSV 加载历史国家队比赛数据。包含日期、对阵双方、比分、赛事名称等。",
        "parameters": {
            "type": "object",
            "properties": {
                "start_year": {
                    "type": "integer",
                    "description": "起始年份，例如 2018",
                }
            },
            "required": [],
        },
        "returns": {"historical_matches": "list|dict", "count": "int"},
    },
    {
        "name": "check_data_quality",
        "description": "检查当前已采集的数据是否足够支撑预测。返回质量分数、缺失字段、是否可以进入预测阶段。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "returns": {"data_quality_score": "float", "can_predict": "bool", "missing_fields": "list"},
    },
    {
        "name": "build_team_features",
        "description": "根据已采集数据构建球队实力特征（Elo、FIFA排名、攻防评分、综合实力等）。需要先采集球队数据。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "returns": {"team_features": "dict", "count": "int"},
    },
    {
        "name": "predict_group_stage",
        "description": "预测世界杯小组赛结果。需要球队特征数据。返回小组赛预测和锦标赛中间结果。如果有真实数据则直接使用。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "returns": {"group_predictions": "list", "qualified_count": "int"},
    },
    {
        "name": "predict_knockout_bracket",
        "description": "根据小组赛结果推演淘汰赛（32强→16强→8强→半决赛→决赛），得出冠军和亚军。需要先完成小组赛预测。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "returns": {"knockout_predictions": "list", "champion": "str", "runner_up": "str"},
    },
    {
        "name": "predict_champion",
        "description": "计算冠军、亚军、夺冠概率。如果已有冠军预测则直接返回。需要先完成淘汰赛推演。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "returns": {"champion": "str", "runner_up": "str", "champion_probability": "float"},
    },
    {
        "name": "build_visualization_payload",
        "description": "构建页面展示数据。包括实力排行、小组摘要、淘汰赛对阵、决赛预测。需要先完成冠军预测。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "returns": {"power_ranking": "list", "knockout_bracket": "list", "final_prediction": "dict"},
    },
    {
        "name": "generate_final_explanation",
        "description": "生成冠军预测的完整中文解释文本。需要先完成冠军预测。",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "returns": {"explanation": "str"},
    },
]


def get_all_schemas() -> list[dict]:
    """返回所有工具的 schema 列表"""
    return TOOL_SCHEMAS


def get_schema_by_name(name: str) -> dict | None:
    """按名称查找 schema"""
    for schema in TOOL_SCHEMAS:
        if schema["name"] == name:
            return schema
    return None
