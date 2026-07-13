"""
足球静态数据爬虫 - TeamDataScraper (Playwright 版本)

抓取球队身价、平均年龄、世界杯历史战绩等公开静态数据。
使用 Playwright 无头浏览器绕过 Cloudflare 反爬保护。
零成本防封锁策略：
- 真实 Chromium 浏览器渲染（绕过 JS 检测）
- 随机 User-Agent 伪装
- 强制随机延迟 (3~7秒)
- 失败时返回默认预估值，绝不崩溃
"""

import re
import time
import random
import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from playwright.async_api import async_playwright, Page, BrowserContext

logger = logging.getLogger(__name__)

# ==================== 配置 ====================

# 页面加载超时（毫秒）
PAGE_TIMEOUT = 30000

# 请求间隔范围（秒）- "礼貌"爬取
MIN_DELAY = 3.0
MAX_DELAY = 7.0

# 默认预估值（抓取失败时使用）
DEFAULT_TEAM_VALUE = 500_000_000  # 5亿欧元
DEFAULT_AVG_AGE = 27.0
DEFAULT_WORLD_CUP_TITLES = 0

# 真实浏览器 User-Agent 池（最新浏览器版本）
USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    # Firefox on Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0",
    # Safari on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
]

# 常用球队名到 Transfermarkt URL slug 的映射
TEAM_SLUGS = {
    "France": "frankreich",
    "Brazil": "brasilien",
    "Argentina": "argentinien",
    "Germany": "deutschland",
    "Spain": "spanien",
    "England": "england",
    "Portugal": "portugal",
    "Netherlands": "niederlande",
    "Belgium": "belgien",
    "Italy": "italien",
    "Croatia": "kroatien",
    "Uruguay": "uruguay",
    "Colombia": "kolumbien",
    "Mexico": "mexiko",
    "USA": "usa",
    "Japan": "japan",
    "South Korea": "sudkorea",
    "Australia": "australien",
    "Morocco": "marokko",
    "Senegal": "senegal",
    "Poland": "polen",
    "Switzerland": "schweiz",
    "Denmark": "danemark",
    "Serbia": "serbien",
    "Canada": "kanada",
    "Ecuador": "ecuador",
    "Wales": "wales",
    "Ghana": "ghana",
    "Cameroon": "kamerun",
    "Tunisia": "tunesien",
    "Saudi Arabia": "saudi-arabien",
    "Iran": "iran",
    "Qatar": "katar",
    "Costa Rica": "costa-rica",
    "Nigeria": "nigeria",
}


# ==================== 工具函数 ====================

def parse_money_string(money_str: str) -> float:
    """
    将非结构化金额文本转换为浮点数（欧元）。

    示例:
        '€1.05bn'   -> 1050000000.0
        '€850m'     -> 850000000.0
        '€50.5m'    -> 50500000.0
        '€1.2bn'    -> 1200000000.0
        '€500m'     -> 500000000.0
        '1,050,000' -> 1050000.0

    Args:
        money_str: 包含金额的字符串

    Returns:
        转换后的浮点数，解析失败返回 0.0
    """
    if not money_str:
        return 0.0

    # 清理字符串
    cleaned = money_str.strip()
    cleaned = cleaned.replace("€", "").replace("£", "").replace("$", "")
    cleaned = cleaned.strip()

    # 匹配数字部分（支持逗号分隔）
    num_match = re.search(r'[\d,]+(?:\.\d+)?', cleaned)
    if not num_match:
        return 0.0

    num_str = num_match.group().replace(",", "")
    try:
        num = float(num_str)
    except ValueError:
        return 0.0

    # 检测单位后缀
    lower = cleaned.lower()
    if "bn" in lower or "billion" in lower:
        num *= 1_000_000_000
    elif "m" in lower or "million" in lower:
        num *= 1_000_000
    elif "k" in lower or "thousand" in lower:
        num *= 1_000

    return num


# ==================== 爬虫类 ====================

class TeamDataScraper:
    """
    足球静态数据爬虫 (Playwright 版本)

    使用无头 Chromium 浏览器抓取 Transfermarkt / Wikipedia 等公开网站的球队数据。
    内置防封锁机制：真实浏览器渲染 + 随机 UA + 强制延迟。
    """

    def __init__(self, enable_delay: bool = True):
        """
        初始化爬虫

        Args:
            enable_delay: 是否启用请求间延迟（测试时可关闭）
        """
        self.enable_delay = enable_delay
        self._last_request_time = 0.0
        self._request_count = 0
        self._browser = None
        self._playwright = None

    async def _ensure_browser(self):
        """确保浏览器已启动"""
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ]
            )
            logger.info("[爬虫] Chromium 浏览器已启动")

    async def _create_context(self) -> BrowserContext:
        """创建带随机 UA 的浏览器上下文"""
        await self._ensure_browser()
        ua = random.choice(USER_AGENTS)
        context = await self._browser.new_context(
            user_agent=ua,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
        )
        return context

    async def _polite_delay(self):
        """礼貌延迟：在请求之间等待 3~7 秒（异步版本）"""
        if not self.enable_delay:
            return

        elapsed = time.time() - self._last_request_time
        if elapsed < MIN_DELAY:
            wait_time = random.uniform(MIN_DELAY, MAX_DELAY)
            logger.debug(f"[爬虫] 等待 {wait_time:.1f} 秒...")
            await asyncio.sleep(wait_time)

    async def _safe_goto(self, page: Page, url: str) -> bool:
        """
        安全的页面导航，带完整的错误处理

        Returns:
            是否成功加载页面
        """
        await self._polite_delay()

        try:
            logger.info(f"[爬虫] 请求: {url}")
            response = await page.goto(url, timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")

            self._last_request_time = time.time()
            self._request_count += 1

            # 检查响应状态
            if response is None:
                logger.warning(f"[爬虫] 无响应: {url}")
                return False

            if response.status == 403:
                logger.warning(f"[爬虫] 403 Forbidden: {url}")
                return False
            if response.status == 429:
                logger.warning(f"[爬虫] 429 Too Many Requests: {url}")
                return False
            if response.status >= 400:
                logger.warning(f"[爬虫] HTTP {response.status}: {url}")
                return False

            # 等待页面完全加载（包括 JS 渲染）
            await page.wait_for_load_state("networkidle", timeout=10000)

            logger.info(f"[爬虫] 成功加载页面")
            return True

        except Exception as e:
            logger.error(f"[爬虫] 页面加载失败: {e}")
            return False

    async def _safe_fetch(self, url: str) -> Optional[Page]:
        """
        安全的页面抓取，返回 Page 对象

        Returns:
            Page 对象，或 None（失败时）
        """
        context = await self._create_context()
        page = await context.new_page()

        try:
            success = await self._safe_goto(page, url)
            if success:
                return page
            else:
                await page.close()
                await context.close()
                return None
        except Exception as e:
            logger.error(f"[爬虫] 抓取失败: {e}")
            await page.close()
            await context.close()
            return None

    async def _close_page(self, page: Page):
        """安全关闭页面和上下文"""
        try:
            context = page.context
            await page.close()
            await context.close()
        except Exception:
            pass

    async def close(self):
        """关闭浏览器"""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("[爬虫] 浏览器已关闭")

    # ==================== 核心方法 ====================

    async def scrape_team_value(self, team_name: str) -> Dict[str, Any]:
        """
        抓取球队总身价（异步版本，使用 Playwright）

        数据源: Transfermarkt

        Args:
            team_name: 球队英文名（如 "France", "Brazil"）

        Returns:
            {
                "team_name": str,
                "total_value": float,        # 总身价（欧元）
                "total_value_str": str,      # 原始文本
                "avg_age": float,            # 平均年龄
                "num_players": int,          # 球员数量
                "source": str,               # "transfermarkt" | "default"
                "scraped_at": str | None
            }
        """
        # 获取球队 URL slug
        slug = TEAM_SLUGS.get(team_name, team_name.lower().replace(" ", "-"))
        url = f"https://www.transfermarkt.com/{slug}/startseite/verein/0"

        page = await self._safe_fetch(url)

        if page is not None:
            try:
                result = await self._parse_team_value_playwright(page, team_name)
                if result and result["total_value"] > 0:
                    result["source"] = "transfermarkt"
                    result["scraped_at"] = datetime.now().isoformat()
                    await self._close_page(page)
                    return result
            except Exception as e:
                logger.error(f"[爬虫] 解析球队身价失败: {e}")
            finally:
                await self._close_page(page)

        # 降级：返回默认预估值
        logger.warning(f"[爬虫] 使用默认预估值: {team_name}")
        return {
            "team_name": team_name,
            "total_value": DEFAULT_TEAM_VALUE,
            "total_value_str": "€500m (预估)",
            "avg_age": DEFAULT_AVG_AGE,
            "num_players": 26,
            "source": "default",
            "scraped_at": None
        }

    async def scrape_world_cup_history(self, team_name: str) -> Dict[str, Any]:
        """
        抓取球队世界杯历史战绩（异步版本，使用 Playwright）

        数据源: Wikipedia

        Args:
            team_name: 球队英文名

        Returns:
            {
                "team_name": str,
                "titles": int,               # 夺冠次数
                "appearances": int,          # 参赛次数
                "best_result": str,          # 最佳成绩
                "historical_matches": List,  # 历史交锋记录
                "source": str,               # "wikipedia" | "default"
                "scraped_at": str | None
            }
        """
        # Wikipedia 搜索
        search_url = f"https://en.wikipedia.org/wiki/{team_name}_national_football_team"

        page = await self._safe_fetch(search_url)

        if page is not None:
            try:
                result = await self._parse_world_cup_history_playwright(page, team_name)
                if result:
                    result["source"] = "wikipedia"
                    result["scraped_at"] = datetime.now().isoformat()
                    await self._close_page(page)
                    return result
            except Exception as e:
                logger.error(f"[爬虫] 解析世界杯历史失败: {e}")
            finally:
                await self._close_page(page)

        # 降级
        logger.warning(f"[爬虫] 使用默认历史数据: {team_name}")
        return {
            "team_name": team_name,
            "titles": DEFAULT_WORLD_CUP_TITLES,
            "appearances": 0,
            "best_result": "Unknown",
            "historical_matches": [],
            "source": "default",
            "scraped_at": None
        }

    async def scrape_team_squad(self, team_name: str) -> Dict[str, Any]:
        """
        抓取球队阵容详情（球员名单 + 个人身价）（异步版本，使用 Playwright）

        数据源: Transfermarkt

        Args:
            team_name: 球队英文名

        Returns:
            {
                "team_name": str,
                "players": [
                    {
                        "name": str,
                        "position": str,
                        "age": int,
                        "market_value": float,
                        "market_value_str": str
                    }, ...
                ],
                "source": str,
                "scraped_at": str | None
            }
        """
        slug = TEAM_SLUGS.get(team_name, team_name.lower().replace(" ", "-"))
        url = f"https://www.transfermarkt.com/{slug}/kader/verein/0"

        page = await self._safe_fetch(url)

        if page is not None:
            try:
                result = await self._parse_squad_playwright(page, team_name)
                if result:
                    result["source"] = "transfermarkt"
                    result["scraped_at"] = datetime.now().isoformat()
                    await self._close_page(page)
                    return result
            except Exception as e:
                logger.error(f"[爬虫] 解析阵容失败: {e}")
            finally:
                await self._close_page(page)

        # 降级
        return {
            "team_name": team_name,
            "players": [],
            "source": "default",
            "scraped_at": None
        }

    # ==================== Playwright 页面解析 ====================

    async def _parse_team_value_playwright(self, page: Page, team_name: str) -> Optional[Dict]:
        """使用 Playwright 选择器从 Transfermarkt 页面解析球队身价"""
        try:
            total_value = 0.0
            total_value_str = ""

            # 方法1: 查找 market value 相关元素
            value_elements = await page.query_selector_all('[class*="market-value"], [class*="marktwert"]')
            for elem in value_elements:
                text = await elem.inner_text()
                parsed = parse_money_string(text)
                if parsed > total_value:
                    total_value = parsed
                    total_value_str = text

            # 方法2: 查找所有包含 € 的文本
            if total_value == 0:
                all_text = await page.inner_text("body")
                money_patterns = re.findall(r'€[\d,.]+[mbkMBK]?(?:illion)?', all_text)
                for pattern in money_patterns:
                    parsed = parse_money_string(pattern)
                    if parsed > total_value:
                        total_value = parsed
                        total_value_str = pattern

            # 查找平均年龄
            avg_age = DEFAULT_AVG_AGE
            age_elements = await page.query_selector_all('text=/Ø age|average age|Durchschnittsalter/i')
            for elem in age_elements:
                parent = await elem.evaluate("el => el.parentElement?.textContent || ''")
                age_match = re.search(r'(\d{1,2}\.\d)', parent)
                if age_match:
                    avg_age = float(age_match.group(1))
                    break

            # 查找球员数量
            num_players = 0
            player_rows = await page.query_selector_all('[class*="player"], [class*="spieler"]')
            if player_rows:
                num_players = len(player_rows)

            return {
                "team_name": team_name,
                "total_value": total_value if total_value > 0 else DEFAULT_TEAM_VALUE,
                "total_value_str": total_value_str or f"€{DEFAULT_TEAM_VALUE/1e6:.0f}m (预估)",
                "avg_age": avg_age,
                "num_players": num_players if num_players > 0 else 26
            }

        except Exception as e:
            logger.error(f"[解析] 球队身价解析异常: {e}")
            return None

    async def _parse_world_cup_history_playwright(self, page: Page, team_name: str) -> Optional[Dict]:
        """使用 Playwright 选择器从 Wikipedia 页面解析世界杯历史"""
        try:
            titles = 0
            appearances = 0
            best_result = "Unknown"

            # 查找 infobox
            infobox = await page.query_selector('.infobox, .vcard')
            if infobox:
                infobox_text = await infobox.inner_text()

                # 查找 FIFA World Cup 冠军次数
                title_patterns = [
                    r'FIFA World Cup.*?(\d+)\s*(?:title|champion|winner)',
                    r'World Cup.*?(\d+)\s*(?:title|champion|winner)',
                    r'(\d+)\s*(?:FIFA )?World Cup',
                ]
                for pattern in title_patterns:
                    match = re.search(pattern, infobox_text, re.I)
                    if match:
                        titles = int(match.group(1))
                        break

            # 查找参赛次数
            content = await page.inner_text("body")
            appearance_patterns = [
                r'Appearances.*?(\d+)',
                r'(\d+)\s*(?:FIFA )?World Cup.*?(?:appearance|tournament)',
            ]
            for pattern in appearance_patterns:
                match = re.search(pattern, content, re.I)
                if match:
                    appearances = int(match.group(1))
                    break

            # 最佳成绩
            if titles > 0:
                best_result = f"Champion ({titles}x)"
            else:
                if re.search(r'runner.?up|finalist', content, re.I):
                    best_result = "Runner-up"
                elif re.search(r'third.?place|semi.?final', content, re.I):
                    best_result = "Third place / Semi-final"

            return {
                "team_name": team_name,
                "titles": titles,
                "appearances": appearances,
                "best_result": best_result,
                "historical_matches": []
            }

        except Exception as e:
            logger.error(f"[解析] 世界杯历史解析异常: {e}")
            return None

    async def _parse_squad_playwright(self, page: Page, team_name: str) -> Optional[Dict]:
        """使用 Playwright 选择器从 Transfermarkt 页面解析阵容"""
        try:
            players = []

            # 查找球员表格行
            rows = await page.query_selector_all('tr.odd, tr.even')

            for row in rows[:30]:  # 最多取 30 名球员
                try:
                    cells = await row.query_selector_all('td')
                    if len(cells) < 4:
                        continue

                    # 球员姓名
                    name_cell = await row.query_selector('[class*="player"], [class*="hauptlink"]')
                    name = await name_cell.inner_text() if name_cell else ""

                    # 位置
                    pos_cell = await row.query_selector('[class*="pos"], [class*="position"]')
                    position = await pos_cell.inner_text() if pos_cell else ""

                    # 年龄
                    age_cell = await row.query_selector('[class*="age"], [class*="zentriert"]')
                    age = 0
                    if age_cell:
                        age_text = await age_cell.inner_text()
                        age_match = re.search(r'(\d{2})', age_text)
                        if age_match:
                            age = int(age_match.group(1))

                    # 身价
                    value_cell = await row.query_selector('[class*="market"], [class*="marktwert"]')
                    market_value = 0.0
                    market_value_str = ""
                    if value_cell:
                        market_value_str = await value_cell.inner_text()
                        market_value = parse_money_string(market_value_str)

                    if name:
                        players.append({
                            "name": name.strip(),
                            "position": position.strip(),
                            "age": age,
                            "market_value": market_value,
                            "market_value_str": market_value_str.strip()
                        })

                except Exception as e:
                    logger.debug(f"[解析] 跳过球员行: {e}")
                    continue

            return {
                "team_name": team_name,
                "players": players
            }

        except Exception as e:
            logger.error(f"[解析] 阵容解析异常: {e}")
            return None

    # ==================== 辅助方法 ====================

    def get_stats(self) -> Dict[str, Any]:
        """获取爬虫运行统计"""
        return {
            "total_requests": self._request_count,
            "last_request_at": datetime.fromtimestamp(self._last_request_time).isoformat() if self._last_request_time else None,
            "delay_enabled": self.enable_delay,
            "delay_range": f"{MIN_DELAY}-{MAX_DELAY}s",
            "browser_active": self._browser is not None
        }


# ==================== 便捷单例 ====================

_scraper_instance: Optional[TeamDataScraper] = None


def get_scraper(enable_delay: bool = True) -> TeamDataScraper:
    """获取全局爬虫单例"""
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = TeamDataScraper(enable_delay=enable_delay)
    return _scraper_instance


# ==================== 测试入口 ====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("TeamDataScraper (Playwright) 测试")
    print("=" * 60)

    # 测试金额解析
    print("\n[1] 金额解析测试:")
    test_cases = [
        ("€1.05bn", 1050000000.0),
        ("€850m", 850000000.0),
        ("€50.5m", 50500000.0),
        ("€1.2bn", 1200000000.0),
        ("€500m", 500000000.0),
        ("1,050,000", 1050000.0),
    ]
    for text, expected in test_cases:
        result = parse_money_string(text)
        status = "✓" if abs(result - expected) < 1 else "✗"
        print(f"  {status} '{text}' -> {result:,.0f} (期望: {expected:,.0f})")

    # 测试爬虫（异步版本）
    print("\n[2] 爬虫测试（关闭延迟）:")

    async def run_test():
        scraper = TeamDataScraper(enable_delay=False)
        print(f"\n  爬虫统计: {scraper.get_stats()}")

        # 尝试抓取（可能因网络/反爬而失败，会降级到默认值）
        print("\n  抓取 France 球队身价...")
        result = await scraper.scrape_team_value("France")
        print(f"  结果: {result['team_name']}")
        print(f"  身价: {result['total_value']:,.0f} EUR")
        print(f"  来源: {result['source']}")

        # 关闭浏览器
        await scraper.close()

    asyncio.run(run_test())

    print("\n测试完成！")
