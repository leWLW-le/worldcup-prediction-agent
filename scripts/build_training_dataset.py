"""
构建训练数据集脚本
从历史比赛数据生成用于PyTorch训练的数据集
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from app.services.training_dataset_builder import TrainingDatasetBuilder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("构建训练数据集")
    logger.info("=" * 60)
    
    builder = TrainingDatasetBuilder()
    
    try:
        stats = builder.build_dataset(
            output_file="data/training_dataset.csv",
            start_date="2010-01-01",
            end_date="2024-12-31"
        )
        
        logger.info("\n" + "=" * 60)
        logger.info("构建完成")
        logger.info("=" * 60)
        logger.info(f"总比赛数: {stats['total_matches']}")
        logger.info(f"已处理: {stats['processed']}")
        logger.info(f"跳过: {stats['skipped']}")
        logger.info(f"输出文件: {stats['output_file']}")
        
    finally:
        builder.close()
    
    logger.info("\n训练数据集构建完成！")


if __name__ == "__main__":
    main()
