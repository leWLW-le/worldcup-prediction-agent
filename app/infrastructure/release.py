"""Idempotently seed the versioned real-data replay, never overwrite existing records."""

import json
from pathlib import Path


def seed_release(store):
    path = Path("data/verified/release-result.json")
    if not path.exists():
        return
    from scripts.release_v2 import released_snapshot

    snapshot = released_snapshot()
    result = json.loads(path.read_text(encoding="utf-8"))
    if result["snapshot_id"] != snapshot.snapshot_id:
        raise ValueError("Release snapshot/result digest mismatch")
    store.put_input(snapshot)
    try:
        store.result(result["run_id"])
    except KeyError:
        store.save_result(result)
