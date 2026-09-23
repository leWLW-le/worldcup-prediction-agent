"""Deterministic probabilities; sampling consumes an explicit Generator."""

from dataclasses import dataclass
from math import exp

import numpy as np

from app.domain.contracts import validate_distribution


@dataclass(frozen=True)
class MatchDistribution:
    probabilities: tuple[float, float, float]
    scores: np.ndarray
    draw_advancement: float = 0.5

    def __post_init__(self):
        validate_distribution(self.probabilities)
        if not 0 <= self.draw_advancement <= 1:
            raise ValueError("Invalid draw advancement probability")
        if self.scores.ndim != 2 or np.any(~np.isfinite(self.scores)) or np.any(self.scores < 0):
            raise ValueError("Invalid score matrix")
        if abs(self.scores.sum() - 1) > 1e-8:
            raise ValueError("Score matrix must sum to one")
        margins = (
            np.tril(self.scores, -1).sum(),
            np.trace(self.scores),
            np.triu(self.scores, 1).sum(),
        )
        if not np.allclose(margins, self.probabilities, atol=1e-8):
            raise ValueError("Score margins disagree with outcome probabilities")

    @property
    def home_advancement(self):
        return self.probabilities[0] + self.probabilities[1] * self.draw_advancement

    def sample(self, rng):
        index = rng.choice(self.scores.size, p=self.scores.ravel())
        home, away = np.unravel_index(index, self.scores.shape)
        return int(home), int(away)

    def representative_score(self, outcome):
        rows, cols = np.indices(self.scores.shape)
        mask = (rows > cols, rows == cols, rows < cols)[outcome]
        flat = np.argmax(np.where(mask, self.scores, -1))
        return tuple(int(x) for x in np.unravel_index(flat, self.scores.shape))


def poisson_matrix(home_lambda, away_lambda, tolerance=1e-12):
    if not all(np.isfinite(x) and 0 < x <= 15 for x in (home_lambda, away_lambda)):
        raise ValueError("Unsupported goal intensity")

    def pmf(lam):
        values = [exp(-lam)]
        while 1 - sum(values) > tolerance:
            values.append(values[-1] * lam / len(values))
        return np.asarray(values)

    h, a = pmf(home_lambda), pmf(away_lambda)
    size = max(len(h), len(a))
    h, a = np.pad(h, (0, size - len(h))), np.pad(a, (0, size - len(a)))
    matrix = np.outer(h, a)
    return matrix / matrix.sum()


def from_matrix(matrix, probabilities=None):
    masks = (
        np.tril(np.ones_like(matrix, dtype=bool), -1),
        np.eye(len(matrix), dtype=bool),
        np.triu(np.ones_like(matrix, dtype=bool), 1),
    )
    margins = np.asarray([matrix[m].sum() for m in masks])
    target = margins if probabilities is None else np.asarray(probabilities, dtype=float)
    validate_distribution(target)
    result = np.zeros_like(matrix)
    for mask, p, mass in zip(masks, target, margins):
        if mass <= 0:
            raise ValueError("Missing score support for outcome")
        result[mask] = matrix[mask] * p / mass
    return MatchDistribution(tuple(float(p) for p in target), result)


def elo_probabilities(home_elo, away_elo, neutral=True):
    # Davidson-style draw-aware rating baseline; not a claimed fitted model.
    strength = 10 ** ((home_elo - away_elo + (0 if neutral else 80)) / 800)
    denominator = strength + 1 / strength + 0.75
    return np.array([strength, 0.75, 1 / strength]) / denominator


def baseline_distribution(state, home, away, as_of, neutral=True):
    if not state.games[home] or not state.games[away]:
        raise ValueError(f"Historical features unavailable: {home} / {away}")

    # Explicit empirical Poisson baseline; modest prior regularizes sparse histories.
    def rate(team, scored):
        games = state.games[team][-20:]
        idx = 1 if scored else 2
        return (sum(g[idx] for g in games) + 2 * 1.25) / (len(games) + 2)

    lh = np.clip((rate(home, True) + rate(away, False)) / 2 * (1 if neutral else 1.08), 0.1, 10)
    la = np.clip((rate(away, True) + rate(home, False)) / 2, 0.1, 10)
    matrix = poisson_matrix(float(lh), float(la))
    # Baseline deliberately uses Poisson alone until validation selects ensemble weights.
    return from_matrix(matrix)
