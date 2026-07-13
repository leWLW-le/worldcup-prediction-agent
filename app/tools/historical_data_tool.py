"""
历史数据工具

从本地 CSV 加载过往真实国家队比赛数据。
默认读取 data/historical_international_matches.csv
"""

import csv
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_CSV_PATH = Path("data/historical_international_matches.csv")


class HistoricalDataTool:
    """历史国际比赛数据工具"""

    def __init__(self, csv_path: Optional[Path] = None):
        self.csv_path = csv_path or DEFAULT_CSV_PATH
        self._matches: List[Dict] = []

    def _ok(self, data: Any) -> Dict[str, Any]:
        return {"success": True, "source": "historical_csv", "data": data, "error": None}

    def _fail(self, error: str) -> Dict[str, Any]:
        return {"success": False, "source": "historical_csv", "data": None, "error": error}

    def load_matches(self, start_year: int = 2018) -> Dict[str, Any]:
        """加载 CSV 中的历史比赛"""
        if not self.csv_path.exists():
            return self._fail(f"CSV 文件不存在: {self.csv_path}")

        try:
            matches = []
            with open(self.csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        date_str = row.get("date", "")
                        year = int(date_str[:4]) if date_str else 0
                        if year >= start_year:
                            matches.append({
                                "date": date_str,
                                "home_team": row.get("home_team", ""),
                                "away_team": row.get("away_team", ""),
                                "home_score": int(row.get("home_score", 0)),
                                "away_score": int(row.get("away_score", 0)),
                                "tournament": row.get("tournament", ""),
                                "city": row.get("city", ""),
                                "country": row.get("country", ""),
                                "neutral": row.get("neutral", "FALSE"),
                            })
                    except (ValueError, KeyError):
                        continue

            self._matches = matches
            return self._ok({"total": len(matches), "matches": matches})
        except Exception as e:
            logger.error(f"[HistoricalDataTool] load_matches error: {e}")
            return self._fail(str(e))

    def get_team_matches(self, team_name: str, start_year: int = 2018) -> Dict[str, Any]:
        """获取指定球队的历史比赛"""
        if not self._matches:
            loaded = self.load_matches(start_year)
            if not loaded["success"]:
                return loaded

        team_matches = [
            m for m in self._matches
            if team_name.lower() in (m["home_team"].lower(), m["away_team"].lower())
        ]
        return self._ok({"team": team_name, "count": len(team_matches), "matches": team_matches})

    def get_head_to_head(self, team_a: str, team_b: str) -> Dict[str, Any]:
        """获取两队交锋记录"""
        if not self._matches:
            loaded = self.load_matches()
            if not loaded["success"]:
                return loaded

        h2h = [
            m for m in self._matches
            if (team_a.lower() in (m["home_team"].lower(), m["away_team"].lower()))
            and (team_b.lower() in (m["home_team"].lower(), m["away_team"].lower()))
        ]
        return self._ok({"team_a": team_a, "team_b": team_b, "count": len(h2h), "matches": h2h})
