from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.domain.contracts import FixtureNode, HistoricalGame, TournamentInput
from app.infrastructure.jobs import Jobs
from app.infrastructure.store import Store
from app.models.registry import ModelRegistry
from app.pipelines.prediction import PredictionPipeline


@pytest.fixture
def snapshot():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    history = []
    for day in range(60):
        for i, (h, a) in enumerate(
            (("A", "B"), ("C", "D")) if day % 2 else (("A", "C"), ("B", "D"))
        ):
            history.append(
                HistoricalGame(
                    match_id=f"h{day}-{i}",
                    date=start + timedelta(days=day),
                    home=h,
                    away=a,
                    home_score=day % 3,
                    away_score=(day + i) % 2,
                    neutral=True,
                    competition="International Friendly",
                    source="test-synthetic",
                    score_basis="90_minutes",
                )
            )
    as_of = start + timedelta(days=100)
    fixtures = [
        FixtureNode(
            fixture_id="sf1",
            stage="semi_finals",
            home_source="team:A",
            away_source="team:B",
            kickoff=as_of + timedelta(days=1),
        ),
        FixtureNode(
            fixture_id="sf2",
            stage="semi_finals",
            home_source="team:C",
            away_source="team:D",
            kickoff=as_of + timedelta(days=2),
        ),
        FixtureNode(
            fixture_id="f",
            stage="final",
            home_source="winner:sf1",
            away_source="winner:sf2",
            kickoff=as_of + timedelta(days=5),
        ),
    ]
    return TournamentInput(
        season=2026,
        as_of=as_of,
        source="test fixture",
        provenance="synthetic",
        history=tuple(history),
        fixtures=tuple(fixtures),
    )


@pytest.fixture
def service(snapshot, tmp_path):
    engine = create_engine(
        "sqlite:///" + str(tmp_path / "test.db"), connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    store = Store(sessionmaker(bind=engine))
    store.put_input(snapshot)
    registry = ModelRegistry()
    pipeline = PredictionPipeline(store, registry, allow_demo=True)
    jobs = Jobs(store, pipeline)
    yield SimpleNamespace(store=store, registry=registry, pipeline=pipeline, jobs=jobs)
    jobs.close()
    engine.dispose()
