from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.data.v2_provider import refresh_snapshot
from app.infrastructure.store import BusyError
from app.tournament.bracket import BracketGraph


def test_provider_refresh_preserves_graph_and_history(snapshot):
    now = datetime.now(timezone.utc)
    fixtures = [
        f.model_copy(update={"kickoff": now + timedelta(days=i + 1)})
        for i, f in enumerate(snapshot.fixtures)
    ]
    original = snapshot.model_copy(update={"as_of": now, "fixtures": tuple(fixtures)})
    rows = [
        {
            "fixture": {
                "id": f.fixture_id,
                "date": f.kickoff.isoformat(),
                "status": {"short": "NS"},
            },
            "league": {"season": original.season},
            "teams": {"home": {"name": f.home_source[5:]}, "away": {"name": f.away_source[5:]}},
        }
        for f in fixtures
    ]
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"response": rows}))
    updated = refresh_snapshot(original, "test", transport)
    assert updated.history == original.history
    assert updated.provenance == "synthetic"
    assert updated.snapshot_id != original.snapshot_id
    assert [f.home_source for f in updated.fixtures] == [f.home_source for f in original.fixtures]
    BracketGraph(updated.fixtures)


@pytest.mark.parametrize("payload", [{"response": []}, {"errors": {"quota": "exhausted"}}])
def test_bad_provider_response_never_fabricates_data(snapshot, payload):
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
    with pytest.raises(ValueError):
        refresh_snapshot(snapshot, "test", transport)


def test_daily_quota_is_shared_between_store_instances(service):
    from app.infrastructure.store import Store

    second = Store(service.store.sessions)
    service.store.consume_budget("provider", 1)
    with pytest.raises(BusyError, match="budget"):
        second.consume_budget("provider", 1)


def test_finished_final_requires_finished_predecessors(snapshot):
    final = snapshot.fixtures[-1].model_copy(update={"status": "finished", "actual_winner": "A"})
    with pytest.raises(ValueError, match="unresolved"):
        BracketGraph((*snapshot.fixtures[:-1], final))
