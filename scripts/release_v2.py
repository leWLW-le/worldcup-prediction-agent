"""Build a reproducible, explicitly dated pre-tournament replay from real data."""

import argparse
import hashlib
import json
from pathlib import Path

from app.domain.contracts import PredictionRequest, TournamentInput
from app.models.registry import ModelRegistry
from app.pipelines.prediction import PredictionPipeline
from app.pipelines.training import load_history


def released_snapshot(root=Path(".")):
    history, provenance = load_history(root / "data/verified")
    stage = json.loads((root / "data/verified/worldcup2026.json").read_text(encoding="utf-8"))
    return TournamentInput(
        season=2026,
        as_of="2026-06-01T00:00:00Z",
        provenance=provenance,
        source="Pre-tournament replay; martj42 pinned CC0 fixtures/history; FIFA May 2026 rules",
        history=tuple(history),
        group_stage=stage,
        warnings=(
            "赛前历史回放：信息截止 2026-06-01，不是当前实时比赛。",
            "赛程来源只有日期，00:00 UTC 是日期占位，不是已核验开球时间。",
            "历史数据经过回溯修订，进球事件覆盖筛选存在样本选择偏差。",
            "加时/点球仍采用平局后各 50% 晋级基线。",
        ),
    )


def build_release(root=Path("."), count=2000):
    snapshot = released_snapshot(root)

    class Input:
        def get_input(self, snapshot_id):
            if snapshot_id != snapshot.snapshot_id:
                raise KeyError(snapshot_id)
            return snapshot

    registry = ModelRegistry(root / "models/production-v2")
    pipeline = PredictionPipeline(Input(), registry, timeout=600)
    result = pipeline.run(
        PredictionRequest(snapshot_id=snapshot.snapshot_id, simulation_count=count), persist=False
    )
    # Stable identity makes deployment seeding idempotent.
    result["run_id"] = (
        "release-"
        + hashlib.sha256(
            (result["snapshot_id"] + result["model_version"] + str(count) + ":42").encode()
        ).hexdigest()[:32]
    )
    path = root / "data/verified/release-result.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"champion": result["champion"], "top5": result["top5"], "run_id": result["run_id"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=2000)
    args = parser.parse_args()
    print(json.dumps(build_release(count=args.count), ensure_ascii=True))
