"""
历史数据导入工具
提供从CSV文件导入历史比赛数据的功能
"""
from typing import Dict, Optional
import logging

from app.services.historical_data_pipeline import HistoricalDataPipeline
from app.db.database import SessionLocal

logger = logging.getLogger(__name__)


class HistoricalDataImportTool:
    """
    历史数据导入工具
    
    功能：
    1. 读取CSV
    2. 清洗空数据
    3. 过滤异常比分（score < 0 或 score > 20）
    4. 标准化球队名称
    5. 写入数据库
    """
    
    def __init__(self):
        """初始化工具"""
        self.pipeline = None
    
    def import_historical_matches(
        self,
        csv_file: str,
        source: str = "csv_import"
    ) -> Dict:
        """
        导入历史比赛数据
        
        Args:
            csv_file: CSV文件路径
            source: 数据来源标识
            
        Returns:
            导入统计信息:
            {
                "total_rows": 总行数,
                "imported_rows": 成功导入行数,
                "skipped_rows": 跳过行数,
                "duplicated_rows": 重复行数,
                "source": 数据来源
            }
        """
        try:
            # 创建管线
            self.pipeline = HistoricalDataPipeline()
            
            # 执行导入
            stats = self.pipeline.import_matches(csv_file, source)
            
            # 关闭管线
            self.pipeline.close()
            
            logger.info(f"Historical data import completed: {stats}")
            
            return {
                "success": True,
                "data": stats,
                "message": f"Successfully imported {stats['imported_rows']} matches"
            }
            
        except Exception as e:
            logger.error(f"Failed to import historical matches: {e}")
            
            if self.pipeline:
                self.pipeline.close()
            
            return {
                "success": False,
                "data": {
                    "total_rows": 0,
                    "imported_rows": 0,
                    "skipped_rows": 0,
                    "duplicated_rows": 0,
                    "source": source
                },
                "error_type": type(e).__name__,
                "message": str(e)
            }
    
    def get_statistics(self) -> Dict:
        """
        获取历史数据统计信息
        
        Returns:
            统计信息字典
        """
        try:
            pipeline = HistoricalDataPipeline()
            stats = pipeline.get_statistics()
            pipeline.close()
            
            return {
                "success": True,
                "data": stats,
                "message": "Statistics retrieved successfully"
            }
            
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {
                "success": False,
                "data": {},
                "error_type": type(e).__name__,
                "message": str(e)
            }


# 工具注册信息
TOOL_NAME = "import_historical_matches"
TOOL_DESCRIPTION = "从CSV文件导入历史比赛数据到数据库"
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "import_historical_matches",
        "description": "从CSV文件导入历史比赛数据到数据库",
        "parameters": {
            "type": "object",
            "properties": {
                "csv_file": {
                    "type": "string",
                    "description": "CSV文件路径"
                },
                "source": {
                    "type": "string",
                    "description": "数据来源标识",
                    "default": "csv_import"
                }
            },
            "required": ["csv_file"]
        }
    }
}
