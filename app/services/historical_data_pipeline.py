"""
历史数据管线服务模块
负责从CSV/公开数据源导入、清洗、标准化历史比赛数据
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

from app.db.database import SessionLocal
from app.models.schemas import Team

logger = logging.getLogger(__name__)


class HistoricalDataPipeline:
    """
    历史数据管线
    
    流程：
    CSV/公开数据 → 清洗 → 球队名称标准化 → historical_matches数据库
    """
    
    def __init__(self, db: Optional[Session] = None):
        """
        初始化管线
        
        Args:
            db: 数据库会话，如果为None则创建新会话
        """
        self.db = db or SessionLocal()
        self._team_cache = {}
        self._alias_cache = {}
    
    def close(self):
        """关闭数据库会话"""
        if self.db:
            self.db.close()
    
    def load_team_aliases(self, alias_file: str = "data/team_aliases.csv") -> Dict[str, str]:
        """
        加载球队名称映射表
        
        Args:
            alias_file: 别名CSV文件路径
            
        Returns:
            映射字典 {raw_name: standard_name}
        """
        try:
            df = pd.read_csv(alias_file)
            alias_map = {}
            
            for _, row in df.iterrows():
                raw_name = str(row.get('raw_name', '')).strip()
                standard_name = str(row.get('standard_name', '')).strip()
                
                if raw_name and standard_name:
                    alias_map[raw_name.lower()] = standard_name
            
            self._alias_cache = alias_map
            logger.info(f"Loaded {len(alias_map)} team aliases")
            return alias_map
            
        except Exception as e:
            logger.error(f"Failed to load team aliases: {e}")
            return {}
    
    def standardize_team_name(self, team_name: str) -> str:
        """
        标准化球队名称
        
        Args:
            team_name: 原始球队名称
            
        Returns:
            标准化后的球队名称
        """
        if not team_name:
            return team_name
        
        team_lower = team_name.strip().lower()
        
        # 检查别名缓存
        if team_lower in self._alias_cache:
            return self._alias_cache[team_lower]
        
        # 常见映射规则
        mappings = {
            'usa': 'United States',
            'united states': 'United States',
            'south korea': 'Korea Republic',
            'korea republic': 'Korea Republic',
            'iran': 'IR Iran',
            'ir iran': 'IR Iran',
            'czech republic': 'Czechia',
            'czechia': 'Czechia',
        }
        
        if team_lower in mappings:
            return mappings[team_lower]
        
        # 返回原始名称（首字母大写）
        return team_name.strip().title()
    
    def get_or_create_team(self, team_name: str) -> Optional[int]:
        """
        获取或创建球队记录
        
        Args:
            team_name: 球队名称
            
        Returns:
            球队ID，如果失败返回None
        """
        if not team_name:
            return None
        
        # 检查缓存
        if team_name in self._team_cache:
            return self._team_cache[team_name]
        
        # 查询数据库
        team = self.db.query(Team).filter(Team.name == team_name).first()
        
        if team:
            self._team_cache[team_name] = team.id
            return team.id
        
        # 创建新球队（使用默认ELO）
        new_team = Team(
            name=team_name,
            current_elo=1500.0,
            confederation=None
        )
        
        try:
            self.db.add(new_team)
            self.db.commit()
            self.db.refresh(new_team)
            self._team_cache[team_name] = new_team.id
            logger.info(f"Created new team: {team_name} (ID: {new_team.id})")
            return new_team.id
        except Exception as e:
            logger.error(f"Failed to create team {team_name}: {e}")
            self.db.rollback()
            return None
    
    def clean_match_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        清洗比赛数据
        
        Args:
            df: 原始DataFrame
            
        Returns:
            清洗后的DataFrame
        """
        # 移除空行
        df = df.dropna(how='all')
        
        # 移除关键字段缺失的行
        required_cols = ['date', 'home_team', 'away_team', 'home_score', 'away_score']
        df = df.dropna(subset=required_cols)
        
        # 转换日期格式
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date'])
        
        # 确保比分为数值类型
        df['home_score'] = pd.to_numeric(df['home_score'], errors='coerce')
        df['away_score'] = pd.to_numeric(df['away_score'], errors='coerce')
        df = df.dropna(subset=['home_score', 'away_score'])
        
        # 过滤异常比分
        df = df[(df['home_score'] >= 0) & (df['home_score'] <= 20)]
        df = df[(df['away_score'] >= 0) & (df['away_score'] <= 20)]
        
        # 标准化球队名称
        df['home_team'] = df['home_team'].apply(self.standardize_team_name)
        df['away_team'] = df['away_team'].apply(self.standardize_team_name)
        
        # 添加result字段
        def determine_result(row):
            if row['home_score'] > row['away_score']:
                return 'home_win'
            elif row['home_score'] < row['away_score']:
                return 'away_win'
            else:
                return 'draw'
        
        df['result'] = df.apply(determine_result, axis=1)
        
        # 添加competition_weight（默认0.5）
        if 'competition_weight' not in df.columns:
            df['competition_weight'] = 0.5
        
        # 添加neutral字段（默认True）
        if 'neutral' not in df.columns:
            df['neutral'] = True
        
        # 添加source字段
        if 'source' not in df.columns:
            df['source'] = 'csv_import'
        
        logger.info(f"Cleaned data: {len(df)} matches remaining")
        return df
    
    def import_matches(
        self,
        csv_file: str,
        source: str = "csv_import"
    ) -> Dict[str, int]:
        """
        从CSV导入历史比赛数据
        
        Args:
            csv_file: CSV文件路径
            source: 数据来源标识
            
        Returns:
            导入统计信息
        """
        stats = {
            'total_rows': 0,
            'imported_rows': 0,
            'skipped_rows': 0,
            'duplicated_rows': 0,
            'source': source
        }
        
        try:
            # 读取CSV
            df = pd.read_csv(csv_file)
            stats['total_rows'] = len(df)
            
            # 清洗数据
            df = self.clean_match_data(df)
            
            # 检查重复
            df = df.drop_duplicates(
                subset=['date', 'home_team', 'away_team'],
                keep='first'
            )
            stats['duplicated_rows'] = stats['total_rows'] - len(df)
            
            # 加载别名映射
            if not self._alias_cache:
                self.load_team_aliases()
            
            # 逐行导入
            for _, row in df.iterrows():
                try:
                    # 获取球队ID
                    home_team_id = self.get_or_create_team(row['home_team'])
                    away_team_id = self.get_or_create_team(row['away_team'])
                    
                    if not home_team_id or not away_team_id:
                        stats['skipped_rows'] += 1
                        continue
                    
                    # 检查是否已存在
                    check_date = row['date']
                    if hasattr(check_date, 'to_pydatetime'):
                        check_date = check_date.to_pydatetime()
                    
                    existing = self.db.execute(
                        text("""
                            SELECT id FROM historical_matches
                            WHERE date = :date
                            AND home_team_id = :home_id
                            AND away_team_id = :away_id
                        """),
                        {
                            'date': check_date,
                            'home_id': home_team_id,
                            'away_id': away_team_id
                        }
                    ).fetchone()
                    
                    if existing:
                        stats['duplicated_rows'] += 1
                        continue
                    
                    # 插入新记录
                    # 转换日期类型
                    match_date = row['date']
                    if hasattr(match_date, 'to_pydatetime'):
                        match_date = match_date.to_pydatetime()
                    
                    self.db.execute(
                        text("""
                            INSERT INTO historical_matches
                            (date, home_team_id, away_team_id, home_score, away_score,
                             result, competition, competition_weight, neutral, source, created_at)
                            VALUES
                            (:date, :home_id, :away_id, :home_score, :away_score,
                             :result, :competition, :weight, :neutral, :source, :created_at)
                        """),
                        {
                            'date': match_date,
                            'home_id': home_team_id,
                            'away_id': away_team_id,
                            'home_score': int(row['home_score']),
                            'away_score': int(row['away_score']),
                            'result': row['result'],
                            'competition': row.get('tournament', 'Unknown'),
                            'weight': row.get('competition_weight', 0.5),
                            'neutral': bool(row.get('neutral', True)),
                            'source': source,
                            'created_at': datetime.utcnow()
                        }
                    )
                    
                    stats['imported_rows'] += 1
                    
                except Exception as e:
                    logger.error(f"Failed to import match: {e}")
                    stats['skipped_rows'] += 1
                    continue
            
            self.db.commit()
            logger.info(f"Import completed: {stats}")
            
        except Exception as e:
            logger.error(f"Import failed: {e}")
            self.db.rollback()
            raise
        
        return stats
    
    def get_historical_matches(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        team_id: Optional[int] = None,
        limit: int = 1000
    ) -> List[Dict]:
        """
        查询历史比赛数据
        
        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            team_id: 球队ID（可选）
            limit: 返回数量限制
            
        Returns:
            比赛记录列表
        """
        query = """
            SELECT
                hm.id,
                hm.date,
                t1.name as home_team,
                t2.name as away_team,
                hm.home_score,
                hm.away_score,
                hm.result,
                hm.competition,
                hm.competition_weight,
                hm.neutral,
                hm.source
            FROM historical_matches hm
            JOIN teams t1 ON hm.home_team_id = t1.id
            JOIN teams t2 ON hm.away_team_id = t2.id
            WHERE 1=1
        """
        
        params = {}
        
        if start_date:
            query += " AND hm.date >= :start_date"
            params['start_date'] = start_date
        
        if end_date:
            query += " AND hm.date <= :end_date"
            params['end_date'] = end_date
        
        if team_id:
            query += " AND (hm.home_team_id = :team_id OR hm.away_team_id = :team_id)"
            params['team_id'] = team_id
        
        query += " ORDER BY hm.date DESC LIMIT :limit"
        params['limit'] = limit
        
        try:
            results = self.db.execute(text(query), params).fetchall()
            
            matches = []
            for row in results:
                matches.append({
                    'id': row[0],
                    'date': row[1],
                    'home_team': row[2],
                    'away_team': row[3],
                    'home_score': row[4],
                    'away_score': row[5],
                    'result': row[6],
                    'competition': row[7],
                    'competition_weight': row[8],
                    'neutral': row[9],
                    'source': row[10]
                })
            
            return matches
            
        except Exception as e:
            logger.error(f"Failed to query historical matches: {e}")
            return []
    
    def get_statistics(self) -> Dict:
        """
        获取历史数据统计信息
        
        Returns:
            统计信息字典
        """
        try:
            # 总比赛数
            total_matches = self.db.execute(
                text("SELECT COUNT(*) FROM historical_matches")
            ).scalar() or 0
            
            # 时间跨度
            date_range = self.db.execute(
                text("""
                    SELECT
                        MIN(date) as min_date,
                        MAX(date) as max_date
                    FROM historical_matches
                """)
            ).fetchone()
            
            # 球队数量
            team_count = self.db.execute(
                text("""
                    SELECT COUNT(DISTINCT home_team_id) +
                           COUNT(DISTINCT away_team_id)
                    FROM historical_matches
                """)
            ).scalar() or 0
            
            # 结果分布
            result_dist = self.db.execute(
                text("""
                    SELECT result, COUNT(*) as count
                    FROM historical_matches
                    GROUP BY result
                """)
            ).fetchall()
            
            result_stats = {row[0]: row[1] for row in result_dist}
            
            return {
                'total_matches': total_matches,
                'date_range': {
                    'min': str(date_range[0]) if date_range[0] else None,
                    'max': str(date_range[1]) if date_range[1] else None
                },
                'unique_teams': team_count,
                'result_distribution': result_stats
            }
            
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}
