"""
回测模块 — 用历史比赛数据评估预测准确率

使用 ELO + 泊松分布概率引擎对历史比赛进行回测，
计算多项评估指标：方向准确率、Brier 分数、对数损失、比分准确率等。
"""

import sys
import math
import csv
import json
from pathlib import Path
from collections import defaultdict

# 确保项目根目录在 path 中
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.services.probability_engine import ProbabilityEngine


# ==================== 数据加载 ====================

def load_team_ratings(path: str) -> dict[str, dict]:
    """加载球队 ELO 评分"""
    ratings = {}
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["team"].strip()
            ratings[name] = {
                "elo_rating": float(row["elo_rating"]),
                "fifa_rank": int(row["fifa_rank"]),
                "squad_strength": float(row["squad_strength"]),
            }
    return ratings


def load_historical_matches(path: str) -> list[dict]:
    """加载历史比赛数据"""
    matches = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            matches.append({
                "date": row["date"],
                "home_team": row["home_team"].strip(),
                "away_team": row["away_team"].strip(),
                "home_score": int(row["home_score"]),
                "away_score": int(row["away_score"]),
                "tournament": row["tournament"],
                "neutral": row["neutral"].strip().upper() == "TRUE",
            })
    return matches


# ==================== 预测与评估 ====================

def predict_match(engine: ProbabilityEngine, home_elo: float, away_elo: float) -> dict:
    """用概率引擎预测单场比赛，返回概率分布和最可能比分"""
    outcome = engine.calculate_match_outcome_probabilities(home_elo, away_elo)
    top_scores = engine.predict_score_distribution(home_elo, away_elo)
    best = top_scores[0]
    return {
        "win_a": outcome["win_a"],
        "draw": outcome["draw"],
        "win_b": outcome["win_b"],
        "predicted_home_score": best[0],
        "predicted_away_score": best[1],
        "top3_scores": [(s[0], s[1], s[2]) for s in top_scores],
    }


def actual_result(home_score: int, away_score: int) -> str:
    """根据实际比分判定结果"""
    if home_score > away_score:
        return "home_win"
    elif home_score < away_score:
        return "away_win"
    else:
        return "draw"


def brier_score(predicted_prob: float, actual_outcome: float) -> float:
    """单场 Brier 分数 = (predicted - actual)^2"""
    return (predicted_prob - actual_outcome) ** 2


def log_loss(predicted_prob: float, actual_outcome: float, eps: float = 1e-7) -> float:
    """单场对数损失"""
    p = max(eps, min(1 - eps, predicted_prob))
    return -(actual_outcome * math.log(p) + (1 - actual_outcome) * math.log(1 - p))


def run_backtest(matches: list[dict], ratings: dict[str, dict], verbose: bool = True) -> dict:
    """
    执行回测

    对每场历史比赛：
    1. 查找两队 ELO 评分（找不到则用默认 1500）
    2. 用概率引擎预测胜平负概率和最可能比分
    3. 与实际结果对比

    返回评估指标字典
    """
    engine = ProbabilityEngine()

    # 统计变量
    total = len(matches)
    correct_direction = 0       # 胜平负方向预测正确
    correct_score = 0           # 精确比分预测正确
    correct_score_top3 = 0      # 比分在 Top-3 预测中
    correct_winner_only = 0     # 仅胜负方向（排除平局）

    brier_scores = []           # 每场三分类 Brier 分数
    log_losses = []             # 每场三分类对数损失

    # 按赛事分组统计
    tournament_stats = defaultdict(lambda: {
        "total": 0, "correct_dir": 0, "correct_score": 0, "brier": []
    })

    # 按置信度区间统计（校准曲线）
    confidence_bins = defaultdict(lambda: {"count": 0, "correct": 0})

    results_detail = []

    for match in matches:
        home = match["home_team"]
        away = match["away_team"]
        home_score = match["home_score"]
        away_score = match["away_score"]
        tournament = match["tournament"]

        # 获取 ELO（缺失则用默认值）
        home_elo = ratings.get(home, {}).get("elo_rating", 1500)
        away_elo = ratings.get(away, {}).get("elo_rating", 1500)

        # 预测
        pred = predict_match(engine, home_elo, away_elo)

        # 实际结果
        actual = actual_result(home_score, away_score)

        # --- 方向准确率 ---
        # 预测方向：概率最高的结果
        pred_probs = {
            "home_win": pred["win_a"],
            "draw": pred["draw"],
            "away_win": pred["win_b"],
        }
        predicted_direction = max(pred_probs, key=pred_probs.get)
        is_correct_dir = (predicted_direction == actual)
        if is_correct_dir:
            correct_direction += 1

        # 仅胜负（排除平局场次）
        if actual != "draw":
            pred_winner = "home_win" if pred["win_a"] >= pred["win_b"] else "away_win"
            if pred_winner == actual:
                correct_winner_only += 1

        # --- 比分准确率 ---
        pred_hs = pred["predicted_home_score"]
        pred_as = pred["predicted_away_score"]
        if pred_hs == home_score and pred_as == away_score:
            correct_score += 1

        # Top-3 比分覆盖
        top3 = [(s[0], s[1]) for s in pred["top3_scores"]]
        if (home_score, away_score) in top3:
            correct_score_top3 += 1

        # --- Brier 分数（三分类 one-hot） ---
        actual_onehot = {
            "home_win": 1.0 if actual == "home_win" else 0.0,
            "draw": 1.0 if actual == "draw" else 0.0,
            "away_win": 1.0 if actual == "away_win" else 0.0,
        }
        match_brier = sum(
            brier_score(pred_probs[k], actual_onehot[k])
            for k in ["home_win", "draw", "away_win"]
        )
        brier_scores.append(match_brier)

        # --- 对数损失 ---
        match_ll = sum(
            log_loss(pred_probs[k], actual_onehot[k])
            for k in ["home_win", "draw", "away_win"]
        )
        log_losses.append(match_ll)

        # --- 置信度校准 ---
        max_prob = pred_probs[predicted_direction]
        bin_label = f"{int(max_prob * 10) * 10}%-{int(max_prob * 10) * 10 + 10}%"
        confidence_bins[bin_label]["count"] += 1
        if is_correct_dir:
            confidence_bins[bin_label]["correct"] += 1

        # --- 赛事分组 ---
        ts = tournament_stats[tournament]
        ts["total"] += 1
        if is_correct_dir:
            ts["correct_dir"] += 1
        if pred_hs == home_score and pred_as == away_score:
            ts["correct_score"] += 1
        ts["brier"].append(match_brier)

        # 记录明细
        results_detail.append({
            "date": match["date"],
            "home_team": home,
            "away_team": away,
            "actual_score": f"{home_score}-{away_score}",
            "predicted_score": f"{pred_hs}-{pred_as}",
            "actual_result": actual,
            "predicted_direction": predicted_direction,
            "correct": is_correct_dir,
            "home_win_prob": round(pred["win_a"], 4),
            "draw_prob": round(pred["draw"], 4),
            "away_win_prob": round(pred["win_b"], 4),
            "confidence": round(max_prob, 4),
        })

    # ==================== 汇总指标 ====================
    avg_brier = sum(brier_scores) / len(brier_scores) if brier_scores else 0
    avg_log_loss = sum(log_losses) / len(log_losses) if log_losses else 0

    # 方向准确率细分
    home_win_matches = [m for m in matches if actual_result(m["home_score"], m["away_score"]) == "home_win"]
    draw_matches = [m for m in matches if actual_result(m["home_score"], m["away_score"]) == "draw"]
    away_win_matches = [m for m in matches if actual_result(m["home_score"], m["away_score"]) == "away_win"]

    # 计算各结果类型的预测准确率
    def _calc_type_accuracy(type_name, match_list):
        if not match_list:
            return 0, 0
        correct = sum(
            1 for m in match_list
            if actual_result(m["home_score"], m["away_score"]) == type_name
            and max(
                predict_match(engine,
                              ratings.get(m["home_team"], {}).get("elo_rating", 1500),
                              ratings.get(m["away_team"], {}).get("elo_rating", 1500))["win_a" if type_name == "home_win" else "draw" if type_name == "draw" else "win_b"],
                # We need to re-predict; let's do it properly below
            )
            for _ in [0]  # placeholder
        )
        # Actually let me redo this properly
        return 0, len(match_list)

    # 重新计算各类型准确率
    type_correct = {"home_win": 0, "draw": 0, "away_win": 0}
    type_total = {"home_win": len(home_win_matches), "draw": len(draw_matches), "away_win": len(away_win_matches)}

    for match in matches:
        actual = actual_result(match["home_score"], match["away_score"])
        home_elo = ratings.get(match["home_team"], {}).get("elo_rating", 1500)
        away_elo = ratings.get(match["away_team"], {}).get("elo_rating", 1500)
        pred = predict_match(engine, home_elo, away_elo)
        pred_probs = {"home_win": pred["win_a"], "draw": pred["draw"], "away_win": pred["win_b"]}
        predicted_direction = max(pred_probs, key=pred_probs.get)
        if predicted_direction == actual:
            type_correct[actual] += 1

    home_win_acc = type_correct["home_win"] / type_total["home_win"] if type_total["home_win"] else 0
    draw_acc = type_correct["draw"] / type_total["draw"] if type_total["draw"] else 0
    away_win_acc = type_correct["away_win"] / type_total["away_win"] if type_total["away_win"] else 0

    metrics = {
        "total_matches": total,
        "direction_accuracy": round(correct_direction / total, 4) if total else 0,
        "winner_only_accuracy": round(correct_winner_only / (total - len(draw_matches)), 4) if (total - len(draw_matches)) else 0,
        "exact_score_accuracy": round(correct_score / total, 4) if total else 0,
        "top3_score_coverage": round(correct_score_top3 / total, 4) if total else 0,
        "brier_score": round(avg_brier, 4),
        "log_loss": round(avg_log_loss, 4),
        "breakdown": {
            "home_win": {"accuracy": round(home_win_acc, 4), "count": type_total["home_win"]},
            "draw": {"accuracy": round(draw_acc, 4), "count": type_total["draw"]},
            "away_win": {"accuracy": round(away_win_acc, 4), "count": type_total["away_win"]},
        },
        "tournament_breakdown": {
            t: {
                "total": s["total"],
                "direction_accuracy": round(s["correct_dir"] / s["total"], 4) if s["total"] else 0,
                "exact_score_accuracy": round(s["correct_score"] / s["total"], 4) if s["total"] else 0,
                "brier_score": round(sum(s["brier"]) / len(s["brier"]), 4) if s["brier"] else 0,
            }
            for t, s in tournament_stats.items()
        },
        "confidence_calibration": {
            k: {
                "count": v["count"],
                "accuracy": round(v["correct"] / v["count"], 4) if v["count"] else 0,
            }
            for k, v in sorted(confidence_bins.items())
        },
        "detail": results_detail,
    }

    return metrics


# ==================== 输出报告 ====================

def print_report(metrics: dict):
    """打印回测报告"""
    print("=" * 70)
    print("  2026 世界杯预测系统 · 回测报告")
    print("  基于 ELO + 泊松分布概率引擎")
    print("=" * 70)

    print(f"\n{'─' * 70}")
    print(f"  总比赛场次: {metrics['total_matches']}")
    print(f"{'─' * 70}")

    print(f"\n  【核心指标】")
    print(f"  {'胜平负方向准确率':<20s} {metrics['direction_accuracy']:.1%}  "
          f"({metrics['direction_accuracy'] * metrics['total_matches']:.0f}/{metrics['total_matches']})")
    print(f"  {'仅胜负准确率(排除平局)':<20s} {metrics['winner_only_accuracy']:.1%}")
    print(f"  {'精确比分准确率':<20s} {metrics['exact_score_accuracy']:.1%}")
    print(f"  {'Top-3 比分覆盖率':<20s} {metrics['top3_score_coverage']:.1%}")
    print(f"  {'Brier 分数':<20s} {metrics['brier_score']:.4f}  (越低越好, 频率基线≈0.46)")
    print(f"  {'对数损失 (Log Loss)':<20s} {metrics['log_loss']:.4f}  (越低越好, 随机基线≈1.10)")

    print(f"\n  【按结果类型细分】")
    for result_type, data in metrics["breakdown"].items():
        cn = {"home_win": "主胜", "draw": "平局", "away_win": "客胜"}[result_type]
        print(f"  {cn:<8s} 准确率: {data['accuracy']:.1%}  ({data['count']} 场)")

    print(f"\n  【按赛事分组】")
    for tournament, data in sorted(metrics["tournament_breakdown"].items()):
        print(f"  {tournament:<30s} 方向: {data['direction_accuracy']:.1%}  "
              f"比分: {data['exact_score_accuracy']:.1%}  "
              f"Brier: {data['brier_score']:.4f}  ({data['total']}场)")

    print(f"\n  【置信度校准】")
    print(f"  {'预测置信度区间':<18s} {'样本数':>8s}  {'实际准确率':>10s}")
    for bin_label, data in metrics["confidence_calibration"].items():
        print(f"  {bin_label:<18s} {data['count']:>8d}  {data['accuracy']:>9.1%}")

    print(f"\n  【模型偏向分析】")
    home_acc = metrics["breakdown"]["home_win"]["accuracy"]
    draw_acc = metrics["breakdown"]["draw"]["accuracy"]
    away_acc = metrics["breakdown"]["away_win"]["accuracy"]
    if home_acc > 0.9 and draw_acc < 0.1:
        print(f"  ⚠ 模型严重偏向预测主胜（主胜准确率 {home_acc:.1%}，平局 {draw_acc:.1%}，客胜 {away_acc:.1%}）")
        print(f"  建议：检查 ELO 参数或增加平局/客胜的预测权重")

    print(f"\n{'─' * 70}")
    print(f"  【预测明细（最近 20 场）】")
    print(f"{'─' * 70}")
    print(f"  {'日期':<12s} {'主队':<14s} {'客队':<14s} {'预测':<8s} {'实际':<8s} {'结果':<6s}")
    for r in metrics["detail"][-20:]:
        mark = "✓" if r["correct"] else "✗"
        print(f"  {r['date']:<12s} {r['home_team']:<14s} {r['away_team']:<14s} "
              f"{r['predicted_score']:<8s} {r['actual_score']:<8s} {mark}")

    print(f"\n{'=' * 70}")
    print(f"  回测完成")
    print(f"{'=' * 70}")


# ==================== 主程序 ====================

if __name__ == "__main__":
    data_dir = project_root / "data"
    matches_path = data_dir / "historical_international_matches.csv"
    ratings_path = data_dir / "team_ratings.csv"

    if not matches_path.exists():
        print(f"错误: 找不到历史比赛数据 {matches_path}")
        sys.exit(1)
    if not ratings_path.exists():
        print(f"错误: 找不到球队评分数据 {ratings_path}")
        sys.exit(1)

    matches = load_historical_matches(str(matches_path))
    ratings = load_team_ratings(str(ratings_path))

    print(f"加载了 {len(matches)} 场历史比赛, {len(ratings)} 支球队评分")
    print()

    metrics = run_backtest(matches, ratings)

    print_report(metrics)

    # 保存结果到 JSON
    output_path = project_root / "backtest_result.json"
    # 保存时去掉 detail 中的冗余数据以控制文件大小
    save_metrics = {k: v for k, v in metrics.items() if k != "detail"}
    save_metrics["detail_sample"] = metrics["detail"][:30]  # 只保存前 30 条明细
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(save_metrics, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到 {output_path}")
