"""Chronological train/validation/calibration/test; no legacy CSV features."""

import json
from hashlib import sha256
from pathlib import Path

import joblib
import numpy as np
from scipy.optimize import minimize, minimize_scalar
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, log_loss
from sklearn.preprocessing import StandardScaler

from app.domain.contracts import HistoricalGame
from app.features.prematch import COLUMNS, SCHEMA_VERSION, PrematchState, training_rows
from app.models.distributions import baseline_distribution


def metrics(y, p):
    confidence = p.max(1)
    correct = p.argmax(1) == y
    buckets = np.minimum((confidence * 10).astype(int), 9)
    reliability = []
    for bucket in range(10):
        mask = buckets == bucket
        reliability.append({
            "lower": bucket / 10, "upper": (bucket + 1) / 10,
            "n": int(mask.sum()),
            "confidence": float(confidence[mask].mean()) if mask.any() else None,
            "accuracy": float(correct[mask].mean()) if mask.any() else None,
        })
    return {
        "log_loss": float(log_loss(y, p, labels=[0, 1, 2])),
        "brier": float(np.mean(np.sum((p - np.eye(3)[y]) ** 2, axis=1))),
        "accuracy": float(accuracy_score(y, p.argmax(1))),
        "macro_f1": float(f1_score(y, p.argmax(1), labels=[0, 1, 2], average="macro", zero_division=0)),
        "reliability": reliability,
    }


def train_bundle(history, destination, provenance, seed=42, epochs=40, split_dates=None):
    from importlib.metadata import version

    import torch
    from xgboost import XGBClassifier

    from app.models.mlp import MatchMLP

    if provenance not in ("verified", "synthetic"):
        raise ValueError("Training requires explicit verified or synthetic provenance")
    if epochs < 1 or epochs > 1000:
        raise ValueError("epochs must be between 1 and 1000")
    if len({g.match_id for g in history}) != len(history):
        raise ValueError("Duplicate historical match IDs")
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    rng = np.random.default_rng(seed)
    rows = list(training_rows(history))
    if len(rows) < 200:
        raise ValueError("At least 200 warm-history examples required")
    dates = sorted({g.date.date() for g, _, _ in rows})
    cuts = split_dates or [dates[int(len(dates) * p)] for p in (0.6, 0.75, 0.85)]
    if len(cuts) != 3 or not cuts[0] < cuts[1] < cuts[2]:
        raise ValueError("Three strictly increasing split dates required")
    indices = [
        [
            i
            for i, (g, _, _) in enumerate(rows)
            if (j == 0 or g.date.date() >= cuts[j - 1]) and (j == 3 or g.date.date() < cuts[j])
        ]
        for j in range(4)
    ]
    if any(len(ids) < 20 for ids in indices):
        raise ValueError("Each chronological split needs at least 20 examples")
    x = np.array([np.append(v, float(g.neutral)) for g, v, _ in rows])
    y = np.array([label for _, _, label in rows])
    tr, va, ca, te = indices
    if set(y[tr]) != {0, 1, 2}:
        raise ValueError("Training split must include all three outcomes")
    scaler = StandardScaler().fit(x[tr])
    xt = scaler.transform(x)
    elo_x = np.column_stack((x[:, 0] - x[:, 25], x[:, -1]))
    elo = LogisticRegression(max_iter=1000).fit(elo_x[tr], y[tr])
    xgb = XGBClassifier(
        n_estimators=100,
        max_depth=3,
        learning_rate=0.05,
        objective="multi:softprob",
        num_class=3,
        n_jobs=1,
        random_state=seed,
    )
    xgb.fit(x[tr], y[tr])
    model = MatchMLP()
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001)
    tensor = torch.tensor(xt, dtype=torch.float32)
    target = torch.tensor(y, dtype=torch.long)
    best, best_loss = None, float("inf")
    for _ in range(epochs):
        model.train()
        for start in range(0, len(tr), 128):
            # A complete fixed permutation per epoch, not independent overlapping batches.
            if start == 0:
                order = rng.permutation(tr)
            batch = order[start : start + 128]
            optimizer.zero_grad()
            loss = torch.nn.functional.cross_entropy(model(tensor[batch]), target[batch])
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.inference_mode():
            val_loss = float(torch.nn.functional.cross_entropy(model(tensor[va]), target[va]))
        if val_loss < best_loss:
            best_loss = val_loss
            best = {k: v.detach().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best)
    model.eval()
    with torch.inference_mode():
        nn_prob = torch.softmax(model(tensor), dim=1).numpy()
    # Build Poisson forecasts strictly before each match date.
    from itertools import groupby

    state, poisson_by_id = PrematchState(), {}
    for _, batch in groupby(
        sorted(history, key=lambda g: (g.date, g.match_id)), lambda g: g.date.date()
    ):
        games = list(batch)
        for game in games:
            if state.games[game.home] and state.games[game.away]:
                poisson_by_id[game.match_id] = baseline_distribution(
                    state, game.home, game.away, game.date, game.neutral
                ).probabilities
        state.update_day(games)
    names = ["elo", "poisson", "xgb", "mlp"]
    predictions = np.array(
        [
            elo.predict_proba(elo_x),
            [poisson_by_id[g.match_id] for g, _, _ in rows],
            xgb.predict_proba(x),
            nn_prob,
        ],
        dtype=np.float64,
    )
    predictions /= predictions.sum(axis=2, keepdims=True)
    result = minimize(
        lambda w: log_loss(y[va], np.einsum("m,mnc->nc", w, predictions[:, va]), labels=[0, 1, 2]),
        np.ones(4) / 4,
        bounds=[(0, 1)] * 4,
        constraints={"type": "eq", "fun": lambda w: w.sum() - 1},
        method="SLSQP",
    )
    weights = (
        result.x
        if result.success
        else np.eye(4)[
            min(range(4), key=lambda i: log_loss(y[va], predictions[i, va], labels=[0, 1, 2]))
        ]
    )
    weights = np.maximum(weights, 0)
    weights /= weights.sum()
    # Validation decides whether a single candidate is preferable to the blend.
    choices = list(np.eye(4)) + [weights]
    weights = min(
        choices,
        key=lambda w: log_loss(
            y[va], np.einsum("m,mnc->nc", w, predictions[:, va]), labels=[0, 1, 2]
        ),
    )
    mixed = np.einsum("m,mnc->nc", weights, predictions)

    def calibrate(p, temperature):
        logs = np.log(np.clip(p, 1e-12, 1)) / temperature
        probs = np.exp(logs - logs.max(1, keepdims=True))
        return probs / probs.sum(1, keepdims=True)

    fit = minimize_scalar(
        lambda t: log_loss(y[ca], calibrate(mixed[ca], t), labels=[0, 1, 2]),
        bounds=(0.5, 3),
        method="bounded",
    )
    temperature = float(fit.x)
    output = Path(destination)
    output.mkdir(parents=True, exist_ok=False)
    joblib.dump({"scaler": scaler, "elo": elo, "xgb": xgb}, output / "estimators.joblib")
    torch.save(model.state_dict(), output / "mlp.pt")
    checksums = {
        f: sha256((output / f).read_bytes()).hexdigest() for f in ("estimators.joblib", "mlp.pt")
    }
    report = {
        "samples": {
            name: len(ids)
            for name, ids in zip(("train", "validation", "calibration", "test"), indices)
        },
        "test_metrics": {name: metrics(y[te], predictions[i, te]) for i, name in enumerate(names)},
        "selected_test_metrics": metrics(y[te], calibrate(mixed[te], temperature)),
        "split_dates": [str(d) for d in cuts],
        "seed": seed,
        "provenance": provenance,
        "best_validation_loss": best_loss,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "columns": list(COLUMNS) + ["neutral"],
        "provenance": provenance,
        "weights": dict(zip(names, [float(w) for w in weights])),
        "temperature": temperature,
        "files": checksums,
        "dependencies": {
            k: version(k) for k in ("numpy", "scipy", "scikit-learn", "xgboost", "torch", "joblib")
        },
        # All selection and calibration data count toward availability.
        "trained_through": rows[ca[-1]][0].date.isoformat(),
        "model_version": "v3-"
        + sha256(json.dumps(checksums, sort_keys=True).encode()).hexdigest()[:16],
        "training_data_hash": sha256(
            json.dumps([g.model_dump(mode="json") for g in history], sort_keys=True).encode()
        ).hexdigest(),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def load_history(path):
    path = Path(path)
    if path.is_dir():
        import csv
        import gzip
        import io
        metadata = json.loads((path / "provenance.json").read_text(encoding="utf-8"))
        raw=(path/"history.csv").read_bytes() if (path/"history.csv").exists() else gzip.decompress((path/"history.csv.gz").read_bytes())
        if sha256(raw).hexdigest() != metadata["history_sha256"]:
            raise ValueError("Historical data checksum mismatch")
        with io.StringIO(raw.decode("utf-8"),newline="") as file:
            history = [HistoricalGame.model_validate(row) for row in csv.DictReader(file)]
        return history, metadata["provenance"]
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [HistoricalGame.model_validate(g) for g in data["history"]], data["provenance"]
