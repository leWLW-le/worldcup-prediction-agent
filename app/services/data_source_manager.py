"""
Data Source Manager - 数据源管理器

负责：
- refresh_fixtures: 从外部 API 刷新比赛数据并写入 fixtures 表
- get_cached_fixtures: 读取缓存的比赛数据
- get_data_status: 获取当前数据状态

支持的 API：
1. football-data.org (优先)
2. API-Football (备选)
"""

import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

# 加载 .env
_project_root = Path(__file__).parent.parent.parent
load_dotenv(_project_root / ".env")

from app.services.fixture_repository import FixtureRepository
from app.models.agent_models import compute_canonical_pair

logger = logging.getLogger(__name__)


class DataSourceManager:
    """数据源管理器"""
    
    def __init__(self):
        self.repo = FixtureRepository()
        self.football_data_key = self._get_api_key("FOOTBALL_DATA_API", "FOOTBALL_DATA_API_KEY")
        self.api_football_key = self._get_api_key("API_FOOTBALL", "API_FOOTBALL_KEY")
    
    def _get_api_key(self, primary: str, fallback: str) -> Optional[str]:
        """获取 API key，优先使用 primary，兼容 fallback"""
        key = os.environ.get(primary)
        if not key:
            key = os.environ.get(fallback)
        return key
    
    def refresh_fixtures(self, season: int = 2026) -> Dict[str, Any]:
        """
        从外部 API 刷新 fixtures 数据
        
        逻辑：
        1. 先调用 football-data.org
        2. 如果成功且 matches > 0，标准化后写入 fixtures 表
        3. 如果失败，再调用 API-Football
        4. 如果 API-Football 成功且 fixtures > 0，标准化后写入 fixtures 表
        5. 如果两个 API 都失败，读取 fixtures 表缓存
        
        Returns:
            {
                "success": bool,
                "source": "football_data" | "api_football" | "db_cache" | "unavailable",
                "source_level": "external_real" | "verified_cache" | "unavailable",
                "message": 用户消息,
                "inserted": 新增数量,
                "updated": 更新数量,
                "skipped": 跳过数量,
                "fixtures_count": fixtures 表总数,
                "last_updated": 最后更新时间,
                "is_external_realtime": 是否外部实时数据,
                "needs_review_count": 需要审核的数量,
                "football_data_status": "success" | "failed" | "not_attempted",
                "api_football_status": "success" | "failed" | "not_attempted"
            }
        """
        result = {
            "success": False,
            "source": None,
            "source_level": None,
            "message": None,
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "fixtures_count": 0,
            "last_updated": None,
            "is_external_realtime": False,
            "needs_review_count": 0,
            "football_data_status": "not_attempted",
            "api_football_status": "not_attempted"
        }
        
        # ── 1. 尝试 football-data.org ──
        if self.football_data_key:
            logger.info("[DataSource] 尝试 football-data.org...")
            fd_result = self._fetch_from_football_data(season)
            
            if fd_result["success"] and fd_result.get("matches_count", 0) > 0:
                logger.info(f"[DataSource] football-data.org 成功: {fd_result['matches_count']} 场比赛")
                
                # 标准化并写入
                upsert_result = self._upsert_football_data_matches(fd_result["matches"])
                
                result.update({
                    "success": True,
                    "source": "football_data",
                    "source_level": "external_real",
                    "message": "比赛数据已更新。",
                    "inserted": upsert_result["inserted"],
                    "updated": upsert_result["updated"],
                    "skipped": upsert_result["skipped"],
                    "is_external_realtime": True,
                    "football_data_status": "success"
                })
                
                # 获取最新状态
                status = self.repo.get_status()
                result["fixtures_count"] = status["fixtures_count"]
                result["last_updated"] = status["last_updated"]
                result["needs_review_count"] = status["needs_review_count"]
                
                return result
            
            else:
                result["football_data_status"] = "failed"
                logger.warning(f"[DataSource] football-data.org 失败: {fd_result.get('error')}")
        
        # ─ 2. 尝试 API-Football ─
        if self.api_football_key:
            logger.info("[DataSource] 尝试 API-Football...")
            af_result = self._fetch_from_api_football(season)
            
            if af_result["success"] and af_result.get("fixtures_count", 0) > 0:
                logger.info(f"[DataSource] API-Football 成功: {af_result['fixtures_count']} 场比赛")
                
                # 标准化并写入
                upsert_result = self._upsert_api_football_fixtures(af_result["fixtures"])
                
                result.update({
                    "success": True,
                    "source": "api_football",
                    "source_level": "external_real",
                    "message": "比赛数据已更新。",
                    "inserted": upsert_result["inserted"],
                    "updated": upsert_result["updated"],
                    "skipped": upsert_result["skipped"],
                    "is_external_realtime": True,
                    "api_football_status": "success"
                })
                
                # 获取最新状态
                status = self.repo.get_status()
                result["fixtures_count"] = status["fixtures_count"]
                result["last_updated"] = status["last_updated"]
                result["needs_review_count"] = status["needs_review_count"]
                
                return result
            
            else:
                result["api_football_status"] = "failed"
                logger.warning(f"[DataSource] API-Football 失败: {af_result.get('error')}")
        
        # ── 3. 两个 API 都失败，读取缓存 ──
        logger.info("[DataSource] 两个 API 都失败，读取 fixtures 表缓存...")
        cached_fixtures = self.repo.get_cached_fixtures(season)
        
        if len(cached_fixtures) > 0:
            logger.info(f"[DataSource] 使用缓存: {len(cached_fixtures)} 场比赛")
            
            status = self.repo.get_status()
            result.update({
                "success": True,
                "source": "db_cache",
                "source_level": "verified_cache",
                "message": "暂时无法刷新，已使用最近一次真实缓存。",
                "fixtures_count": status["fixtures_count"],
                "last_updated": status["last_updated"],
                "needs_review_count": status["needs_review_count"],
                "is_external_realtime": False
            })
            
            return result
        
        # ── 4. fixtures 表也为空 ──
        logger.error("[DataSource] fixtures 表为空，无可用数据")
        result.update({
            "success": False,
            "source": "unavailable",
            "source_level": "unavailable",
            "message": "当前比赛数据不足，请先刷新数据源。",
            "fixtures_count": 0,
            "is_external_realtime": False,
            "needs_review_count": 0
        })
        
        return result
    
    def _fetch_from_football_data(self, season: int) -> Dict[str, Any]:
        """从 football-data.org 获取比赛数据"""
        url = "https://api.football-data.org/v4/competitions/WC/matches"
        headers = {"X-Auth-Token": self.football_data_key}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                matches = data.get("matches", [])
                return {
                    "success": True,
                    "matches": matches,
                    "matches_count": len(matches),
                    "error": None
                }
            else:
                return {
                    "success": False,
                    "matches": [],
                    "matches_count": 0,
                    "error": f"HTTP {response.status_code}: {response.text[:200]}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "matches": [],
                "matches_count": 0,
                "error": str(e)
            }
    
    def _fetch_from_api_football(self, season: int) -> Dict[str, Any]:
        """从 API-Football 获取比赛数据"""
        url = "https://v3.football.api-sports.io/fixtures"
        params = {"league": 1, "season": season}
        headers = {"x-apisports-key": self.api_football_key}
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # 检查 API 是否返回错误信息
                api_errors = data.get("errors", {})
                if api_errors:
                    return {
                        "success": False,
                        "fixtures": [],
                        "fixtures_count": 0,
                        "error": str(api_errors)
                    }
                
                if isinstance(data, dict) and "response" in data:
                    fixtures = data["response"]
                    return {
                        "success": True,
                        "fixtures": fixtures,
                        "fixtures_count": len(fixtures),
                        "error": None
                    }
                else:
                    return {
                        "success": False,
                        "fixtures": [],
                        "fixtures_count": 0,
                        "error": f"Invalid response format: {str(data)[:200]}"
                    }
            else:
                return {
                    "success": False,
                    "fixtures": [],
                    "fixtures_count": 0,
                    "error": f"HTTP {response.status_code}: {response.text[:200]}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "fixtures": [],
                "fixtures_count": 0,
                "error": str(e)
            }
    
    # football-data.org stage → 统一 stage 名
    _STAGE_MAP = {
        "GROUP_STAGE": "group_stage",
        "LAST_32": "round_of_32",
        "ROUND_OF_32": "round_of_32",
        "LAST_16": "round_of_16",
        "ROUND_OF_16": "round_of_16",
        "QUARTER_FINALS": "quarter_finals",
        "SEMI_FINALS": "semi_finals",
        "FINAL": "final",
    }

    def _upsert_football_data_matches(self, matches: List[Dict]) -> Dict[str, int]:
        """将 football-data.org 的 matches 标准化并 upsert"""
        fixtures = []
        
        for match in matches:
            raw_id = match.get("id")
            if not raw_id:
                continue
            # 统一 fixture_id 格式：fd_ 前缀（与 football_data_tool.py 一致）
            fixture_id = f"fd_{raw_id}"
            
            home_team = (match.get("homeTeam") or {}).get("name", "") or "TBD"
            away_team = (match.get("awayTeam") or {}).get("name", "") or "TBD"
            status = match.get("status", "")
            score = match.get("score", {})
            full_time = score.get("fullTime", {})
            home_score = full_time.get("home")
            away_score = full_time.get("away")
            
            # 判断胜者
            winner = None
            if home_score is not None and away_score is not None:
                if home_score > away_score:
                    winner = home_team
                elif away_score > home_score:
                    winner = away_team
                else:
                    winner = "Draw"
            
            # 解析比赛时间
            match_date_str = match.get("utcDate")
            match_date = None
            if match_date_str:
                try:
                    match_date = datetime.fromisoformat(match_date_str.replace('Z', '+00:00'))
                except:
                    pass
            
            # 从 API 读取 stage（不再硬编码 group_stage）
            api_stage = match.get("stage", "GROUP_STAGE")
            stage = self._STAGE_MAP.get(api_stage, "group_stage")
            
            # 构建 fixture
            fixture = {
                "fixture_id": fixture_id,
                "api_fixture_id": fixture_id,
                "home_team": home_team,
                "away_team": away_team,
                "match_date": match_date,
                "stage": stage,
                "status": status,
                "home_score": home_score,
                "away_score": away_score,
                "winner": winner,
                "source": "football_data",
                "source_level": "external_real",
                "is_verified": True,
                "needs_review": False,
                "confidence_level": "medium",
                "evidence_count": 1,
                "evidence_sources": ["football_data"],
                "canonical_pair": compute_canonical_pair(home_team, away_team),
                "raw_payload": json.dumps(match, ensure_ascii=False)
            }
            
            fixtures.append(fixture)
        
        return self.repo.upsert_fixtures(fixtures)
    
    def _upsert_api_football_fixtures(self, fixtures_raw: List[Dict]) -> Dict[str, int]:
        """将 API-Football 的 fixtures 标准化并 upsert"""
        fixtures = []
        
        for fx in fixtures_raw:
            fixture_info = fx.get("fixture", {})
            fixture_id = str(fixture_info.get("id"))
            if not fixture_id:
                continue
            
            teams = fx.get("teams", {})
            home_team = (teams.get("home") or {}).get("name", "") or "TBD"
            away_team = (teams.get("away") or {}).get("name", "") or "TBD"
            
            status = fixture_info.get("status", {}).get("short", "")
            goals = fx.get("goals", {})
            home_score = goals.get("home")
            away_score = goals.get("away")
            
            # 判断胜者
            winner = None
            if home_score is not None and away_score is not None:
                if home_score > away_score:
                    winner = home_team
                elif away_score > home_score:
                    winner = away_team
                else:
                    winner = "Draw"
            
            # 解析比赛时间
            match_date_str = fixture_info.get("date")
            match_date = None
            if match_date_str:
                try:
                    match_date = datetime.fromisoformat(match_date_str)
                except:
                    pass
            
            # 构建 fixture
            # API-Football 的 round 字段可能包含阶段信息
            round_name = fx.get("league", {}).get("round", "")
            stage = self._infer_stage_from_round(round_name)
            
            fixture = {
                "fixture_id": fixture_id,
                "api_fixture_id": fixture_id,
                "home_team": home_team,
                "away_team": away_team,
                "match_date": match_date,
                "stage": stage,
                "status": status,
                "home_score": home_score,
                "away_score": away_score,
                "winner": winner,
                "source": "api_football",
                "source_level": "external_real",
                "is_verified": True,
                "needs_review": False,
                "confidence_level": "medium",
                "evidence_count": 1,
                "evidence_sources": ["api_football"],
                "canonical_pair": compute_canonical_pair(home_team, away_team),
                "raw_payload": json.dumps(fx, ensure_ascii=False)
            }
            
            fixtures.append(fixture)
        
        return self.repo.upsert_fixtures(fixtures)
    
    def get_cached_fixtures(self, season: int = 2026) -> List[Dict[str, Any]]:
        """从 fixtures 表读取缓存数据"""
        return self.repo.get_cached_fixtures(season)
    
    def _infer_stage_from_round(self, round_name: str) -> str:
        """从 API-Football 的 round 字段推断比赛阶段"""
        if not round_name:
            return "group_stage"
        round_lower = round_name.lower()
        if "group" in round_lower:
            return "group_stage"
        if "32" in round_lower or "round of 32" in round_lower:
            return "round_of_32"
        if "16" in round_lower or "round of 16" in round_lower:
            return "round_of_16"
        if "quarter" in round_lower or "1/4" in round_lower:
            return "quarter_finals"
        if "semi" in round_lower or "1/2" in round_lower:
            return "semi_finals"
        if "final" in round_lower:
            return "final"
        return "group_stage"
    
    def get_data_status(self) -> Dict[str, Any]:
        """获取当前 canonical 数据状态"""
        return self.repo.get_canonical_status()
