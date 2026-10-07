"""Explanations are derived views; numeric fields remain backend-owned."""


def explain_result(result):
    champion, p = result["champion"], result["champion_probability"]
    if result.get("status") == "observed":
        return {
            "run_id": result["run_id"],
            "source": "observed",
            "champion": champion,
            "champion_probability": p,
            "text": f"{champion} 是接口记录的实际冠军；100% 表示赛果已知，不是赛前预测准确率。",
            "warnings": result["warnings"],
        }
    paragraphs = [
        f"为什么看好 {champion}？在这次完整赛事模拟中，它的夺冠概率为 {p:.1%}，"
        "是模型最看好的球队。这表示它在多种可能的比赛进程中更常走到最后，并不意味着冠军已经确定。"
    ]
    stages = result.get("stage_probabilities", {})
    milestones = []
    for stage, label in (("round_of_32", "小组出线"), ("semi_finals", "进入四强"), ("final", "进入决赛")):
        value = stages.get(stage, {}).get(champion)
        if value is not None:
            milestones.append(f"{label}的概率为 {value:.1%}")
    if milestones:
        paragraphs.append("把晋级过程拆开看，模型给它" + "，".join(milestones) + "。这些数字能帮助理解它的争冠前景，但不能单独证明某种战术或某位球员带来了优势。")
    rivals = sorted(
        ((team, probability) for team, probability in result.get("champion_distribution", {}).items() if team != champion),
        key=lambda item: item[1], reverse=True,
    )
    if rivals:
        rival, rival_p = rivals[0]
        gap = (p - rival_p) * 100
        if gap >= 0:
            paragraphs.append(f"最接近的竞争者是 {rival}，夺冠概率为 {rival_p:.1%}；两队只差 {gap:.1f} 个百分点。" if gap < 5 else f"相比之下，最接近的竞争者 {rival} 的夺冠概率为 {rival_p:.1%}，落后 {gap:.1f} 个百分点。")
    paragraphs.append(
        f"因此，更合适的理解是把 {champion} 视为争冠热门，而不是认定它一定夺冠。"
        + (f"模型仍给其他球队合计 {1 - p:.1%} 的夺冠机会，比赛中的变化也可能改变预测。" if p < 1 else "这仍是模型模拟结果，并非已确认的实际赛果。")
    )
    return {
        "run_id": result["run_id"],
        "source": "template",
        "champion": champion,
        "champion_probability": p,
        "text": "\n\n".join(paragraphs),
        "warnings": result["warnings"],
    }
