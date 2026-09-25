"""One immutable model bundle per process, verified before loading."""

import json
from datetime import datetime
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

import numpy as np

from app.features.prematch import COLUMNS, SCHEMA_VERSION
from app.models.distributions import (
    baseline_distribution,
    from_matrix,
)


class ModelRegistry:
    def __init__(self, artifact_dir=None):
        self.manifest = None
        self.version = "empirical-poisson-baseline-v3"
        self.models = {}
        if artifact_dir:
            self._load(Path(artifact_dir))

    def _load(self, root):
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if manifest["schema_version"] != SCHEMA_VERSION or manifest["columns"] != list(COLUMNS) + [
            "neutral"
        ]:
            raise ValueError("Model/feature schema mismatch; retraining required")
        if manifest["provenance"] != "verified":
            raise ValueError(
                "Unverified/synthetic artifacts cannot be used for production inference"
            )
        from importlib.metadata import version

        expected = {"numpy", "scipy", "scikit-learn", "xgboost", "torch", "joblib"}
        dependencies = manifest.get("dependencies", {})
        if set(dependencies) != expected or any(version(k) != v for k, v in dependencies.items()):
            raise ValueError("Artifact dependency versions differ; use the training environment")
        if set(manifest["files"]) != {"estimators.joblib", "mlp.pt"}:
            raise ValueError("Missing artifact checksums")
        weights = manifest["weights"]
        if (
            set(weights) != {"poisson", "elo", "xgb", "mlp"}
            or any(not np.isfinite(w) or w < 0 for w in weights.values())
            or abs(sum(weights.values()) - 1) > 1e-8
        ):
            raise ValueError("Invalid ensemble weights")
        if not 0.5 <= manifest["temperature"] <= 3:
            raise ValueError("Invalid calibration temperature")
        for name, checksum in manifest["files"].items():
            path = (root / name).resolve()
            if path.parent != root.resolve() or sha256(path.read_bytes()).hexdigest() != checksum:
                raise ValueError("Artifact checksum/path mismatch")
        import joblib
        import torch

        from app.models.mlp import MatchMLP

        # Artifacts are operator-supplied trusted files, never user uploads.
        self.models = joblib.load(root / "estimators.joblib")
        self.nn = MatchMLP()
        self.nn.load_state_dict(torch.load(root / "mlp.pt", map_location="cpu", weights_only=True))
        self.nn.eval()
        self.manifest = manifest
        self.version = manifest["model_version"]

    def predict(self, state, home, away, as_of, neutral=True):
        base = baseline_distribution(state, home, away, as_of, neutral)
        if self.manifest is None:
            return base
        if as_of.date() <= datetime.fromisoformat(self.manifest["trained_through"]).date():
            raise ValueError("Artifact uses information unavailable at prediction time")
        if min(len(state.games[home]), len(state.games[away])) < 5:
            raise ValueError("Insufficient history for trained model")
        import torch

        raw = np.append(state.vector(home, away, as_of), float(neutral)).reshape(1, -1)
        scaled = self.models["scaler"].transform(raw)
        with torch.inference_mode():
            nn = torch.softmax(self.nn(torch.tensor(scaled, dtype=torch.float32)), dim=1).numpy()[0]
        rating = state.elo[home] - state.elo[away]
        elo = self.models["elo"].predict_proba([[rating, float(neutral)]])[0]
        probs = {
            "poisson": np.asarray(base.probabilities),
            "elo": elo,
            "mlp": nn,
            "xgb": self.models["xgb"].predict_proba(raw)[0],
        }
        mixed = sum(self.manifest["weights"][name] * p for name, p in probs.items())
        temperature = self.manifest["temperature"]
        mixed = np.exp(np.log(np.clip(mixed, 1e-12, 1)) / temperature)
        mixed /= mixed.sum()
        return from_matrix(base.scores, mixed)


@lru_cache(maxsize=4)
def get_registry(artifact_dir=None):
    return ModelRegistry(artifact_dir)
