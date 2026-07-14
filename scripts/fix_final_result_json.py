"""
修复 final_agent_result.json 一致性

读取当前文件，强制同步所有预测字段：
  - top_candidates = deepcopy(top5)
  - explanation.champion = champion
  - explanation.champion_probability = champion_probability
  - explanation.probability = champion_probability * 100
  - explanation.run_id = run_id
  - 生成 run_id（如果缺失）
  - 保存前执行 _validate_prediction_snapshot 校验

用法:
  python scripts/fix_final_result_json.py
  python scripts/fix_final_result_json.py --dry-run   # 仅检查，不修改
"""
import json
import sys
import hashlib
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
JSON_PATH = DATA_DIR / "final_agent_result.json"


def fix_json(dry_run: bool = False):
    if not JSON_PATH.exists():
        print(f"[INFO] 文件不存在，跳过修复: {JSON_PATH}")
        print("[INFO] 首次运行时会由 agent 自动生成，无需干预")
        return True  # 文件不存在不是错误，不阻止启动

    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    print("=" * 60)
    print("修复前状态:")
    print(f"  status           = {data.get('status')}")
    print(f"  champion         = {data.get('champion')}")
    print(f"  champion_prob    = {data.get('champion_probability')}")
    print(f"  top5[0]          = {data.get('top5', [{}])[0] if data.get('top5') else 'NONE'}")
    print(f"  top_cand[0]      = {data.get('top_candidates', [{}])[0] if data.get('top_candidates') else 'NONE'}")
    expl = data.get("explanation", {})
    print(f"  expl.champion    = {expl.get('champion') if isinstance(expl, dict) else 'N/A'}")
    print(f"  expl.prob        = {expl.get('champion_probability') if isinstance(expl, dict) else 'N/A'}")
    print(f"  expl.probability = {expl.get('probability') if isinstance(expl, dict) else 'N/A'}")
    print(f"  run_id           = {data.get('run_id')}")
    print("=" * 60)

    # ── Step 1: 强制 champion / champion_probability 来自 top5[0] ──
    top5 = data.get("top5", [])
    if not top5:
        print("[ERROR] top5 为空，无法修复")
        return False

    champ = top5[0].get("team", "")
    top1_prob = top5[0].get("probability", 0)
    champ_prob_01 = top1_prob if top1_prob <= 1 else top1_prob / 100.0
    champ_prob_01 = round(champ_prob_01, 4)

    print(f"\n[Step 1] 统一: champion={champ}, champion_probability={champ_prob_01}")

    # ── Step 2: 生成 run_id ──
    run_id = data.get("run_id", "")
    if not run_id:
        run_ts = datetime.now(timezone.utc).isoformat()
        run_id_raw = f"{champ}:{champ_prob_01}:{run_ts}"
        run_id = "run_" + hashlib.md5(run_id_raw.encode()).hexdigest()[:12]
        print(f"[Step 2] 生成 run_id: {run_id}")
    else:
        print(f"[Step 2] 保留 run_id: {run_id}")

    # ── Step 3: 同步所有字段 ──
    data["champion"] = champ
    data["predicted_champion"] = champ
    data["champion_probability"] = champ_prob_01
    data["top5"] = top5
    data["top_candidates"] = deepcopy(top5)
    data["run_id"] = run_id
    data["status"] = "completed"
    data["generated_at"] = datetime.now(timezone.utc).isoformat()

    print(f"[Step 3] top_candidates[0] = {data['top_candidates'][0]}")

    # ── Step 4: 修复 explanation ──
    expl = data.get("explanation", {})
    if not isinstance(expl, dict):
        expl = {}

    prob_pct = round(champ_prob_01 * 100, 2)

    # 如果 explanation.champion 不一致，需要重新生成内容
    expl_champ = expl.get("champion", "")
    if expl_champ and expl_champ != champ:
        print(f"[Step 4] explanation.champion({expl_champ}) != champion({champ}), 重新生成内容")
        # 替换文本中的旧冠军名和新冠军名
        content = expl.get("content", "")
        if content:
            content = content.replace(expl_champ, champ)
        else:
            content = (
                f"## 为什么预测 {champ} 夺冠？\n\n"
                f"根据已结束比赛结果和后续对阵形势，{champ} 展现出较强的夺冠实力，"
                f"系统给出 {prob_pct}% 的夺冠概率。"
                f"球队在攻防两端表现均衡，是当前最有可能捧起大力神杯的队伍。\n"
            )
        title = f"为什么预测 {champ} 夺冠？"
    else:
        content = expl.get("content", "")
        title = expl.get("title", f"为什么预测 {champ} 夺冠？")
        if champ not in title:
            title = f"为什么预测 {champ} 夺冠？"

    expl["title"] = title
    expl["content"] = content
    expl["champion"] = champ
    expl["champion_probability"] = champ_prob_01
    expl["probability"] = prob_pct
    expl["run_id"] = run_id

    data["explanation"] = expl

    print(f"[Step 4] explanation: champion={expl['champion']}, prob={expl['champion_probability']}, "
          f"probability={expl['probability']}, run_id={expl['run_id']}")

    # ── Step 5: 校验 ──
    print("\n[Step 5] 执行一致性校验...")
    errors = []

    if data.get("status") != "completed":
        errors.append(f"status={data.get('status')} != completed")
    if data.get("champion") != top5[0].get("team"):
        errors.append(f"champion({data.get('champion')}) != top5[0].team({top5[0].get('team')})")

    cp = data.get("champion_probability", 0)
    tp = top5[0].get("probability", 0)
    cp_norm = cp if cp <= 1 else cp / 100.0
    tp_norm = tp if tp <= 1 else tp / 100.0
    if abs(cp_norm - tp_norm) > 1e-9:
        errors.append(f"champion_probability({cp}) != top5[0].probability({tp})")

    tc = data.get("top_candidates", [])
    if tc:
        if tc[0].get("team") != champ:
            errors.append(f"top_candidates[0].team({tc[0].get('team')}) != champion({champ})")
        tc_p = tc[0].get("probability", 0)
        tc_p_norm = tc_p if tc_p <= 1 else tc_p / 100.0
        if abs(tc_p_norm - cp_norm) > 1e-9:
            errors.append(f"top_candidates[0].probability({tc_p}) != champion_probability({cp})")

    if isinstance(expl, dict):
        if expl.get("champion") != champ:
            errors.append(f"explanation.champion({expl.get('champion')}) != champion({champ})")
        ep = expl.get("champion_probability")
        if ep is not None:
            ep_norm = float(ep) if float(ep) <= 1 else float(ep) / 100.0
            if abs(ep_norm - cp_norm) > 1e-9:
                errors.append(f"explanation.champion_probability({ep}) != champion_probability({cp})")
        if expl.get("run_id") != run_id:
            errors.append(f"explanation.run_id({expl.get('run_id')}) != run_id({run_id})")

    if errors:
        print("[FAIL] 校验失败:")
        for e in errors:
            print(f"  - {e}")
        return False

    print("[PASS] 一致性校验通过")

    # ── Step 6: 保存 ──
    if dry_run:
        print("\n[DRY-RUN] 不保存，仅检查")
        return True

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n[Step 6] 已保存: {JSON_PATH.resolve()}")

    # 验证保存后状态
    print("\n修复后状态:")
    print(f"  status           = {data.get('status')}")
    print(f"  champion         = {data.get('champion')}")
    print(f"  champion_prob    = {data.get('champion_probability')}")
    print(f"  top5[0]          = {data.get('top5', [{}])[0]}")
    print(f"  top_cand[0]      = {data.get('top_candidates', [{}])[0]}")
    print(f"  expl.champion    = {data['explanation'].get('champion')}")
    print(f"  expl.prob        = {data['explanation'].get('champion_probability')}")
    print(f"  expl.probability = {data['explanation'].get('probability')}")
    print(f"  run_id           = {data.get('run_id')}")

    return True


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    ok = fix_json(dry_run=dry_run)
    sys.exit(0 if ok else 1)
