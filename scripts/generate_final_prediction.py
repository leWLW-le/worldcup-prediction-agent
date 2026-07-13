"""
生成 data/final_prediction_result.json

从 champion_prediction_ensemble.json + walk_forward_results.json + DB 汇总最终预测结果。

运行:
    python scripts/generate_final_prediction.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def generate():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # 1. 读取蒙特卡洛模拟结果
    sim_path = os.path.join(base_dir, "data", "champion_prediction_ensemble.json")
    if not os.path.exists(sim_path):
        logger.error("champion_prediction_ensemble.json not found. Run run_champion_simulation.py first.")
        return None

    with open(sim_path, "r", encoding="utf-8") as f:
        sim_data = json.load(f)

    champion = sim_data["top_champion"]
    champion_prob = sim_data["top_probability"]
    top5 = sim_data["top5"]
    n_simulations = sim_data["n_simulations"]

    # 2. 读取 Walk Forward 评估结果（可选）
    wf_path = os.path.join(base_dir, "data", "walk_forward_results.json")
    walk_forward = None
    if os.path.exists(wf_path):
        with open(wf_path, "r", encoding="utf-8") as f:
            walk_forward = json.load(f)

    # 3. 统计训练样本数
    training_csv = os.path.join(base_dir, "data", "training_dataset_v2.csv")
    historical_samples = 0
    if os.path.exists(training_csv):
        with open(training_csv, "r", encoding="utf-8") as f:
            historical_samples = sum(1 for _ in f) - 1  # 减去 header

    # 4. 检查数据来源
    data_source = "fixtures_table"
    try:
        from app.db.database import SessionLocal
        from app.services.fixture_repository import FixtureRepository
        db = SessionLocal()
        repo = FixtureRepository()
        canon = repo.get_canonical_fixtures()
        fixtures = canon.get("fixtures", [])
        finished = [fx for fx in fixtures if fx.get("status") in ("FT", "AET", "PEN", "FINISHED")]
        data_source = f"fixtures_table ({len(finished)}/{len(fixtures)} finished)"
        db.close()
    except Exception as e:
        logger.warning("Failed to query fixtures count: %s", e)

    # 5. 检查模型版本
    model_version = "ensemble_v2"
    model_files = {
        "nn_v2": os.path.join(base_dir, "models", "feature_network_v2_latest.pth"),
        "xgboost": os.path.join(base_dir, "models", "tree_predictor.pkl"),
        "feature_stats": os.path.join(base_dir, "models", "feature_stats_v2.json"),
    }
    model_status = {}
    for name, path in model_files.items():
        model_status[name] = os.path.exists(path)

    # 6. 构建最终结果
    result = {
        "champion": champion,
        "champion_probability": champion_prob,
        "top5": top5,
        "model_version": model_version,
        "simulation_count": n_simulations,
        "data_source": data_source,
        "historical_samples": historical_samples,
        "model_files_loaded": model_status,
        "walk_forward_summary": None,
    }

    if walk_forward:
        avg_acc = sum(p["accuracy"] for p in walk_forward) / len(walk_forward)
        avg_f1 = sum(p["macro_f1"] for p in walk_forward) / len(walk_forward)
        result["walk_forward_summary"] = {
            "n_phases": len(walk_forward),
            "avg_accuracy": round(avg_acc, 4),
            "avg_macro_f1": round(avg_f1, 4),
        }

    # 7. 写入文件
    out_path = os.path.join(base_dir, "data", "final_prediction_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info("Written to %s", out_path)
    logger.info("Champion: %s (%.1f%%)", champion, champion_prob * 100)
    logger.info("Simulations: %d", n_simulations)
    logger.info("Historical samples: %d", historical_samples)
    logger.info("Data source: %s", data_source)

    return result


if __name__ == "__main__":
    generate()
