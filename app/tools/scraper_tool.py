"""
爬虫工具

封装 app/data/web_scraper.py 的 TeamDataScraper，
爬虫失败不阻塞 Agent，只作为 warning。
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ScraperTool:
    """封装 Playwright 爬虫为标准 Agent 工具"""

    def __init__(self):
        self._scraper = None

    def _get_scraper(self):
        """懒加载爬虫"""
        if self._scraper is None:
            try:
                from app.data.web_scraper import TeamDataScraper
                self._scraper = TeamDataScraper()
            except Exception as e:
                logger.warning(f"[ScraperTool] 爬虫初始化失败: {e}")
                self._scraper = None
        return self._scraper

    def _ok(self, data: Any) -> Dict[str, Any]:
        return {"success": True, "source": "scraper", "data": data, "error": None}

    def _fail(self, error: str) -> Dict[str, Any]:
        return {"success": False, "source": "scraper", "data": None, "error": error}

    def get_team_market_value(self, team_name: str) -> Dict[str, Any]:
        """获取球队身价"""
        try:
            scraper = self._get_scraper()
            if scraper is None:
                return self._fail("爬虫不可用")
            result = scraper.get_team_market_value(team_name)
            if result:
                return self._ok({"team": team_name, "market_value": result})
            return self._fail(f"未获取到 {team_name} 身价")
        except Exception as e:
            logger.warning(f"[ScraperTool] get_team_market_value 失败: {e}")
            return self._fail(str(e))

    def get_team_news(self, team_name: str) -> Dict[str, Any]:
        """获取球队新闻（预留接口）"""
        return self._fail("暂不支持")

    def get_injury_summary(self, team_name: str) -> Dict[str, Any]:
        """获取伤病摘要（预留接口）"""
        return self._fail("暂不支持")
