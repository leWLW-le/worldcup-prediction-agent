"""
预测快照 DB 读写服务

提供 save / load 操作，将完整的 prediction snapshot 存入 PostgreSQL，
解决 Render 临时文件系统导致 JSON 数据丢失的问题。
"""
import json
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def save_prediction_snapshot(snapshot: Dict) -> bool:
    """将预测快照保存到数据库。

    Args:
        snapshot: 完整的 canonical prediction snapshot

    Returns:
        True 如果保存成功，False 否则
    """
    try:
        from app.db.database import SessionLocal
        from app.models.agent_models import PredictionSnapshot

        db = SessionLocal()
        try:
            run_id = snapshot.get("run_id", "")
            if not run_id:
                logger.warning("[SnapshotDB] run_id 为空，跳过 DB 保存")
                return False

            # 检查是否已存在相同 run_id
            existing = db.query(PredictionSnapshot).filter_by(run_id=run_id).first()
            if existing:
                existing.snapshot_json = json.dumps(snapshot, ensure_ascii=False)
                existing.status = snapshot.get("status", "completed")
                logger.info("[SnapshotDB] 更新已有 snapshot: run_id=%s", run_id)
            else:
                record = PredictionSnapshot(
                    run_id=run_id,
                    status=snapshot.get("status", "completed"),
                    snapshot_json=json.dumps(snapshot, ensure_ascii=False),
                )
                db.add(record)
                logger.info("[SnapshotDB] 新建 snapshot: run_id=%s", run_id)

            db.commit()
            logger.info("[SnapshotDB] 保存成功: run_id=%s", run_id)
            return True
        except Exception as e:
            logger.error("[SnapshotDB] 保存失败: %s", e)
            db.rollback()
            return False
        finally:
            db.close()
    except Exception as e:
        logger.error("[SnapshotDB] 数据库连接失败: %s", e)
        return False


def load_latest_prediction_snapshot() -> Optional[Dict]:
    """从数据库加载最新的 completed 预测快照。

    Returns:
        完整的 prediction snapshot dict，如果没有有效记录则返回 None
    """
    try:
        from app.db.database import SessionLocal
        from app.models.agent_models import PredictionSnapshot

        db = SessionLocal()
        try:
            record = (
                db.query(PredictionSnapshot)
                .filter_by(status="completed")
                .order_by(PredictionSnapshot.created_at.desc())
                .first()
            )
            if record:
                snapshot = json.loads(record.snapshot_json)
                logger.info("[SnapshotDB] 加载成功: run_id=%s", record.run_id)
                return snapshot
            else:
                logger.info("[SnapshotDB] 无 completed snapshot")
                return None
        finally:
            db.close()
    except Exception as e:
        logger.error("[SnapshotDB] 加载失败: %s", e)
        return None
