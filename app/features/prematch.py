"""Point-in-time state: all matches on a date are evaluated before updates."""

from collections import defaultdict
from datetime import timedelta
from itertools import groupby

import numpy as np

from app.domain.contracts import utc

TEAM_FEATURES = (
    "elo_rating",
    "elo_change_1year",
    "elo_change_3year",
    "world_cup_experience",
    "major_tournament_points",
    "wins_5",
    "draws_5",
    "losses_5",
    "goals_for_5",
    "goals_against_5",
    "win_rate_5",
    "wins_10",
    "draws_10",
    "losses_10",
    "goals_for_10",
    "goals_against_10",
    "win_rate_10",
    "attack_score",
    "avg_goals_scored",
    "goals_proxy",
    "big_win_rate",
    "scoring_consistency",
    "defense_score",
    "avg_goals_conceded",
    "clean_sheet_rate",
)
COLUMNS = tuple(
    [f"home_{x}" for x in TEAM_FEATURES]
    + [f"away_{x}" for x in TEAM_FEATURES]
    + [f"diff_{x}" for x in TEAM_FEATURES[:17]]
)
SCHEMA_VERSION = "prematch-67-v3"


class PrematchState:
    def __init__(self):
        self.elo = defaultdict(lambda: 1500.0)
        self.games = defaultdict(list)
        self.rating_history = defaultdict(list)

    def features(self, team, at):
        matches = self.games[team]
        rating = self.elo[team]

        def change(years):
            cutoff = at - timedelta(days=365 * years)
            older = [r for d, r in self.rating_history[team] if d < cutoff]
            return rating - (older[-1] if older else 1500.0)

        values = [
            rating,
            change(1),
            change(3),
            len({d.year for d, gf, ga, comp in matches if comp == "FIFA World Cup"}),
            sum(
                (3 if gf > ga else 1 if gf == ga else 0)
                for d, gf, ga, comp in matches
                if comp != "International Friendly"
            ),
        ]
        for n in (5, 10):
            recent = matches[-n:]
            count = len(recent)
            wins = sum(gf > ga for _, gf, ga, _ in recent)
            draws = sum(gf == ga for _, gf, ga, _ in recent)
            values.extend(
                [
                    wins,
                    draws,
                    count - wins - draws,
                    sum(gf for _, gf, _, _ in recent),
                    sum(ga for _, _, ga, _ in recent),
                    wins / count if count else 0,
                ]
            )
        recent = matches[-20:]
        count = len(recent)
        gf = sum(x[1] for x in recent) / count if count else 0
        ga = sum(x[2] for x in recent) / count if count else 0
        scoring = sum(x[1] > 0 for x in recent) / count if count else 0
        clean = sum(x[2] == 0 for x in recent) / count if count else 0
        big = sum(x[1] >= 3 and x[1] > x[2] for x in recent) / count if count else 0
        values.extend([gf, gf, gf * 2.5, big, scoring, 1 / (1 + ga), ga, clean])
        return np.asarray(values, dtype=np.float64)

    def vector(self, home, away, at):
        h, a = self.features(home, at), self.features(away, at)
        return np.concatenate((h, a, h[:17] - a[:17]))

    def update_day(self, games):
        changes = defaultdict(float)
        for game in games:
            h, a = self.elo[game.home], self.elo[game.away]
            expectation = 1 / (1 + 10 ** ((a - h - (0 if game.neutral else 80)) / 400))
            score = (
                1
                if game.home_score > game.away_score
                else 0.5
                if game.home_score == game.away_score
                else 0
            )
            delta = 30 * (score - expectation)
            changes[game.home] += delta
            changes[game.away] -= delta
            self.games[game.home].append(
                (game.date, game.home_score, game.away_score, game.competition)
            )
            self.games[game.away].append(
                (game.date, game.away_score, game.home_score, game.competition)
            )
        for team, delta in changes.items():
            self.elo[team] += delta
            self.rating_history[team].append((games[0].date, self.elo[team]))

    @classmethod
    def before(cls, history, as_of):
        state = cls()
        # Dates without original intraday availability use conservative day boundaries.
        ordered = sorted(
            (g for g in history if g.date.date() < utc(as_of).date()),
            key=lambda g: (g.date, g.match_id),
        )
        for _, batch in groupby(ordered, key=lambda g: g.date.date()):
            state.update_day(list(batch))
        return state


def training_rows(history):
    state = PrematchState()
    for _, batch in groupby(
        sorted(history, key=lambda g: (g.date, g.match_id)), key=lambda g: g.date.date()
    ):
        games = list(batch)
        for game in games:
            # Cold starts are not silently filled with invented form.
            if len(state.games[game.home]) >= 5 and len(state.games[game.away]) >= 5:
                label = (
                    0
                    if game.home_score > game.away_score
                    else 1
                    if game.home_score == game.away_score
                    else 2
                )
                yield game, state.vector(game.home, game.away, game.date), label
        state.update_day(games)
