"""
football-data.org API 工具

接口文档：https://www.football-data.org/documentation/api
免费套餐：10 次/分钟

请求头：X-Auth-Token: FOOTBALL_DATA_API
"""

import json
import logging
import requests
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# football-data.org API 基础 URL
FOOTBALL_DATA_BASE_URL = "https://api.football-data.org/v4"

# 请求超时（秒）
REQUEST_TIMEOUT = 15


class FootballDataTool:
    """football-data.org API 工具"""

    def __init__(self):
        self.settings = get_settings()
        self._api_key = self.settings.football_data_api_key
        self.session = requests.Session()
        if self._api_key:
            self.session.headers.update({"X-Auth-Token": self._api_key})

    @property
    def api_key_detected(self) -> bool:
        return bool(self._api_key)

    def _ok(self, endpoint: str, data: Any, message: str = "") -> Dict[str, Any]:
        return {
            "success": True,
            "data": data,
            "source": "football_data",
            "source_level": "external_real",
            "error_type": None,
            "message": message or f"football-data.org {endpoint} 成功",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    def _fail(self, endpoint: str, error_type: str, message: str) -> Dict[str, Any]:
        return {
            "success": False,
            "data": [],
            "source": "football_data",
            "source_level": "",
            "error_type": error_type,
            "message": message,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """发起 HTTP 请求"""
        if not self._api_key:
            logger.warning("[football-data.org] API Key 未配置")
            return None

        url = f"{FOOTBALL_DATA_BASE_URL}/{endpoint}"
        try:
            logger.info(f"[football-data.org] 请求: {endpoint}")
            response = self.session.get(url, params=params or {}, timeout=REQUEST_TIMEOUT)

            if response.status_code == 401:
                logger.error("[football-data.org] 401 Unauthorized - API Key 无效")
                return None
            if response.status_code == 403:
                logger.error("[football-data.org] 403 Forbidden - 无权限访问")
                return None
            if response.status_code == 429:
                logger.warning("[football-data.org] 429 Too Many Requests - 限流")
                return None

            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            logger.error(f"[football-data.org] 请求超时: {endpoint}")
            return None
        except requests.exceptions.ConnectionError:
            logger.error(f"[football-data.org] 连接失败: {endpoint}")
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"[football-data.org] HTTP 错误: {e}")
            return None
        except Exception as e:
            logger.error(f"[football-data.org] 未知错误: {e}")
            return None

    def get_worldcup_teams(self) -> Dict[str, Any]:
        """获取世界杯参赛球队"""
        if not self._api_key:
            return self._fail("competitions/WC/teams", "missing_api_key", "FOOTBALL_DATA_API 未配置")

        resp = self._make_request("competitions/WC/teams")
        if resp is None:
            return self._fail("competitions/WC/teams", "request_failed", "football-data.org 请求失败")

        teams = resp.get("teams", [])
        if not teams:
            return self._fail("competitions/WC/teams", "empty_data", "football-data.org 返回 0 支球队")

        # 转换为统一格式
        parsed_teams = []
        for t in teams:
            parsed_teams.append({
                "team": {
                    "id": t.get("id"),
                    "name": t.get("name", t.get("shortName", "Unknown")),
                    "tla": t.get("tla", ""),
                },
                "raw": t,
            })

        return self._ok("competitions/WC/teams", parsed_teams, f"获取 {len(parsed_teams)} 支球队")

    def get_worldcup_matches(self) -> Dict[str, Any]:
        """获取世界杯比赛赛程"""
        if not self._api_key:
            return self._fail("competitions/WC/matches", "missing_api_key", "FOOTBALL_DATA_API 未配置")

        resp = self._make_request("competitions/WC/matches")
        if resp is None:
            return self._fail("competitions/WC/matches", "request_failed", "football-data.org 请求失败")

        matches = resp.get("matches", [])
        if not matches:
            return self._fail("competitions/WC/matches", "empty_data", "football-data.org 返回 0 场比赛")

        # 转换为统一格式
        parsed_matches = []
        for m in matches:
            home_team = m.get("homeTeam", {})
            away_team = m.get("awayTeam", {})
            
            # 跳过未确定球队的比赛（如半决赛/决赛的 TBD）
            if not home_team or not away_team:
                continue
            home_name = home_team.get("name")
            away_name = away_team.get("name")
            if not home_name or not away_name:
                continue

            # 判断比赛阶段
            stage = m.get("stage", "GROUP_STAGE")
            stage_map = {
                "GROUP_STAGE": "group_stage",
                "LAST_32": "round_of_32",
                "ROUND_OF_32": "round_of_32",
                "LAST_16": "round_of_16",
                "ROUND_OF_16": "round_of_16",
                "QUARTER_FINALS": "quarter_finals",
                "SEMI_FINALS": "semi_finals",
                "FINAL": "final",
            }

            # 判断状态
            status = m.get("status", "SCHEDULED")
            status_map = {
                "SCHEDULED": "NS",
                "TIMED": "NS",
                "IN_PLAY": "LIVE",
                "PAUSED": "LIVE",
                "FINISHED": "FT",
                "AFTER_EXTRA_TIME": "AET",
                "AFTER_PENALTY": "PEN",
                "CANCELLED": "CANC",
                "POSTPONED": "POST",
            }

            # 获取比分
            score = m.get("score", {})
            full_time = score.get("fullTime", {})

            # 判断胜者
            winner = score.get("winner", "")
            winner_team = None
            if winner == "HOME_TEAM":
                winner_team = home_name
            elif winner == "AWAY_TEAM":
                winner_team = away_name

            parsed_matches.append({
                "fixture_id": f"fd_{m.get('id', '')}",
                "api_fixture_id": str(m.get("id", "")),
                "home_team": home_name,
                "away_team": away_name,
                "home_team_id": str(home_team.get("id", "")),
                "away_team_id": str(away_team.get("id", "")),
                "match_date": m.get("utcDate"),
                "stage": stage_map.get(stage, stage.lower()),
                "status": status_map.get(status, status),
                "home_score": full_time.get("home"),
                "away_score": full_time.get("away"),
                "winner": winner_team,
                "source": "football_data",
                "source_level": "external_real",
                "is_verified": True,
                "needs_review": False,
                "raw": m,
            })

        return self._ok("competitions/WC/matches", parsed_matches, f"获取 {len(parsed_matches)} 场比赛")

    def get_cache_status(self) -> Dict[str, Any]:
        """获取 API 状态"""
        return {
            "api": "football-data.org",
            "api_key_configured": bool(self._api_key),
            "base_url": FOOTBALL_DATA_BASE_URL,
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tool = FootballDataTool()
    print(f"API Key 已配置: {tool.api_key_detected}")
    print(f"状态: {tool.get_cache_status()}")
    
    teams = tool.get_worldcup_teams()
    print(f"球队: success={teams['success']}, count={len(teams.get('data', []))}")
    
    matches = tool.get_worldcup_matches()
    print(f"比赛: success={matches['success']}, count={len(matches.get('data', []))}")
