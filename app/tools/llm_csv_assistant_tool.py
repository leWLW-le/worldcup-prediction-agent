"""
智谱 AI 辅助 CSV 生成工具

允许智谱 AI 做：
- 根据 API-Sports 真实 teams 生成 team_aliases.csv
- 生成 team_ratings.csv 初始版本
- 导出 API cache CSV
- 标准化球队名称
- 生成 competition_weights.csv
- 标记 needs_review

禁止智谱 AI 做：
- 编造赛程、比分、FIFA ranking、Elo rating、身价
- 把 LLM 生成数据标记为 api-sports 或 real_result
- 覆盖 fixtures 表
"""

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
CACHE_DIR = DATA_DIR / "cache"


def _get_zhipu_client():
    """获取智谱 AI 客户端"""
    try:
        from zhipuai import ZhipuAI
        settings = get_settings()
        api_key = settings.OPENAI_API_KEY
        if not api_key:
            return None
        return ZhipuAI(api_key=api_key)
    except ImportError:
        logger.warning("[LLM CSV] zhipuai not installed")
        return None


def _call_llm(prompt: str, max_tokens: int = 2000) -> Optional[str]:
    """调用智谱 AI 生成内容"""
    client = _get_zhipu_client()
    if not client:
        return None
    try:
        settings = get_settings()
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL or "glm-4-flash",
            messages=[
                {"role": "system", "content": "你是一个数据整理助手。只输出 JSON 格式，不输出其他内容。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"[LLM CSV] LLM call failed: {e}")
        return None


def _ensure_dirs():
    """确保数据目录存在"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def generate_csv_template(csv_type: str) -> Dict[str, Any]:
    """生成 CSV 模板文件

    Args:
        csv_type: team_aliases | team_ratings | competition_weights

    Returns:
        {success, path, source, needs_review, rows, error}
    """
    _ensure_dirs()

    templates = {
        "team_aliases": {
            "path": DATA_DIR / "team_aliases.csv",
            "headers": ["team_name", "alias", "source", "needs_review"],
            "sample_rows": [
                ["TeamName", "Alias", "llm_generated_template", "true"],
            ],
        },
        "team_ratings": {
            "path": DATA_DIR / "team_ratings.csv",
            "headers": ["team_name", "elo_rating", "fifa_rank", "source", "needs_review"],
            "sample_rows": [
                ["TeamName", "1500", "50", "llm_generated_template", "true"],
            ],
        },
        "competition_weights": {
            "path": DATA_DIR / "competition_weights.csv",
            "headers": ["competition_name", "weight", "source", "needs_review"],
            "sample_rows": [
                ["FIFA World Cup", "1.0", "llm_generated_template", "true"],
                ["UEFA Euro", "0.8", "llm_generated_template", "true"],
                ["Copa America", "0.75", "llm_generated_template", "true"],
            ],
        },
    }

    tmpl = templates.get(csv_type)
    if not tmpl:
        return {"success": False, "path": None, "source": "llm_generated_template",
                "needs_review": True, "rows": 0, "error": f"Unknown csv_type: {csv_type}"}

    path = tmpl["path"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(tmpl["headers"])
        for row in tmpl["sample_rows"]:
            writer.writerow(row)

    return {
        "success": True,
        "path": str(path),
        "source": "llm_generated_template",
        "needs_review": True,
        "rows": len(tmpl["sample_rows"]),
        "error": None,
    }


def convert_api_response_to_csv_rows(data_type: str, api_response: Dict) -> Dict[str, Any]:
    """将 API-Sports 真实响应转换为 CSV 行

    Args:
        data_type: teams | fixtures | live
        api_response: APISportsTool 返回的完整响应

    Returns:
        {success, rows, source, path, error}
    """
    _ensure_dirs()

    if not api_response.get("success"):
        return {"success": False, "rows": 0, "source": "api-sports",
                "path": None, "error": api_response.get("error")}

    data = api_response.get("data", [])
    fetched_at = api_response.get("fetched_at", "")

    if data_type == "teams":
        path = CACHE_DIR / "worldcup_2026_teams_api.csv"
        headers = ["team_id", "team_name", "country", "founded", "logo_url", "source", "fetched_at"]
        rows = []
        for t in data:
            team = t.get("team", {})
            rows.append([
                team.get("id", ""),
                team.get("name", ""),
                team.get("country", ""),
                team.get("founded", ""),
                team.get("logo", ""),
                "api-sports",
                fetched_at,
            ])
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)

        return {"success": True, "rows": len(rows), "source": "api-sports",
                "path": str(path), "error": None}

    elif data_type == "fixtures":
        path = CACHE_DIR / "worldcup_2026_fixtures_api.csv"
        headers = ["fixture_id", "date", "round", "home_team", "away_team",
                    "home_score", "away_score", "status", "source", "fetched_at"]
        rows = []
        for fx in data:
            fixture = fx.get("fixture", {})
            teams = fx.get("teams", {})
            goals = fx.get("goals", {})
            league = fx.get("league", {})
            status = fixture.get("status", {})
            rows.append([
                fixture.get("id", ""),
                fixture.get("date", ""),
                league.get("round", ""),
                teams.get("home", {}).get("name", ""),
                teams.get("away", {}).get("name", ""),
                goals.get("home", ""),
                goals.get("away", ""),
                status.get("short", ""),
                "api-sports",
                fetched_at,
            ])
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)

        return {"success": True, "rows": len(rows), "source": "api-sports",
                "path": str(path), "error": None}

    elif data_type == "live":
        path = CACHE_DIR / "worldcup_2026_live_api.csv"
        headers = ["fixture_id", "date", "home_team", "away_team",
                    "home_score", "away_score", "status", "elapsed", "source", "fetched_at"]
        rows = []
        for fx in data:
            fixture = fx.get("fixture", {})
            teams = fx.get("teams", {})
            goals = fx.get("goals", {})
            status = fixture.get("status", {})
            rows.append([
                fixture.get("id", ""),
                fixture.get("date", ""),
                teams.get("home", {}).get("name", ""),
                teams.get("away", {}).get("name", ""),
                goals.get("home", ""),
                goals.get("away", ""),
                status.get("short", ""),
                status.get("elapsed", ""),
                "api-sports",
                fetched_at,
            ])
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)

        return {"success": True, "rows": len(rows), "source": "api-sports",
                "path": str(path), "error": None}

    return {"success": False, "rows": 0, "source": "api-sports",
            "path": None, "error": f"Unknown data_type: {data_type}"}


def normalize_team_names(rows: List[Dict], aliases: Optional[Dict] = None) -> List[Dict]:
    """标准化球队名称"""
    default_aliases = {
        "USA": "United States",
        "US": "United States",
        "England": "England",
        "Korea": "South Korea",
        "DR Congo": "DR Congo",
        "Cape Verde": "Cape Verde",
        "Ivory Coast": "Ivory Coast",
    }
    alias_map = {**default_aliases, **(aliases or {})}

    normalized = []
    for row in rows:
        name = row.get("team_name", "")
        canonical = alias_map.get(name, name)
        normalized.append({**row, "team_name": canonical, "original_name": name})
    return normalized


def generate_team_alias_candidates(api_teams: List[Dict]) -> Dict[str, Any]:
    """用智谱 AI 根据 API teams 生成 team_aliases 候选"""
    _ensure_dirs()
    path = DATA_DIR / "team_aliases.csv"

    team_names = [t.get("team", {}).get("name", "") for t in api_teams if t.get("team", {}).get("name")]
    if not team_names:
        return {"success": False, "path": None, "source": "llm_generated_candidate",
                "needs_review": True, "rows": 0, "error": "No team names provided"}

    prompt = f"""以下是 {len(team_names)} 支参加 2026 世界杯的球队名称：
{json.dumps(team_names, ensure_ascii=False)}

请为每支球队生成 1-2 个常见别名（如缩写、中文译名等）。
输出 JSON 数组格式：[{{"team_name": "xxx", "alias": "yyy"}}, ...]
只输出 JSON，不要其他内容。"""

    content = _call_llm(prompt)
    rows = []

    if content:
        try:
            content = content.strip()
            json_start = content.find('[')
            json_end = content.rfind(']') + 1
            if json_start >= 0 and json_end > json_start:
                parsed = json.loads(content[json_start:json_end])
                for item in parsed:
                    rows.append({
                        "team_name": item.get("team_name", ""),
                        "alias": item.get("alias", ""),
                        "source": "llm_generated_candidate",
                        "needs_review": "true",
                    })
        except Exception as e:
            logger.warning(f"[LLM CSV] Failed to parse LLM aliases: {e}")

    # 写入 CSV
    headers = ["team_name", "alias", "source", "needs_review"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for r in rows:
            writer.writerow([r["team_name"], r["alias"], r["source"], r["needs_review"]])

    return {
        "success": True,
        "path": str(path),
        "source": "llm_generated_candidate",
        "needs_review": True,
        "rows": len(rows),
        "error": None,
    }


def generate_competition_weights() -> Dict[str, Any]:
    """生成 competition_weights.csv"""
    _ensure_dirs()
    path = DATA_DIR / "competition_weights.csv"

    headers = ["competition_name", "weight", "source", "needs_review"]
    rows = [
        ["FIFA World Cup", "1.0", "llm_generated_template", "true"],
        ["UEFA European Championship", "0.8", "llm_generated_template", "true"],
        ["Copa America", "0.75", "llm_generated_template", "true"],
        ["UEFA Nations League", "0.5", "llm_generated_template", "true"],
        ["AFC Asian Cup", "0.6", "llm_generated_template", "true"],
        ["Africa Cup of Nations", "0.6", "llm_generated_template", "true"],
        ["CONCACAF Gold Cup", "0.55", "llm_generated_template", "true"],
        ["FIFA Confederations Cup", "0.7", "llm_generated_template", "true"],
        ["International Friendly", "0.3", "llm_generated_template", "true"],
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    return {"success": True, "path": str(path), "source": "llm_generated_template",
            "needs_review": True, "rows": len(rows), "error": None}


def validate_llm_generated_rows(rows: List[Dict]) -> Dict[str, Any]:
    """验证 LLM 生成的行是否符合规范"""
    issues = []
    for i, row in enumerate(rows):
        source = row.get("source", "")
        if source in ("api-sports", "real_result"):
            issues.append(f"Row {i}: LLM 生成数据不能标记为 source={source}")
        if not row.get("needs_review"):
            issues.append(f"Row {i}: LLM 生成数据必须 needs_review=true")
    return {
        "valid": len(issues) == 0,
        "issues": issues,
    }
