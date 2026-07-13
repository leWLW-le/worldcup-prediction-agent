"""
本地数据初始化服务

从 API-Sports 拉取真实数据，导出 CSV，可选用智谱 AI 辅助整理。
所有 LLM 生成数据标记 source / needs_review。
"""

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.tools.api_sports_tool import APISportsTool
from app.tools.llm_csv_assistant_tool import (
    convert_api_response_to_csv_rows,
    generate_csv_template,
    generate_team_alias_candidates,
    generate_competition_weights,
    _ensure_dirs,
    DATA_DIR,
    CACHE_DIR,
)

logger = logging.getLogger(__name__)

MANIFEST_PATH = DATA_DIR / "data_manifest.json"


def bootstrap_local_data(season: int = 2026, use_llm: bool = True) -> Dict[str, Any]:
    """主入口：拉取 API 数据 → 导出 CSV → 可选 LLM 整理 → 生成 manifest"""

    _ensure_dirs()

    settings = get_settings()
    api = APISportsTool()

    api_key_detected = api.api_key_detected
    zhipu_key_detected = bool(settings.OPENAI_API_KEY)
    llm_assisted = False
    warnings: List[str] = []
    errors: List[str] = []
    csv_manifest: List[Dict] = []

    # ── 1. 拉取 API-Sports 真实数据 ──
    teams_resp = api.get_worldcup_teams(season) if api_key_detected else None
    fixtures_resp = api.get_worldcup_fixtures(season) if api_key_detected else None
    live_resp = api.get_live_fixtures() if api_key_detected else None

    if not api_key_detected:
        warnings.append("APISPORTS_KEY / API_FOOTBALL_KEY 未配置，仅生成模板")

    # ── 2. 导出 API cache CSV ──
    if teams_resp and teams_resp.get("success"):
        r = convert_api_response_to_csv_rows("teams", teams_resp)
        csv_manifest.append({
            "file": r.get("path", ""),
            "rows": r.get("rows", 0),
            "source": "api-sports",
            "needs_manual_review": False,
            "warnings": [],
            "errors": [],
        })
    else:
        if api_key_detected:
            warnings.append(f"teams API 失败: {teams_resp.get('error') if teams_resp else 'N/A'}")

    if fixtures_resp and fixtures_resp.get("success"):
        r = convert_api_response_to_csv_rows("fixtures", fixtures_resp)
        csv_manifest.append({
            "file": r.get("path", ""),
            "rows": r.get("rows", 0),
            "source": "api-sports",
            "needs_manual_review": False,
            "warnings": [],
            "errors": [],
        })
    else:
        if api_key_detected:
            warnings.append(f"fixtures API 失败: {fixtures_resp.get('error') if fixtures_resp else 'N/A'}")

    if live_resp and live_resp.get("success"):
        r = convert_api_response_to_csv_rows("live", live_resp)
        csv_manifest.append({
            "file": r.get("path", ""),
            "rows": r.get("rows", 0),
            "source": "api-sports",
            "needs_manual_review": False,
            "warnings": [],
            "errors": [],
        })
    else:
        if api_key_detected:
            warnings.append(f"live API 失败: {live_resp.get('error') if live_resp else 'N/A'}")

    # ── 3. LLM 辅助整理 ──
    if use_llm and zhipu_key_detected:
        llm_assisted = True

        # team_aliases
        if teams_resp and teams_resp.get("success") and teams_resp.get("data"):
            alias_result = generate_team_alias_candidates(teams_resp["data"])
            csv_manifest.append({
                "file": alias_result.get("path", ""),
                "rows": alias_result.get("rows", 0),
                "source": alias_result.get("source", "llm_generated_candidate"),
                "needs_manual_review": True,
                "warnings": ["LLM 生成候选，需人工审核"],
                "errors": [],
            })
        else:
            # 无 API 数据，生成空模板
            tmpl = generate_csv_template("team_aliases")
            csv_manifest.append({
                "file": tmpl.get("path", ""),
                "rows": tmpl.get("rows", 0),
                "source": "llm_generated_template",
                "needs_manual_review": True,
                "warnings": ["无 API 数据，仅生成模板"],
                "errors": [],
            })

        # team_ratings 模板
        tmpl = generate_csv_template("team_ratings")
        csv_manifest.append({
            "file": tmpl.get("path", ""),
            "rows": tmpl.get("rows", 0),
            "source": "llm_generated_template",
            "needs_manual_review": True,
            "warnings": ["初始模板，需补充真实数据"],
            "errors": [],
        })

        # competition_weights
        cw = generate_competition_weights()
        csv_manifest.append({
            "file": cw.get("path", ""),
            "rows": cw.get("rows", 0),
            "source": "llm_generated_template",
            "needs_manual_review": True,
            "warnings": [],
            "errors": [],
        })
    elif use_llm and not zhipu_key_detected:
        warnings.append("ZHIPU_API_KEY 未配置，跳过 LLM 辅助")
        # 仍然生成模板
        for csv_type in ["team_aliases", "team_ratings", "competition_weights"]:
            tmpl = generate_csv_template(csv_type)
            csv_manifest.append({
                "file": tmpl.get("path", ""),
                "rows": tmpl.get("rows", 0),
                "source": "llm_generated_template",
                "needs_manual_review": True,
                "warnings": ["无 LLM，仅生成模板"],
                "errors": [],
            })
    else:
        # no LLM
        for csv_type in ["team_aliases", "team_ratings", "competition_weights"]:
            tmpl = generate_csv_template(csv_type)
            csv_manifest.append({
                "file": tmpl.get("path", ""),
                "rows": tmpl.get("rows", 0),
                "source": "llm_generated_template",
                "needs_manual_review": True,
                "warnings": ["模板文件"],
                "errors": [],
            })

    # ── 4. 确保 historical CSV 存在 ──
    hist_path = DATA_DIR / "historical_international_matches.csv"
    if not hist_path.exists():
        # 生成空模板
        with open(hist_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "home_team", "away_team", "home_score", "away_score",
                             "tournament", "source", "needs_review"])
            writer.writerow(["2024-01-01", "TeamA", "TeamB", "0", "0",
                             "Friendly", "llm_generated_template", "true"])
        csv_manifest.append({
            "file": str(hist_path),
            "rows": 0,
            "source": "llm_generated_template",
            "needs_manual_review": True,
            "warnings": ["空模板，需补充真实历史数据"],
            "errors": [],
        })

    # ── 5. 确保 fallback groups CSV 存在 ──
    fallback_path = DATA_DIR / "worldcup_2026_groups_fallback.csv"
    if not fallback_path.exists():
        with open(fallback_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["group", "team_name", "source", "needs_review"])
            writer.writerow(["A", "DefaultTeam", "fallback_csv", "true"])
        csv_manifest.append({
            "file": str(fallback_path),
            "rows": 0,
            "source": "fallback_csv",
            "needs_manual_review": True,
            "warnings": ["fallback 模板"],
            "errors": [],
        })

    # ── 6. 生成 data_manifest.json ──
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_key_detected": api_key_detected,
        "zhipu_key_detected": zhipu_key_detected,
        "llm_assisted": llm_assisted,
        "season": season,
        "csv_files": csv_manifest,
        "warnings": warnings,
        "errors": errors,
    }

    try:
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        logger.info(f"[Bootstrap] manifest 写入 {MANIFEST_PATH}")
    except Exception as e:
        logger.error(f"[Bootstrap] manifest 写入失败: {e}")
        errors.append(f"manifest 写入失败: {e}")

    return {
        "success": len(errors) == 0,
        "season": season,
        "llm_assisted": llm_assisted,
        "api_key_detected": api_key_detected,
        "zhipu_key_detected": zhipu_key_detected,
        "manifest_path": str(MANIFEST_PATH),
        "warnings": warnings,
        "errors": errors,
    }
