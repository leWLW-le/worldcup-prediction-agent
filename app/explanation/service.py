"""Explanations are derived views; numeric fields remain backend-owned."""


def explain_result(result):
    champion, p = result["champion"], result["champion_probability"]
    path = result["representative_path_champion"]
    if result.get("status") == "observed":
        return {
            "run_id": result["run_id"],
            "source": "observed",
            "champion": champion,
            "champion_probability": p,
            "text": f"{champion} 是接口记录的实际冠军；100% 表示赛果已知，不是赛前预测准确率。",
            "warnings": result["warnings"],
        }
    return {
        "run_id": result["run_id"],
        "source": "template",
        "champion": champion,
        "champion_probability": p,
        "text": f"{champion} 的模拟夺冠概率为 {p:.1%}。"
        f"本次使用 {result['simulation_count']} 次模拟，数据截止 {result['as_of']}。"
        f"代表路径冠军为 {path}；单条路径与最高概率球队可以不同。"
        "采样误差不包括模型误差。",
        "warnings": result["warnings"],
    }
