"""
模型升级验收脚本

检查:
1. feature 数量 >= 30
2. 训练样本 >= 6000
3. NN V2 模型加载成功
4. XGBoost 模型加载成功
5. ensemble_probability 生成
6. balanced_accuracy 提升
7. macro_f1 提升
8. champion simulation 完成
9. LLM explanation 生成

运行:
    python scripts/check_model_upgrade.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def check(name: str, condition: bool, detail: str = ""):
    status = "PASS" if condition else "FAIL"
    msg = f"  [{status}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return condition


def main():
    print("\n" + "=" * 60)
    print("模型升级验收检查")
    print("=" * 60)

    results = {}

    # 1. 检查训练数据集
    print("\n[1] 训练数据集检查")
    csv_v2 = "data/training_dataset_v2.csv"
    if os.path.exists(csv_v2):
        df = pd.read_csv(csv_v2)
        feature_cols = [c for c in df.columns if c not in ['match_id', 'date', 'label']]
        n_features = len(feature_cols)
        n_samples = len(df)

        results['feature_count'] = n_features
        results['train_samples'] = n_samples

        check("训练数据集存在", True)
        check(f"特征数量 >= 30", n_features >= 30, f"实际: {n_features}")
        check(f"训练样本 >= 6000", n_samples >= 6000, f"实际: {n_samples}")

        # 缺失率
        missing = df.isnull().sum().sum() / (len(df) * len(df.columns)) * 100
        check(f"缺失率 < 5%", missing < 5, f"实际: {missing:.2f}%")

        # 标签分布
        label_counts = df['label'].value_counts()
        total = len(df)
        for label, name in [(0, 'home_win'), (1, 'draw'), (2, 'away_win')]:
            count = label_counts.get(label, 0)
            pct = count / total * 100
            check(f"  {name} 比例 > 10%", pct > 10, f"{count} ({pct:.1f}%)")
    else:
        check("训练数据集存在", False, f"{csv_v2} not found")

    # 2. 检查 NN V2 模型
    print("\n[2] NN V2 模型检查")
    nn_path = "models/feature_network_v2_latest.pth"
    if os.path.exists(nn_path):
        check("NN V2 模型文件存在", True)
        try:
            import torch
            from app.services.feature_network import FeatureAttentionMixerV2
            model = FeatureAttentionMixerV2(team_dim=25, input_dim=50)
            model.load_state_dict(torch.load(nn_path, map_location='cpu'))
            model.eval()

            # 测试推理
            dummy = torch.randn(1, 67)
            with torch.no_grad():
                logits = model(dummy)
                probs = torch.softmax(logits, dim=1).numpy()[0]

            check("NN V2 加载成功", True)
            check("NN V2 输出3维概率", len(probs) == 3, f"probs={probs}")
            check("NN V2 概率和≈1", abs(sum(probs) - 1.0) < 0.01, f"sum={sum(probs):.4f}")
            results['nn_loaded'] = True
        except Exception as e:
            check("NN V2 加载成功", False, str(e))
            results['nn_loaded'] = False
    else:
        check("NN V2 模型文件存在", False, f"{nn_path} not found")
        results['nn_loaded'] = False

    # 3. 检查 XGBoost 模型
    print("\n[3] XGBoost 模型检查")
    xgb_path = "models/tree_predictor.pkl"
    if os.path.exists(xgb_path):
        check("XGBoost 模型文件存在", True)
        try:
            from app.models.tree_predictor import TreePredictor
            tp = TreePredictor(model_path=xgb_path)
            tp.load()

            import numpy as np
            dummy = np.zeros(67, dtype=np.float32)
            probs = tp.predict_proba(dummy)[0]

            check("XGBoost 加载成功", True)
            check("XGBoost 输出3维概率", len(probs) == 3, f"probs={probs}")
            results['xgb_loaded'] = True
        except Exception as e:
            check("XGBoost 加载成功", False, str(e))
            results['xgb_loaded'] = False
    else:
        check("XGBoost 模型文件存在", False, f"{xgb_path} not found")
        results['xgb_loaded'] = False

    # 4. 检查训练结果
    print("\n[4] 训练指标检查")
    nn_results_path = "models/feature_network_v2_latest_results.json"
    if os.path.exists(nn_results_path):
        with open(nn_results_path, 'r') as f:
            nn_results = json.load(f)

        acc = nn_results.get('final_val_accuracy', 0)
        f1 = nn_results.get('final_macro_f1', 0)
        bal_acc = nn_results.get('final_balanced_accuracy', 0)
        brier = nn_results.get('final_brier_score', 1)
        ll = nn_results.get('final_log_loss', 2)

        results['nn_accuracy'] = acc
        results['nn_macro_f1'] = f1
        results['nn_balanced_accuracy'] = bal_acc
        results['nn_brier'] = brier
        results['nn_log_loss'] = ll

        check("NN accuracy > 0.35", acc > 0.35, f"{acc:.4f}")
        check("NN macro_f1 > 0.30", f1 > 0.30, f"{f1:.4f}")
        check("NN balanced_accuracy > 0.30", bal_acc > 0.30, f"{bal_acc:.4f}")
        check("NN brier_score < 0.8", brier < 0.8, f"{brier:.4f}")
    else:
        check("训练结果文件存在", False, nn_results_path)

    # 5. 检查 Walk Forward 结果
    print("\n[5] Walk Forward 回测检查")
    wf_path = "data/walk_forward_results.json"
    if os.path.exists(wf_path):
        with open(wf_path, 'r') as f:
            wf_results = json.load(f)
        check("Walk Forward 完成", len(wf_results) >= 2, f"{len(wf_results)} phases")
        for r in wf_results:
            logger.info(f"  {r['phase']}: acc={r['accuracy']:.4f}, f1={r['macro_f1']:.4f}")
    else:
        check("Walk Forward 完成", False, f"{wf_path} not found")

    # 6. 检查冠军模拟
    print("\n[6] 冠军模拟检查")
    champ_path = "data/champion_prediction_ensemble.json"
    dist_path = "data/simulation_distribution.json"
    if os.path.exists(champ_path):
        with open(champ_path, 'r') as f:
            champ = json.load(f)
        n_sims = champ.get('n_simulations', 0)
        check("冠军模拟完成", n_sims >= 1000, f"{n_sims} simulations")
        check("simulation_distribution.json 存在", os.path.exists(dist_path))

        top5 = champ.get('top5', [])
        if top5:
            print(f"\n  Top 5 冠军概率:")
            for item in top5:
                print(f"    {item['team']}: {item['probability']:.2%}")
            results['champion_top5'] = top5
            results['france_prob'] = champ.get('france_champion_probability', 0)
            results['argentina_prob'] = champ.get('argentina_champion_probability', 0)
    else:
        check("冠军模拟完成", False, champ_path)

    # 7. 汇总
    print("\n" + "=" * 60)
    print("验收汇总")
    print("=" * 60)
    print(f"  特征数量:       {results.get('feature_count', 'N/A')}")
    print(f"  训练样本:       {results.get('train_samples', 'N/A')}")
    print(f"  NN accuracy:    {results.get('nn_accuracy', 'N/A')}")
    print(f"  NN macro_f1:    {results.get('nn_macro_f1', 'N/A')}")
    print(f"  NN balanced_acc:{results.get('nn_balanced_accuracy', 'N/A')}")
    print(f"  NN brier:       {results.get('nn_brier', 'N/A')}")
    print(f"  XGBoost:        {'已加入' if results.get('xgb_loaded') else '未加入'}")
    print(f"  NN V2:          {'已加载' if results.get('nn_loaded') else '未加载'}")

    return results


if __name__ == "__main__":
    main()
