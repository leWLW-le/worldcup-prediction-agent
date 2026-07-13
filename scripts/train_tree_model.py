"""
训练 XGBoost 树模型

运行:
    python scripts/train_tree_model.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from app.models.tree_predictor import TreePredictor

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def main():
    logger.info("=== 训练 XGBoost 树模型 ===")

    predictor = TreePredictor(model_path="models/tree_predictor.pkl")
    results = predictor.train(csv_file="data/training_dataset_v2.csv")

    print("\n=== XGBoost Training Completed ===")
    for k, v in results.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        else:
            print(f"  {k}: {v}")

    return results


if __name__ == "__main__":
    main()
