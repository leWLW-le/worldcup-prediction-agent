"""
Fixture Repository - fixtures 表数据访问层

负责：
- upsert_fixtures: 写入/更新比赛数据
- get_cached_fixtures: 读取缓存的比赛数据
- get_status: 获取数据状态统计
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from app.db.database import SessionLocal
from app.models.agent_models import Fixture, compute_canonical_pair

logger = logging.getLogger(__name__)


class FixtureRepository:
    """fixtures 表的数据访问层"""
    
    def upsert_fixtures(self, fixtures: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        批量 upsert fixtures
        
        Args:
            fixtures: fixture 列表，每个 fixture 包含：
                - fixture_id (必需): 唯一标识
                - api_fixture_id: API 原始 ID
                - home_team, away_team: 球队名称
                - match_date: 比赛时间
                - status: 比赛状态
                - home_score, away_score: 比分
                - winner: 胜者
                - source: 数据来源
                - source_level: 数据可信度级别
                - is_verified: 是否已验证
                - needs_review: 是否需要审核
                - confidence_level: 置信度
                - evidence_count: 证据数量
                - evidence_sources: 证据来源列表
                - raw_payload: 原始 JSON 数据
        
        Returns:
            {
                "inserted": 新增数量,
                "updated": 更新数量,
                "skipped": 跳过数量,
                "total": 总数
            }
        
        规则：
        1. 先按 fixture_id 去重
        2. 再按逻辑键（stage + canonical_pair）去重，防止不同 fixture_id 的同一场比赛重复入库
        3. 已存在则按 source_level 优先级决定是否更新
        4. 不允许预测结果覆盖真实比分
        """
        db = SessionLocal()
        inserted = 0
        updated = 0
        skipped = 0
        
        try:
            for fx_data in fixtures:
                fixture_id = fx_data.get("fixture_id")
                if not fixture_id:
                    skipped += 1
                    continue
                
                # 确保 canonical_pair 已计算
                if "canonical_pair" not in fx_data or not fx_data.get("canonical_pair"):
                    home = fx_data.get("home_team", "")
                    away = fx_data.get("away_team", "")
                    if home and away:
                        fx_data["canonical_pair"] = compute_canonical_pair(home, away)
                
                # 查找现有记录：先按 fixture_id
                existing = db.query(Fixture).filter(
                    Fixture.fixture_id == fixture_id
                ).first()
                
                # 如果 fixture_id 没找到，再按逻辑键查找
                if not existing and fx_data.get("stage") and fx_data.get("canonical_pair"):
                    existing = db.query(Fixture).filter(
                        Fixture.stage == fx_data["stage"],
                        Fixture.canonical_pair == fx_data["canonical_pair"],
                    ).first()
                
                if existing:
                    # 检查是否允许更新（防止预测覆盖真实数据）
                    if self._should_update(existing, fx_data):
                        self._update_fixture(existing, fx_data)
                        updated += 1
                    else:
                        skipped += 1
                else:
                    # 创建新记录
                    new_fixture = self._create_fixture(fx_data)
                    db.add(new_fixture)
                    inserted += 1
            
            db.commit()
            
            return {
                "inserted": inserted,
                "updated": updated,
                "skipped": skipped,
                "total": len(fixtures)
            }
            
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
    
    def _should_update(self, existing: Fixture, new_data: Dict[str, Any]) -> bool:
        """判断是否应该更新现有记录"""
        # 如果现有记录是外部真实数据，而新数据是预测或低可信度，则不更新
        existing_source_level = existing.source_level or ""
        new_source_level = new_data.get("source_level", "")
        
        # external_real > verified_cache > unverified_candidate
        priority = {
            "external_real": 3,
            "verified_cache": 2,
            "manual_verified": 2,
            "unverified_candidate": 1,
            "unavailable": 0
        }
        
        existing_priority = priority.get(existing_source_level, 0)
        new_priority = priority.get(new_source_level, 0)
        
        # 只有新数据优先级 >= 现有数据优先级时才更新
        return new_priority >= existing_priority
    
    def _update_fixture(self, fixture: Fixture, data: Dict[str, Any]):
        """更新 fixture 字段"""
        # 只更新提供的字段
        field_mapping = {
            "api_fixture_id": "api_fixture_id",
            "home_team": "home_team",
            "away_team": "away_team",
            "home_team_id": "home_team_id",
            "away_team_id": "away_team_id",
            "match_date": "match_date",
            "stage": "stage",
            "status": "status",
            "home_score": "home_score",
            "away_score": "away_score",
            "winner": "winner",
            "source": "source",
            "source_level": "source_level",
            "is_verified": "is_verified",
            "needs_review": "needs_review",
            "confidence_level": "confidence_level",
            "evidence_count": "evidence_count",
            "evidence_sources": "evidence_sources",
            "raw_payload": "raw_payload",
            "canonical_pair": "canonical_pair",
        }
        
        for key, attr in field_mapping.items():
            if key in data and data[key] is not None:
                value = data[key]
                # evidence_sources 列表转 JSON 字符串
                if key == "evidence_sources" and isinstance(value, list):
                    value = json.dumps(value, ensure_ascii=False)
                setattr(fixture, attr, value)
        
        # 更新时间戳
        fixture.updated_at = datetime.now(timezone.utc)
    
    def _create_fixture(self, data: Dict[str, Any]) -> Fixture:
        """创建新的 fixture 记录"""
        now = datetime.now(timezone.utc)
        
        # 处理 evidence_sources（如果是列表，转为 JSON 字符串）
        evidence_sources = data.get("evidence_sources")
        if isinstance(evidence_sources, list):
            evidence_sources = json.dumps(evidence_sources, ensure_ascii=False)
        
        # 确保 canonical_pair 已计算
        canonical_pair = data.get("canonical_pair")
        if not canonical_pair:
            home = data.get("home_team", "")
            away = data.get("away_team", "")
            if home and away:
                canonical_pair = compute_canonical_pair(home, away)
        
        return Fixture(
            fixture_id=data["fixture_id"],
            api_fixture_id=data.get("api_fixture_id"),
            home_team=data.get("home_team", ""),
            away_team=data.get("away_team", ""),
            home_team_id=data.get("home_team_id"),
            away_team_id=data.get("away_team_id"),
            match_date=data.get("match_date"),
            stage=data.get("stage"),
            status=data.get("status"),
            home_score=data.get("home_score"),
            away_score=data.get("away_score"),
            winner=data.get("winner"),
            source=data.get("source"),
            source_level=data.get("source_level"),
            is_verified=data.get("is_verified", False),
            needs_review=data.get("needs_review", False),
            confidence_level=data.get("confidence_level"),
            evidence_count=data.get("evidence_count", 0),
            evidence_sources=evidence_sources,
            canonical_pair=canonical_pair,
            fetched_at=now,
            updated_at=now,
            raw_payload=data.get("raw_payload")
        )
    
    def get_canonical_fixtures(self, season: int = 2026) -> List[Dict[str, Any]]:
        """
        获取 canonical fixtures（当前应使用的比赛数据）
        
        规则：
        1. 优先读取 source="football_data" 且 source_level="external_real" 的数据
        2. 如果 football_data external_real 数量 >= 104，只返回这批数据
        3. 不混入旧 db_cache、local_fallback、manual_candidate、agent_prediction 数据
        4. 如果 football_data 不足 104，再按 source_level 兜底读取 verified_cache
        
        Returns:
            {
                "fixtures": fixture 列表,
                "canonical_count": canonical 数量,
                "source": 数据来源,
                "source_level": 数据级别
            }
        """
        db = SessionLocal()
        try:
            # 1. 尝试 football_data external_real（包含所有阶段，不再过滤 confidence_level）
            fd_fixtures = db.query(Fixture).filter(
                Fixture.source == "football_data",
                Fixture.source_level == "external_real",
            ).all()
            
            if len(fd_fixtures) >= 104:
                return {
                    "fixtures": [self._fixture_to_dict(fx) for fx in fd_fixtures],
                    "canonical_count": len(fd_fixtures),
                    "source": "football_data",
                    "source_level": "external_real"
                }
            
            # 2. 尝试 api_football external_real
            af_fixtures = db.query(Fixture).filter(
                Fixture.source == "api_football",
                Fixture.source_level == "external_real"
            ).all()
            
            if len(af_fixtures) > 0:
                return {
                    "fixtures": [self._fixture_to_dict(fx) for fx in af_fixtures],
                    "canonical_count": len(af_fixtures),
                    "source": "api_football",
                    "source_level": "external_real"
                }
            
            # 3. 兜底：读取 verified_cache
            vc_fixtures = db.query(Fixture).filter(
                Fixture.source_level.in_(["verified_cache", "manual_verified"])
            ).all()
            
            if len(vc_fixtures) > 0:
                return {
                    "fixtures": [self._fixture_to_dict(fx) for fx in vc_fixtures],
                    "canonical_count": len(vc_fixtures),
                    "source": vc_fixtures[0].source or "db_cache",
                    "source_level": "verified_cache"
                }
            
            # 4. 无可用数据
            return {
                "fixtures": [],
                "canonical_count": 0,
                "source": "unavailable",
                "source_level": "unavailable"
            }
        finally:
            db.close()
    
    def get_canonical_status(self) -> Dict[str, Any]:
        """
        获取 canonical fixtures 的状态（不是表总状态）
        """
        canonical = self.get_canonical_fixtures()
        count = canonical["canonical_count"]
        source = canonical["source"]
        source_level = canonical["source_level"]
        
        is_external_realtime = source_level == "external_real"
        
        # 获取 canonical fixtures 的 last_updated
        db = SessionLocal()
        try:
            if source == "football_data" and source_level == "external_real":
                last = db.query(Fixture.updated_at).filter(
                    Fixture.source == "football_data",
                    Fixture.source_level == "external_real",
                ).order_by(Fixture.updated_at.desc()).first()
            elif source == "api_football":
                last = db.query(Fixture.updated_at).filter(
                    Fixture.source == "api_football",
                    Fixture.source_level == "external_real"
                ).order_by(Fixture.updated_at.desc()).first()
            else:
                last = db.query(Fixture.updated_at).order_by(Fixture.updated_at.desc()).first()
            
            last_updated = last[0].isoformat() if last and last[0] else None
        finally:
            db.close()
        
        if count == 0:
            user_message = "当前比赛数据不足，请先刷新数据源。"
        elif is_external_realtime:
            user_message = "比赛数据已更新。"
        else:
            user_message = "暂时无法刷新，已使用最近一次真实缓存。"
        
        return {
            "fixtures_count": count,
            "source": source,
            "source_level": source_level,
            "is_external_realtime": is_external_realtime,
            "last_updated": last_updated,
            "user_message": user_message
        }
    
    def get_cached_fixtures(self, season: int = 2026) -> List[Dict[str, Any]]:
        """
        从 fixtures 表读取 canonical 数据（向后兼容）
        
        Returns:
            fixture 列表（字典格式）
        """
        result = self.get_canonical_fixtures(season)
        return result["fixtures"]
    
    def get_knockout_fixtures(self) -> List[Dict[str, Any]]:
        """
        获取淘汰赛阶段的 fixtures（从所有受信外部源中读取）

        返回所有 stage 不是 group_stage 的 external_real 记录，
        包括已结束的（有真实比分）和未开始的（待预测）。

        注意：source 字段可能被不同同步路径覆盖（football_data ↔ real_result），
        因此不再限制 source == "football_data"，而是接受所有受信外部源。

        Returns:
            fixture 字典列表，每个包含 stage, status, home_team, away_team, home_score, away_score, winner 等
        """
        db = SessionLocal()
        try:
            # 淘汰赛 = 所有非 group_stage 的 external_real 记录（不限 source）
            fixtures = db.query(Fixture).filter(
                Fixture.source.in_(["football_data", "real_result", "api-sports", "api_football"]),
                Fixture.source_level == "external_real",
                Fixture.stage != "group_stage",
                Fixture.stage.isnot(None),
            ).order_by(Fixture.match_date.asc()).all()

            result = [self._fixture_to_dict(fx) for fx in fixtures]

            # 诊断日志：按 stage 统计
            from collections import Counter
            stage_counts = Counter(fx.get("stage") for fx in result)
            logger.info("[FixtureRepo] get_knockout_fixtures: %d 场淘汰赛, 按 stage: %s",
                        len(result), dict(stage_counts))

            # 特别记录决赛状态
            final_fixtures = [fx for fx in result if fx.get("stage") == "final"]
            if final_fixtures:
                ff = final_fixtures[0]
                logger.info("[FixtureRepo] 决赛 fixture: %s vs %s, score=%s-%s, status=%s, source=%s",
                            ff.get("home_team"), ff.get("away_team"),
                            ff.get("home_score"), ff.get("away_score"),
                            ff.get("status"), ff.get("source"))
            else:
                logger.warning("[FixtureRepo] 未找到决赛 fixture！")

            return result
        finally:
            db.close()

    def get_final_match(self) -> Optional[Dict[str, Any]]:
        """直接查询决赛 fixture（不依赖 source 过滤）。

        用于兜底：当 get_knockout_fixtures() 因 source 字段问题查不到决赛时，
        直接按 stage 查询决赛记录。

        Returns:
            fixture 字典或 None
        """
        db = SessionLocal()
        try:
            fx = db.query(Fixture).filter(
                Fixture.stage.in_(["final", "FINAL", "Final"]),
                Fixture.source_level == "external_real",
                Fixture.home_team != "TBD",
                Fixture.away_team != "TBD",
            ).order_by(Fixture.match_date.desc()).first()

            if fx:
                result = self._fixture_to_dict(fx)
                logger.info("[FixtureRepo] get_final_match: %s vs %s, %s-%s, status=%s, source=%s",
                            result.get("home_team"), result.get("away_team"),
                            result.get("home_score"), result.get("away_score"),
                            result.get("status"), result.get("source"))
                return result
            else:
                logger.warning("[FixtureRepo] get_final_match: 未找到决赛记录")
                return None
        finally:
            db.close()
    
    def _fixture_to_dict(self, fx: Fixture) -> Dict[str, Any]:
        """将 Fixture ORM 对象转为字典"""
        evidence_sources = fx.evidence_sources
        if evidence_sources:
            try:
                evidence_sources = json.loads(evidence_sources)
            except:
                pass
        
        return {
            "fixture_id": fx.fixture_id,
            "api_fixture_id": fx.api_fixture_id,
            "home_team": fx.home_team,
            "away_team": fx.away_team,
            "home_team_id": fx.home_team_id,
            "away_team_id": fx.away_team_id,
            "match_date": fx.match_date.isoformat() if fx.match_date else None,
            "stage": fx.stage,
            "status": fx.status,
            "home_score": fx.home_score,
            "away_score": fx.away_score,
            "winner": fx.winner,
            "source": fx.source,
            "source_level": fx.source_level,
            "is_verified": fx.is_verified,
            "needs_review": fx.needs_review,
            "confidence_level": fx.confidence_level,
            "evidence_count": fx.evidence_count,
            "evidence_sources": evidence_sources,
            "canonical_pair": fx.canonical_pair,
            "fetched_at": fx.fetched_at.isoformat() if fx.fetched_at else None,
            "updated_at": fx.updated_at.isoformat() if fx.updated_at else None,
            "raw_payload": fx.raw_payload
        }
    
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取 fixtures 表状态统计
        
        Returns:
            {
                "fixtures_count": 总数量,
                "source_distribution": {"football_data": 10, "api_football": 5},
                "source_level_distribution": {"external_real": 15},
                "confidence_distribution": {"high": 5, "medium": 10},
                "needs_review_count": 需要审核的数量,
                "last_updated": 最后更新时间
            }
        """
        db = SessionLocal()
        try:
            # 总数量
            total = db.query(Fixture).count()
            
            # source 分布
            source_dist = {}
            sources = db.query(Fixture.source, func.count(Fixture.id)) \
                       .group_by(Fixture.source).all()
            for source, count in sources:
                if source:
                    source_dist[source] = count
            
            # source_level 分布
            source_level_dist = {}
            source_levels = db.query(Fixture.source_level, func.count(Fixture.id)) \
                            .group_by(Fixture.source_level).all()
            for level, count in source_levels:
                if level:
                    source_level_dist[level] = count
            
            # confidence_level 分布
            confidence_dist = {}
            confidences = db.query(Fixture.confidence_level, func.count(Fixture.id)) \
                          .group_by(Fixture.confidence_level).all()
            for conf, count in confidences:
                if conf:
                    confidence_dist[conf] = count
            
            # needs_review 数量
            needs_review_count = db.query(Fixture).filter(
                Fixture.needs_review == True
            ).count()
            
            # 最后更新时间
            last_updated = db.query(Fixture.updated_at) \
                           .order_by(Fixture.updated_at.desc()) \
                           .first()
            last_updated_str = last_updated[0].isoformat() if last_updated and last_updated[0] else None
            
            return {
                "fixtures_count": total,
                "source_distribution": source_dist,
                "source_level_distribution": source_level_dist,
                "confidence_distribution": confidence_dist,
                "needs_review_count": needs_review_count,
                "last_updated": last_updated_str
            }
            
        finally:
            db.close()
