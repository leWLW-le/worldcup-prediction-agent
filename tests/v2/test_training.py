import json

import numpy as np
import pytest

from app.features.prematch import training_rows
from app.models.registry import ModelRegistry
from app.pipelines.training import train_bundle


def test_training_pipeline_and_unverified_artifact_guard(snapshot, tmp_path):
    # This is a synthetic smoke test, not evidence of predictive quality.
    games = []
    for i in range(4):
        from datetime import timedelta

        for g in snapshot.history:
            games.append(
                g.model_copy(
                    update={
                        "date": g.date + timedelta(days=100 * i),
                        "match_id": f"{i}-{g.match_id}",
                    }
                )
            )
    artifact = tmp_path / "model"
    report = train_bundle(games, artifact, "synthetic", epochs=2)
    assert report["provenance"] == "synthetic"
    assert report["selected_test_metrics"]["log_loss"] > 0
    manifest = json.loads((artifact / "manifest.json").read_text())
    assert sum(manifest["weights"].values()) == pytest.approx(1)
    import joblib

    estimators = joblib.load(artifact / "estimators.joblib")
    cutoff = report["split_dates"][0]
    raw = [
        np.append(v, float(g.neutral))
        for g, v, _ in training_rows(games)
        if str(g.date.date()) < cutoff
    ]
    np.testing.assert_allclose(estimators["scaler"].mean_, np.mean(raw, axis=0))
    with pytest.raises(ValueError, match="synthetic"):
        ModelRegistry(artifact)
    # Temporary test-only provenance override exercises the loader; no artifact is published.
    manifest["provenance"] = "verified"
    manifest_path = artifact / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    registry = ModelRegistry(artifact)
    from datetime import datetime, timedelta

    from app.features.prematch import PrematchState
    cutoff_time = datetime.fromisoformat(manifest["trained_through"])
    with pytest.raises(ValueError, match="unavailable"):
        registry.predict(PrematchState.before(games, cutoff_time), "A", "B", cutoff_time)
    later = max(g.date for g in games) + timedelta(days=1)
    result = registry.predict(PrematchState.before(games, later), "A", "B", later)
    assert sum(result.probabilities) == pytest.approx(1)
    with (artifact / "mlp.pt").open("ab") as file:
        file.write(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        ModelRegistry(artifact)


def test_walk_forward_test_dates_do_not_overlap():
    from app.pipelines.backtest import fold_boundaries
    from scripts.demo_v2 import demo_snapshot
    boundaries = list(fold_boundaries(demo_snapshot().history))
    for previous, current in zip(boundaries, boundaries[1:]):
        assert previous[3] <= current[2]
        assert current[0] < current[1] < current[2]
