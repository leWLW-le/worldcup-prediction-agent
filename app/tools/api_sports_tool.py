"""
API-Sports 工具 (API-Football)

封装 app/data/api_fetcher.py 的 FootballAPIClients，
提供统一返回格式：{success, data, source, source_level, error_type, message, fetched_at}

Key 优先级：API_FOOTBALL > API_FOOTBALL_KEY > APISPORTS_KEY
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class APISportsTool:
    """封装 FootballAPIClients 为标准 Agent 工具"""

    def __init__(self):
        self.settings = get_settings()
        self._client = None
        # 优先级：API_FOOTBALL > API_FOOTBALL_KEY > APISPORTS_KEY
        self._api_key = self.settings.api_football_key

    @property
    def api_key_detected(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        """懒加载 API 客户端"""
        if self._client is None:
            from app.data.api_fetcher import FootballAPIClients
            self._client = FootballAPIClients(api_key=self._api_key)
        return self._client

    def _ok(self, endpoint: str, data: Any) -> Dict[str, Any]:
        return {
            "success": True,
            "data": data,
            "source": "api_football",
            "source_level": "external_real",
            "error_type": None,
            "message": f"API-Football {endpoint} 成功",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    def _fail(self, endpoint: str, error: str, error_type: str = "request_failed") -> Dict[str, Any]:
        return {
            "success": False,
            "data": [],
            "source": "api_football",
            "source_level": "",
            "error_type": error_type,
            "message": error,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── 世界杯赛程 ──
    def get_worldcup_fixtures(self, season: int = 2026) -> Dict[str, Any]:
        """获取世界杯赛程 GET /fixtures?league=1&season=2026"""
        if not self._api_key:
            return self._fail("fixtures", "API_FOOTBALL 未配置", "missing_api_key")
        try:
            client = self._get_client()
            resp = client._make_request("fixtures", {"league": 1, "season": season})
            if resp is None:
                return self._fail("fixtures", "API 请求失败或额度用尽")
            fixtures = resp.get("response", [])
            return self._ok("fixtures", fixtures)
        except Exception as e:
            logger.error(f"[APISportsTool] get_worldcup_fixtures error: {e}")
            return self._fail("fixtures", str(e))

    # ── 世界杯球队 ──
    def get_worldcup_teams(self, season: int = 2026) -> Dict[str, Any]:
        """获取世界杯参赛球队 GET /teams?league=1&season=2026"""
        if not self._api_key:
            return self._fail("teams", "API_FOOTBALL 未配置", "missing_api_key")
        try:
            client = self._get_client()
            resp = client._make_request("teams", {"league": 1, "season": season})
            if resp is None:
                return self._fail("teams", "API 请求失败或额度用尽")
            teams = resp.get("response", [])
            return self._ok("teams", teams)
        except Exception as e:
            logger.error(f"[APISportsTool] get_worldcup_teams error: {e}")
            return self._fail("teams", str(e))

    # ── 世界杯积分榜 ──
    def get_worldcup_standings(self, season: int = 2026) -> Dict[str, Any]:
        """获取世界杯积分榜 GET /standings?league=1&season=2026"""
        if not self._api_key:
            return self._fail("standings", "API_FOOTBALL 未配置", "missing_api_key")
        try:
            client = self._get_client()
            resp = client._make_request("standings", {"league": 1, "season": season})
            if resp is None:
                return self._fail("standings", "API 请求失败或额度用尽")
            standings = resp.get("response", [])
            return self._ok("standings", standings)
        except Exception as e:
            logger.error(f"[APISportsTool] get_worldcup_standings error: {e}")
            return self._fail("standings", str(e))

    # ── 实时比赛 ──
    def get_live_fixtures(self) -> Dict[str, Any]:
        """获取实时比分 GET /fixtures?live=all
        无直播时 success=True, data=[]
        """
        if not self._api_key:
            return self._fail("live", "API_FOOTBALL 未配置", "missing_api_key")
        try:
            client = self._get_client()
            resp = client._make_request("fixtures", {"live": "all"})
            if resp is None:
                return self._fail("live", "API 请求失败或额度用尽")
            fixtures = resp.get("response", [])
            # 无直播比赛时 success=True, data=[]
            return self._ok("live", fixtures)
        except Exception as e:
            logger.error(f"[APISportsTool] get_live_fixtures error: {e}")
            return self._fail("live", str(e))

    # ── 近期比赛 ──
    def get_recent_matches(self, team_id: int, season: int = 2024) -> Dict[str, Any]:
        """获取球队近期战绩"""
        if not self._api_key:
            return self._fail(f"fixtures/team/{team_id}", "API_FOOTBALL 未配置", "missing_api_key")
        try:
            client = self._get_client()
            data = client.fetch_team_recent_form(team_id, season=season)
            return self._ok(f"fixtures/team/{team_id}", data)
        except Exception as e:
            logger.error(f"[APISportsTool] get_recent_matches error: {e}")
            return self._fail(f"fixtures/team/{team_id}", str(e))

    # ── 缓存状态 ──
    def get_cache_status(self) -> Dict[str, Any]:
        """获取缓存状态"""
        try:
            client = self._get_client()
            return self._ok("cache_status", client.get_cache_status())
        except Exception as e:
            return self._fail("cache_status", str(e))
