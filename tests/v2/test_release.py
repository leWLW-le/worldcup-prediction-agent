import json
from pathlib import Path

from app.infrastructure.release import seed_release
from app.infrastructure.store import ResultRecord
from scripts.release_v2 import released_snapshot


def test_release_matches_snapshot_and_postgres_id_width(service):
    result = json.loads(Path("data/verified/release-result.json").read_text(encoding="utf-8"))
    snapshot = released_snapshot()
    assert result["snapshot_id"] == snapshot.snapshot_id
    assert len(result["run_id"]) <= ResultRecord.__table__.c.id.type.length
    seed_release(service.store)
    seed_release(service.store)
    assert service.store.result(result["run_id"])["champion"] == result["champion"]
