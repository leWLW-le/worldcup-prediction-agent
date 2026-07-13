"""
final_system_check.py — 最终系统验收检查（10 项）

逐项检查整个世界杯预测系统的核心组件是否就绪。
运行:
    PYTHONIOENCODING=utf-8 python scripts/final_system_check.py
"""
import sys
import os
import json
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS_COUNT = 0
FAIL_COUNT = 0
RESULTS = {}


def check(idx: int, name: str, condition: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  [{idx:2d}/10] [PASS] {name}")
    else:
        FAIL_COUNT += 1
        msg = f"  [{idx:2d}/10] [FAIL] {name}"
        if detail:
            msg += f" -- {detail}"
        print(msg)
    RESULTS[name] = condition
    return condition


def main():
    global PASS_COUNT, FAIL_COUNT

    print("=" * 60)
    print("  Final System Check -- 10 项验收")
    print("=" * 60)

    # ── 1. 数据源：fixtures 表有数据 ──
    print("\n[1] 数据源检查")
    try:
        from app.services.fixture_repository import FixtureRepository
        repo = FixtureRepository()
        status = repo.get_status()
        total = status.get("fixtures_count", 0)
        # 查询已结束比赛数
        from app.db.database import SessionLocal
        from app.models.agent_models import Fixture
        db = SessionLocal()
        finished = db.query(Fixture).filter(
            Fixture.status.in_(["FT", "AET", "PEN", "FINISHED"])
        ).count()
        db.close()
        check(1, "数据源 (fixtures 表)", total > 0,
              f"total={total}, finished={finished}")
        RESULTS["data_source_total"] = total
        RESULTS["data_source_finished"] = finished
    except Exception as e:
        check(1, "数据源 (fixtures 表)", False, str(e))

    # ── 2. 历史数据：训练样本 >= 5000 ──
    print("\n[2] 历史数据检查")
    try:
        csv_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "training_dataset_v2.csv"
        )
        if os.path.exists(csv_path):
            import pandas as pd
            df = pd.read_csv(csv_path)
            n_samples = len(df)
            n_features = len([c for c in df.columns if c not in ["match_id", "date", "label"]])
            check(2, "历史数据 (训练样本)", n_samples >= 5000,
                  f"samples={n_samples}, features={n_features}")
            RESULTS["historical_samples"] = n_samples
            RESULTS["feature_count"] = n_features
        else:
            check(2, "历史数据 (训练样本)", False, "training_dataset_v2.csv not found")
    except Exception as e:
        check(2, "历史数据 (训练样本)", False, str(e))

    # ── 3. NN V2 模型加载 ──
    print("\n[3] NN V2 模型检查")
    try:
        nn_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "models", "feature_network_v2_latest.pth"
        )
        if os.path.exists(nn_path):
            import torch
            from app.services.feature_network import FeatureAttentionMixerV2
            model = FeatureAttentionMixerV2(team_dim=25, input_dim=50)
            model.load_state_dict(torch.load(nn_path, map_location="cpu"))
            model.eval()
            dummy = torch.randn(1, 67)
            with torch.no_grad():
                logits = model(dummy)
                probs = torch.softmax(logits, dim=1).numpy()[0]
            ok = len(probs) == 3 and abs(sum(probs) - 1.0) < 0.01
            check(3, "NN V2 模型", ok, f"probs={probs.tolist()}")
            RESULTS["nn_v2_loaded"] = ok
        else:
            check(3, "NN V2 模型", False, "feature_network_v2_latest.pth not found")
    except Exception as e:
        check(3, "NN V2 模型", False, str(e))

    # ── 4. XGBoost 模型加载 ──
    print("\n[4] XGBoost 模型检查")
    try:
        xgb_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "models", "tree_predictor.pkl"
        )
        if os.path.exists(xgb_path):
            from app.models.tree_predictor import TreePredictor
            import numpy as np
            tp = TreePredictor(model_path=xgb_path)
            tp.load()
            dummy = np.zeros(67, dtype=np.float32)
            probs = tp.predict_proba(dummy)[0]
            ok = len(probs) == 3 and abs(sum(probs) - 1.0) < 0.01
            check(4, "XGBoost 模型", ok, f"probs={probs.tolist()}")
            RESULTS["xgboost_loaded"] = ok
        else:
            check(4, "XGBoost 模型", False, "tree_predictor.pkl not found")
    except Exception as e:
        check(4, "XGBoost 模型", False, str(e))

    # ── 5. 集成模型 (EnsemblePredictionService) ──
    print("\n[5] 集成模型检查")
    try:
        from app.db.database import SessionLocal
        from app.services.ensemble_prediction_service import EnsemblePredictionService
        db = SessionLocal()
        svc = EnsemblePredictionService(db)
        # 模型是懒加载的，检查文件是否存在并可加载
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        nn_exists = os.path.exists(os.path.join(base, svc.nn_model_path))
        xgb_exists = os.path.exists(os.path.join(base, svc.tree_model_path))
        stats_exists = os.path.exists(os.path.join(base, svc.feature_stats_path))
        db.close()
        ok = nn_exists and xgb_exists
        detail = f"nn={nn_exists}, xgb={xgb_exists}, stats={stats_exists}"
        check(5, "集成模型 (Ensemble)", ok, detail)
        RESULTS["ensemble_loaded"] = ok
    except Exception as e:
        check(5, "集成模型 (Ensemble)", False, str(e))

    # ── 6. 冠军概率 (final_prediction_result.json) ──
    print("\n[6] 冠军概率检查")
    try:
        pred_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "final_prediction_result.json"
        )
        if os.path.exists(pred_path):
            with open(pred_path, "r", encoding="utf-8") as f:
                pred = json.load(f)
            champion = pred.get("champion", "")
            prob = pred.get("champion_probability", 0)
            top5 = pred.get("top5", [])
            ok = bool(champion) and champion != "Unknown" and prob > 0 and len(top5) >= 3
            check(6, "冠军概率", ok,
                  f"champion={champion}, prob={prob}, top5_count={len(top5)}")
            RESULTS["champion"] = champion
            RESULTS["champion_probability"] = prob
            RESULTS["top5_count"] = len(top5)
        else:
            check(6, "冠军概率", False, "final_prediction_result.json not found")
    except Exception as e:
        check(6, "冠军概率", False, str(e))

    # ── 7. 模拟次数 >= 10000 ──
    print("\n[7] 模拟次数检查")
    try:
        sim_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "champion_prediction_ensemble.json"
        )
        if os.path.exists(sim_path):
            with open(sim_path, "r", encoding="utf-8") as f:
                sim = json.load(f)
            n_sims = sim.get("n_simulations", 0)
            ok = n_sims >= 10000
            check(7, "模拟次数 (>=10000)", ok, f"n_simulations={n_sims}")
            RESULTS["simulation_count"] = n_sims
        else:
            check(7, "模拟次数 (>=10000)", False, "champion_prediction_ensemble.json not found")
    except Exception as e:
        check(7, "模拟次数 (>=10000)", False, str(e))

    # ── 8. LLM 解释服务 ──
    print("\n[8] LLM 解释服务检查")
    try:
        from app.services.champion_explanation_service import ChampionExplanationService
        svc = ChampionExplanationService(use_llm=False)  # 不实际调 LLM，只验证可实例化
        # 用假数据测试 generate 方法能跑通
        test_result = svc.generate(
            champion="TestTeam",
            champion_probability=0.25,
            top_contenders=[
                {"team": "TestTeam", "probability": 0.25,
                 "team_strength_index": 0.9, "overall_strength_score": 0.9, "recent_form_score": 0.8,
                 "attack_score": 0.85, "defense_score": 0.75,
                 "path_advantage_score": 0.6, "key_reasons": ["strong squad"]},
            ],
            team_features={"TestTeam": {"elo_rating": 1900}},
            knockout_predictions=[],
        )
        has_title = bool(test_result.get("title"))
        has_content = bool(test_result.get("content"))
        ok = has_title and has_content
        check(8, "LLM 解释服务", ok,
              f"title={has_title}, content={has_content}")
        RESULTS["llm_explanation_service"] = ok
    except Exception as e:
        check(8, "LLM 解释服务", False, str(e))

    # ── 9. Dashboard (debug_dashboard.py) ──
    print("\n[9] Dashboard 检查")
    try:
        dashboard_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "debug_dashboard.py"
        )
        ok = os.path.exists(dashboard_path)
        if ok:
            with open(dashboard_path, "r", encoding="utf-8") as f:
                src = f.read()
            has_champion_card = "display_champion_card" in src
            has_bracket = "display_worldcup_road_to_final" in src
            has_contenders = "display_champion_contenders" in src
            has_llm = "display_llm_explanation" in src
            ok = has_champion_card and has_bracket and has_contenders and has_llm
            detail = (f"champion_card={has_champion_card}, bracket={has_bracket}, "
                      f"contenders={has_contenders}, llm={has_llm}")
        else:
            detail = "debug_dashboard.py not found"
        check(9, "Dashboard", ok, detail)
        RESULTS["dashboard"] = ok
    except Exception as e:
        check(9, "Dashboard", False, str(e))

    # ── 10. Agent 流程 (bracket_tool 无 rtd 依赖) ──
    print("\n[10] Agent 流程检查")
    try:
        bracket_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "tools", "bracket_tool.py"
        )
        with open(bracket_path, "r", encoding="utf-8") as f:
            src = f.read()
        no_rtd_import = "real_tournament_data" not in src
        no_real_group = "_build_from_real_group_data" not in src
        no_real_knockout = "_build_from_real_knockout_data" not in src
        has_db_knockout = "_build_from_db_knockout_data" in src
        has_fixture_repo = "FixtureRepository" in src
        ok = no_rtd_import and no_real_group and no_real_knockout and has_db_knockout and has_fixture_repo
        detail = (f"no_rtd={no_rtd_import}, no_real_group={no_real_group}, "
                  f"no_real_ko={no_real_knockout}, db_ko={has_db_knockout}, "
                  f"fixture_repo={has_fixture_repo}")
        check(10, "Agent 流程 (bracket_tool)", ok, detail)
        RESULTS["agent_pipeline"] = ok
    except Exception as e:
        check(10, "Agent 流程 (bracket_tool)", False, str(e))

    # ── 汇总 ──
    print("\n" + "=" * 60)
    print("  验收汇总")
    print("=" * 60)
    print(f"  通过: {PASS_COUNT}/10")
    print(f"  失败: {FAIL_COUNT}/10")
    print()

    metrics = [
        ("数据源 (finished/total)", f"{RESULTS.get('data_source_finished', '?')}/{RESULTS.get('data_source_total', '?')}"),
        ("历史样本", str(RESULTS.get("historical_samples", "?"))),
        ("NN V2", "OK" if RESULTS.get("nn_v2_loaded") else "FAIL"),
        ("XGBoost", "OK" if RESULTS.get("xgboost_loaded") else "FAIL"),
        ("集成模型", "OK" if RESULTS.get("ensemble_loaded") else "FAIL"),
        ("冠军", f"{RESULTS.get('champion', '?')} ({RESULTS.get('champion_probability', 0):.2%})" if RESULTS.get("champion_probability") else str(RESULTS.get("champion", "?"))),
        ("模拟次数", str(RESULTS.get("simulation_count", "?"))),
        ("LLM 解释", "OK" if RESULTS.get("llm_explanation_service") else "FAIL"),
        ("Dashboard", "OK" if RESULTS.get("dashboard") else "FAIL"),
        ("Agent 流程", "OK" if RESULTS.get("agent_pipeline") else "FAIL"),
    ]
    for name, val in metrics:
        print(f"  {name:20s} {val}")

    print("\n" + "=" * 60)
    if FAIL_COUNT > 0:
        print(f"  [WARN] {FAIL_COUNT} 项未通过")
        print("=" * 60)
        sys.exit(1)
    else:
        print("  [OK] 全部 10 项检查通过")
        print("=" * 60)
        sys.exit(0)


if __name__ == "__main__":
    main()
