"""The only production prediction/scenario workflow."""

import math
import time
from datetime import datetime, timezone
from uuid import uuid4

from app.features.prematch import PrematchState
from app.tournament.bracket import BracketGraph
from app.tournament.simulator import simulate


def validate_result(result):
    probs = result["champion_distribution"]
    if not probs or any(not math.isfinite(p) or not 0 <= p <= 1 for p in probs.values()):
        raise ValueError("Invalid champion probabilities")
    if abs(sum(probs.values()) - 1) > 1e-8:
        raise ValueError("Champion distribution must sum to one")
    winner = sorted(probs, key=lambda t: (-probs[t], t))[0]
    if result["champion"] != winner or result["champion_probability"] != probs[winner]:
        raise ValueError("Champion must be probability argmax")
    expected = [
        {"team": t, "probability": probs[t]}
        for t in sorted(probs, key=lambda t: (-probs[t], t))[:5]
    ]
    if result["top5"] != expected:
        raise ValueError("Ranking does not match the underlying distribution")
    if result["simulation_count"] <= 0:
        raise ValueError("Missing actual simulation count")


class PredictionPipeline:
    def __init__(self, store, registry, timeout=120, allow_demo=False):
        self.store, self.registry = store, registry
        self.timeout, self.allow_demo = timeout, allow_demo

    def run(self, request, cancelled=lambda: False, persist=True):
        started = time.monotonic()
        data = self.store.get_input(request.snapshot_id)
        if data.provenance != "verified" and not self.allow_demo:
            raise ValueError("Unverified/synthetic inputs are disabled; import verified data")
        graph = BracketGraph(data.fixtures)
        state = PrematchState.before(data.history, data.as_of)
        forced = (
            {request.fixture_id: request.forced_winner} if hasattr(request, "fixture_id") else {}
        )

        def predict(h, a, neutral):
            return self.registry.predict(state, h, a, data.as_of, neutral)

        result = simulate(
            graph,
            predict,
            request.simulation_count,
            request.seed,
            forced,
            cancelled,
            self.timeout - (time.monotonic() - started),
        )
        result.update(
            {
                "schema_version": 3,
                "run_id": "run_" + uuid4().hex,
                "snapshot_id": data.snapshot_id,
                "season": data.season,
                "as_of": data.as_of.isoformat(),
                "model_version": self.registry.version,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "observed"
                if all(f.status == "finished" for f in data.fixtures)
                else "demo"
                if data.provenance != "verified"
                else "baseline"
                if self.registry.manifest is None
                else "completed",
                "warnings": list(data.warnings)
                + (
                    ["Untrained empirical Poisson baseline; q(draw)=0.5"]
                    if self.registry.manifest is None
                    else []
                ),
            }
        )
        if forced:
            # Same inputs/model/seed/budget, no comparison against stale global JSON.
            baseline = simulate(
                graph,
                predict,
                request.simulation_count,
                request.seed,
                {},
                cancelled,
                self.timeout - (time.monotonic() - started),
            )
            result["baseline_champion_distribution"] = baseline["champion_distribution"]
            result["probability_change"] = {
                t: p - baseline["champion_distribution"][t]
                for t, p in result["champion_distribution"].items()
            }
        if cancelled():
            raise RuntimeError("Task cancelled before persistence")
        if persist:
            self.store.save_result(result, "scenario" if forced else "prediction")
        return result

    def compare(self, run_ids):
        results = [self.store.result(r) for r in run_ids]
        if len({r["season"] for r in results}) != 1:
            raise ValueError("Cannot compare different seasons")
        base = results[0]
        return {
            "baseline_run_id": base["run_id"],
            "comparisons": [
                {
                    "run_id": r["run_id"],
                    "model_changed": r["model_version"] != base["model_version"],
                    "snapshot_changed": r["snapshot_id"] != base["snapshot_id"],
                    "as_of": r["as_of"],
                    "champion": r["champion"],
                    "delta": {
                        t: r["champion_distribution"].get(t, 0)
                        - base["champion_distribution"].get(t, 0)
                        for t in sorted(
                            set(r["champion_distribution"]) | set(base["champion_distribution"])
                        )
                    },
                }
                for r in results[1:]
            ],
        }
