"""Generate an explicitly synthetic four-team snapshot for local smoke tests."""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.domain.contracts import FixtureNode, HistoricalGame, TournamentInput


def demo_snapshot():
    as_of = datetime(2026, 7, 1, tzinfo=timezone.utc)
    history = []
    for day in range(240):
        pairs = (
            (("Demo A", "Demo B"), ("Demo C", "Demo D"))
            if day % 2
            else (("Demo A", "Demo C"), ("Demo B", "Demo D"))
        )
        for i, (home, away) in enumerate(pairs):
            history.append(
                HistoricalGame(
                    match_id=f"synthetic-{day}-{i}",
                    date=as_of - timedelta(days=300 - day),
                    home=home,
                    away=away,
                    home_score=day % 3,
                    away_score=(day + i) % 2,
                    neutral=True,
                    source="synthetic demonstration",
                    score_basis="90_minutes",
                )
            )
    fixtures = (
        FixtureNode(
            fixture_id="sf1",
            stage="semi_finals",
            home_source="team:Demo A",
            away_source="team:Demo B",
            kickoff=as_of + timedelta(days=1),
        ),
        FixtureNode(
            fixture_id="sf2",
            stage="semi_finals",
            home_source="team:Demo C",
            away_source="team:Demo D",
            kickoff=as_of + timedelta(days=2),
        ),
        FixtureNode(
            fixture_id="final",
            stage="final",
            home_source="winner:sf1",
            away_source="winner:sf2",
            kickoff=as_of + timedelta(days=5),
        ),
    )
    return TournamentInput(
        season=2026,
        as_of=as_of,
        source="synthetic demonstration",
        provenance="synthetic",
        history=tuple(history),
        fixtures=fixtures,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(demo_snapshot().model_dump(mode="json"), file, ensure_ascii=False, indent=2)
