"""Expanding-window evaluation with disjoint test dates and no future features."""

import json
from pathlib import Path

from app.pipelines.training import train_bundle


def fold_boundaries(history, folds=3):
    dates = sorted({g.date.date() for g in history})
    if not 2 <= folds <= 10:
        raise ValueError("Use 2 to 10 folds")
    width = len(dates) // (folds + 7)
    if width < 10:
        raise ValueError("More dated history is required for walk-forward evaluation")
    for i in range(folds):
        test_start = (7 + i) * width
        test_end = (8 + i) * width
        yield (
            dates[test_start - 2 * width],
            dates[test_start - width],
            dates[test_start],
            dates[test_end] if test_end < len(dates) else None,
        )


def walk_forward(history, destination, provenance, folds=3, epochs=40):
    boundaries = list(fold_boundaries(history, folds))
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=False)
    reports = []
    for i, (val_start, cal_start, test_start, end) in enumerate(boundaries):
        prefix = [g for g in history if end is None or g.date.date() < end]
        report = train_bundle(
            prefix,
            root / f"fold-{i + 1}",
            provenance,
            epochs=epochs,
            split_dates=[val_start, cal_start, test_start],
        )
        reports.append(report)
    result = {
        "provenance": provenance,
        "folds": reports,
        "mean_log_loss": sum(r["selected_test_metrics"]["log_loss"] for r in reports) / folds,
        "warning": "Synthetic data measures execution only, never predictive quality."
        if provenance != "verified"
        else "Historical revisions/publication delays are not reconstructed; not a live trading evaluation.",
    }
    (root / "walk-forward.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
