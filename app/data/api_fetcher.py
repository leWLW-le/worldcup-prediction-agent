"""
Football API 客户端 - 带本地 SQLite 缓存

使用 API-Sports 官方接口（https://v3.football.api-sports.io/）。
认证方式：x-apisports-key Header。
核心策略：本地 SQLite 缓存，12 小时内不重复请求外网。
网络异常或 429/499 时自动降级使用本地历史数据。
"""

import sqlite3
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import requests

logger = logging.getLogger(__name__)

# ==================== 配置常量 ====================

# API-Sports 官方接口
API_SPORTS_BASE_URL = "https://v3.football.api-sports.io"

# 缓存过期时间（小时）
CACHE_TTL_HOURS = 12

# 缓存数据库路径
CACHE_DB_PATH = Path(__file__).parent / "football_cache.db"

# 网络请求超时（秒）
REQUEST_TIMEOUT = 15


# ==================== 缓存数据库管理 ====================

class CacheDB:
    """SQLite 缓存数据库管理器"""

    def __init__(self, db_path: Path = CACHE_DB_PATH):
        self.db_path = db_path
        self._init_tables()

    def _init_tables(self):
        """自动创建缓存表"""
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS team_recent_form (
                    cache_key   TEXT PRIMARY KEY,
                    data_json   TEXT    NOT NULL,
                    updated_at  REAL    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS live_scores (
                    id          INTEGER PRIMARY KEY CHECK (id = 1),
                    data_json   TEXT    NOT NULL,
                    updated_at  REAL    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS api_call_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    endpoint    TEXT    NOT NULL,
                    called_at   REAL    NOT NULL,
                    status_code INTEGER,
                    success     INTEGER DEFAULT 1
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def get(self, table: str, key_col: str, key_val: Any) -> Optional[Dict]:
        """
        从缓存读取数据。
        如果数据未过期（updated_at 距今不到 CACHE_TTL_HOURS），返回缓存数据；
        否则返回 None 表示需要刷新。
        """
        cutoff = time.time() - CACHE_TTL_HOURS * 3600
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT data_json, updated_at FROM {table} WHERE {key_col} = ?",
                (key_val,)
            ).fetchone()

            if row is None:
                return None

            data_json, updated_at = row
            if updated_at < cutoff:
                logger.info(f"[缓存] {table}[{key_val}] 已过期 (更新于 {datetime.fromtimestamp(updated_at)})")
                return None

            logger.info(f"[缓存] {table}[{key_val}] 命中 (更新于 {datetime.fromtimestamp(updated_at)})")
            return json.loads(data_json)

    def put(self, table: str, key_col: str, key_val: Any, data: Any):
        """写入/更新缓存"""
        now = time.time()
        data_json = json.dumps(data, ensure_ascii=False)
        with self._connect() as conn:
            if table == "live_scores":
                conn.execute(
                    "INSERT OR REPLACE INTO live_scores (id, data_json, updated_at) VALUES (1, ?, ?)",
                    (data_json, now)
                )
            else:
                conn.execute(
                    f"INSERT OR REPLACE INTO {table} ({key_col}, data_json, updated_at) VALUES (?, ?, ?)",
                    (key_val, data_json, now)
                )

    def log_api_call(self, endpoint: str, status_code: int, success: bool):
        """记录 API 调用日志（用于监控每日额度消耗）"""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO api_call_log (endpoint, called_at, status_code, success) VALUES (?, ?, ?, ?)",
                (endpoint, time.time(), status_code, int(success))
            )

    def get_today_call_count(self) -> int:
        """获取今天的 API 调用次数"""
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM api_call_log WHERE called_at >= ?",
                (today_start,)
            ).fetchone()
            return row[0] if row else 0

    def get_cached_form_fallback(self, team_id: int) -> Optional[Dict]:
        """
        强制返回缓存数据（即使过期），用于网络异常时的降级。
        查找所有以 {team_id}_ 开头的缓存记录。
        """
        with self._connect() as conn:
            # 查找最新的缓存记录（按更新时间降序）
            row = conn.execute(
                "SELECT data_json, updated_at FROM team_recent_form WHERE cache_key LIKE ? ORDER BY updated_at DESC LIMIT 1",
                (f"{team_id}_%",)
            ).fetchone()
            if row:
                logger.warning(f"[降级] 使用 {team_id} 的过期缓存数据")
                return json.loads(row[0])
        return None

    def get_cached_scores_fallback(self) -> Optional[Dict]:
        """强制返回比分缓存（即使过期），用于降级"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data_json, updated_at FROM live_scores WHERE id = 1"
            ).fetchone()
            if row:
                logger.warning("[降级] 使用过期的比分缓存数据")
                return json.loads(row[0])
        return None


# ==================== API 客户端 ====================

class FootballAPIClients:
    """
    带本地缓存的足球 API 客户端（API-Sports 官方接口）

    特性：
    - 12 小时缓存 TTL，避免频繁调用外网
    - 每日调用次数限制（默认 100 次）
    - 网络异常 / 429 / 499 自动降级使用本地数据
    - 认证方式：x-apisports-key Header
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_db_path: Optional[Path] = None,
        cache_ttl_hours: float = CACHE_TTL_HOURS,
        max_daily_calls: int = 100
    ):
        """
        初始化 API 客户端

        Args:
            api_key: API-Sports 密钥（从 .env 的 API_FOOTBALL_KEY 读取）
            cache_db_path: 缓存数据库路径
            cache_ttl_hours: 缓存有效期（小时），默认 12
            max_daily_calls: 每日最大调用次数，默认 100
        """
        self.api_key = api_key or ""
        self.cache = CacheDB(cache_db_path or CACHE_DB_PATH)
        self.cache_ttl_hours = cache_ttl_hours
        self.max_daily_calls = max_daily_calls
        self.session = requests.Session()

        # 设置 API-Sports 官方认证 Header
        self.session.headers.update({
            "x-apisports-key": self.api_key,
        })

    def _check_rate_limit(self) -> bool:
        """检查是否超过每日调用限制"""
        today_calls = self.cache.get_today_call_count()
        if today_calls >= self.max_daily_calls:
            logger.warning(f"[限流] 今日已调用 {today_calls}/{self.max_daily_calls} 次，停止外网请求")
            return False
        return True

    def _make_request(self, endpoint: str, params: Dict) -> Optional[Dict]:
        """
        发起 HTTP 请求，带完整的错误处理

        Returns:
            API 响应 JSON 或 None（失败时）
        """
        if not self.api_key:
            logger.error("[API] 未配置 API_FOOTBALL_KEY，跳过外网请求")
            return None

        if not self._check_rate_limit():
            return None

        url = f"{API_SPORTS_BASE_URL}/{endpoint}"

        try:
            logger.info(f"[API] 请求: {endpoint} 参数: {params}")
            response = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)

            if response.status_code == 429:
                logger.warning("[API] 429 Too Many Requests - 触发限流，降级使用本地数据")
                self.cache.log_api_call(endpoint, 429, False)
                return None

            if response.status_code == 499:
                logger.warning("[API] 499 Client Closed Request - 连接中断，降级使用本地数据")
                self.cache.log_api_call(endpoint, 499, False)
                return None

            if response.status_code == 403:
                logger.warning("[API] 403 Forbidden - 可能是额度用尽或 Key 无效")
                self.cache.log_api_call(endpoint, 403, False)
                return None

            response.raise_for_status()

            data = response.json()
            self.cache.log_api_call(endpoint, response.status_code, True)
            logger.info(f"[API] 成功: {endpoint}")
            return data

        except requests.exceptions.Timeout:
            logger.error(f"[API] 请求超时: {endpoint}")
            self.cache.log_api_call(endpoint, 0, False)
            return None

        except requests.exceptions.ConnectionError:
            logger.error(f"[API] 连接失败: {endpoint}")
            self.cache.log_api_call(endpoint, 0, False)
            return None

        except requests.exceptions.HTTPError as e:
            logger.error(f"[API] HTTP 错误: {e}")
            self.cache.log_api_call(endpoint, getattr(e.response, 'status_code', 0), False)
            return None

        except json.JSONDecodeError:
            logger.error(f"[API] JSON 解析失败: {endpoint}")
            return None

        except Exception as e:
            logger.error(f"[API] 未知错误: {e}")
            return None

    # ==================== 核心方法 ====================

    def fetch_team_recent_form(self, team_id: int, season: int = None) -> Dict[str, Any]:
        """
        获取球队近期战绩（近 5 场）

        策略：
        1. 先查本地缓存（12 小时内有效）
        2. 缓存过期才发起外网请求
        3. 请求失败则降级使用过期缓存

        注意：免费套餐不支持 last 参数，改用 season 参数获取整个赛季数据，
              然后在 Python 内部切片取最近 5 场。

        Args:
            team_id: 球队 ID（API-Football 的球队编号）
            season: 赛季年份，默认当前年份

        Returns:
            {
                "team_id": int,
                "team_name": str,
                "recent_matches": [
                    {
                        "date": str,
                        "opponent": str,
                        "result": "W/D/L",
                        "score": "2-1",
                        "competition": str
                    }, ...
                ],
                "form": "WWDLL",  # 近 5 场战绩简写
                "source": "cache" | "api",
                "cached_at": str | None
            }
        """
        # 默认使用当前年份
        if season is None:
            season = datetime.now().year
        
        # 缓存 key 包含 season，确保不同赛季的数据分开缓存
        cache_key = f"{team_id}_{season}"
        
        # 1. 尝试读取有效缓存
        cached = self.cache.get("team_recent_form", "cache_key", cache_key)
        if cached is not None:
            logger.info(f"[Form] 缓存命中: {cache_key}")
            cached["source"] = "cache"
            return cached

        # 2. 发起外网请求（使用 season 参数，免费套餐支持）
        logger.info(f"[Form] 缓存过期，从 API 拉取球队 {team_id} {season} 赛季战绩")
        api_data = self._make_request("fixtures", {
            "team": team_id,
            "season": season
        })

        if api_data is not None:
            # 检查 API 是否返回错误（如免费套餐限制）
            errors = api_data.get("errors", {})
            if errors:
                logger.warning(f"[Form] API 返回错误: {errors}")
            
            # 解析 API 响应（内部会切片取最近 5 场）
            parsed = self._parse_recent_form(team_id, api_data)
            if parsed:
                # 存入缓存
                self.cache.put("team_recent_form", "cache_key", cache_key, parsed)
                logger.info(f"[Form] 数据已缓存: {cache_key}")
                parsed["source"] = "api"
                return parsed

        # 3. 降级：使用过期缓存
        fallback = self.cache.get_cached_form_fallback(team_id)
        if fallback:
            fallback["source"] = "cache_expired"
            return fallback

        # 4. 完全没有数据
        logger.warning(f"[Form] 球队 {team_id} 无任何历史数据")
        return {
            "team_id": team_id,
            "team_name": "Unknown",
            "recent_matches": [],
            "form": "-----",
            "source": "none",
            "cached_at": None
        }

    def fetch_live_scores(self) -> Dict[str, Any]:
        """
        获取今日实时比分

        策略同上：缓存优先 → 外网拉取 → 降级过期缓存

        Returns:
            {
                "date": str,
                "matches": [
                    {
                        "home_team": str,
                        "away_team": str,
                        "home_score": int | None,
                        "away_score": int | None,
                        "status": str,  # "LIVE" / "FT" / "NS"
                        "minute": int | None,
                        "competition": str
                    }, ...
                ],
                "source": "cache" | "api",
                "cached_at": str | None
            }
        """
        # 1. 尝试读取有效缓存
        cached = self.cache.get("live_scores", "id", 1)
        if cached is not None:
            cached["source"] = "cache"
            return cached

        # 2. 发起外网请求
        today_str = datetime.now().strftime("%Y-%m-%d")
        logger.info(f"[Scores] 缓存过期，从 API 拉取 {today_str} 比分")
        api_data = self._make_request("fixtures", {
            "date": today_str
        })

        if api_data is not None:
            parsed = self._parse_live_scores(api_data)
            if parsed:
                self.cache.put("live_scores", "id", 1, parsed)
                parsed["source"] = "api"
                return parsed

        # 3. 降级：使用过期缓存
        fallback = self.cache.get_cached_scores_fallback()
        if fallback:
            fallback["source"] = "cache_expired"
            return fallback

        # 4. 无数据
        return {
            "date": today_str,
            "matches": [],
            "source": "none",
            "cached_at": None
        }

    # ==================== 数据解析 ====================

    def _parse_recent_form(self, team_id: int, api_data: Dict) -> Optional[Dict]:
        """
        解析 API-Football 的 fixtures 响应为近期战绩格式
        
        注意：免费套餐返回整个赛季的数据，这里按日期排序后切片取最近 5 场
        """
        try:
            fixtures = api_data.get("response", [])
            if not fixtures:
                return None

            # 按日期排序（降序，最新的在前）
            fixtures_sorted = sorted(
                fixtures,
                key=lambda f: f.get("fixture", {}).get("date", ""),
                reverse=True
            )
            
            # 只取最近 5 场
            recent_fixtures = fixtures_sorted[:5]
            
            recent_matches = []
            form_chars = []
            team_name = "Unknown"

            for fixture in recent_fixtures:
                fixture_data = fixture.get("fixture", {})
                teams = fixture.get("teams", {})
                goals = fixture.get("goals", {})
                league = fixture.get("league", {})

                # 判断主客
                home = teams.get("home", {})
                away = teams.get("away", {})
                is_home = (home.get("id") == team_id)

                # 获取球队名称
                if team_name == "Unknown":
                    if is_home:
                        team_name = home.get("name", "Unknown")
                    else:
                        team_name = away.get("name", "Unknown")

                if is_home:
                    opponent = away.get("name", "Unknown")
                    team_goals = goals.get("home")
                    opp_goals = goals.get("away")
                else:
                    opponent = home.get("name", "Unknown")
                    team_goals = goals.get("away")
                    opp_goals = goals.get("home")

                # 判断胜负平
                if team_goals is not None and opp_goals is not None:
                    if team_goals > opp_goals:
                        result = "W"
                    elif team_goals < opp_goals:
                        result = "L"
                    else:
                        result = "D"
                    form_chars.append(result)
                    score = f"{team_goals}-{opp_goals}"
                else:
                    result = "-"
                    score = "-/-"

                recent_matches.append({
                    "date": fixture_data.get("date", "")[:10],
                    "opponent": opponent,
                    "result": result,
                    "score": score,
                    "competition": league.get("name", "Unknown")
                })

            form_str = "".join(form_chars[:5]) if form_chars else "-----"

            return {
                "team_id": team_id,
                "team_name": team_name,
                "recent_matches": recent_matches,
                "form": form_str,
                "cached_at": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"[解析] 近期战绩解析失败: {e}")
            return None

    def _parse_live_scores(self, api_data: Dict) -> Optional[Dict]:
        """解析 API-Football 的 fixtures 响应为实时比分格式"""
        try:
            fixtures = api_data.get("response", [])
            matches = []

            for fixture in fixtures:
                f = fixture.get("fixture", {})
                teams = fixture.get("teams", {})
                goals = fixture.get("goals", {})
                league = fixture.get("league", {})
                status = f.get("status", {})

                home = teams.get("home", {})
                away = teams.get("away", {})

                # 比赛状态映射
                short = status.get("short", "NS")
                if short in ("1H", "2H", "HT", "ET", "P", "BT"):
                    match_status = "LIVE"
                elif short in ("FT", "AET", "PEN"):
                    match_status = "FT"
                else:
                    match_status = "NS"

                matches.append({
                    "home_team": home.get("name", "Unknown"),
                    "away_team": away.get("name", "Unknown"),
                    "home_score": goals.get("home"),
                    "away_score": goals.get("away"),
                    "status": match_status,
                    "minute": status.get("elapsed"),
                    "competition": league.get("name", "Unknown")
                })

            return {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "matches": matches,
                "cached_at": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"[解析] 比分解析失败: {e}")
            return None

    # ==================== 辅助方法 ====================

    def get_cache_status(self) -> Dict[str, Any]:
        """获取缓存状态摘要（用于调试/监控）"""
        today_calls = self.cache.get_today_call_count()
        return {
            "cache_db": str(self.cache.db_path),
            "cache_ttl_hours": self.cache_ttl_hours,
            "today_api_calls": today_calls,
            "max_daily_calls": self.max_daily_calls,
            "remaining_calls": max(0, self.max_daily_calls - today_calls),
            "api_key_configured": bool(self.api_key)
        }

    def clear_cache(self):
        """手动清除所有缓存（慎用）"""
        with self.cache._connect() as conn:
            conn.execute("DELETE FROM team_recent_form")
            conn.execute("DELETE FROM live_scores")
        logger.info("[缓存] 已清除所有缓存数据")


# ==================== 便捷单例 ====================

_client_instance: Optional[FootballAPIClients] = None


def get_api_client(api_key: Optional[str] = None) -> FootballAPIClients:
    """
    获取全局 API 客户端单例

    Args:
        api_key: API-Sports 密钥，首次调用时传入即可

    Returns:
        FootballAPIClients 实例
    """
    global _client_instance
    if _client_instance is None:
        _client_instance = FootballAPIClients(api_key=api_key)
    return _client_instance


# ==================== 测试入口 ====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("FootballAPIClients 测试")
    print("=" * 60)

    # 无 Key 模式测试（纯缓存降级）
    client = FootballAPIClients(api_key="")

    print("\n[1] 缓存状态:")
    print(json.dumps(client.get_cache_status(), indent=2, ensure_ascii=False))

    print("\n[2] 获取球队近期战绩（无 Key，应降级）:")
    form = client.fetch_team_recent_form(85)  # 85 = 法国
    print(json.dumps(form, indent=2, ensure_ascii=False))

    print("\n[3] 获取实时比分（无 Key，应降级）:")
    scores = client.fetch_live_scores()
    print(json.dumps(scores, indent=2, ensure_ascii=False))

    print("\n测试完成！")
