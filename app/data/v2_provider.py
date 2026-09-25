"""Refresh known fixture IDs without inventing knockout links or score semantics."""

from datetime import datetime, timezone

import httpx

from app.domain.contracts import TournamentInput


def refresh_snapshot(snapshot, api_key, transport=None):
    if snapshot.group_stage:
        raise ValueError("Full-tournament snapshots must be refreshed with complete scores, conduct and ranking provenance")
    if not api_key:
        raise ValueError("API_FOOTBALL is not configured")
    with httpx.Client(timeout=20, transport=transport) as client:
        response = client.get(
            "https://v3.football.api-sports.io/fixtures",
            params={"league": 1, "season": snapshot.season},
            headers={"x-apisports-key": api_key},
        )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise ValueError("Provider rejected refresh (check plan/quota)")
    data = {str(r["fixture"]["id"]): r for r in payload.get("response", [])}
    if not data:
        raise ValueError("Provider returned no fixtures; previous snapshot remains unchanged")
    fixtures = []
    for node in snapshot.fixtures:
        provider_id = node.fixture_id.removeprefix("af_")
        raw = data.get(provider_id)
        if raw is None:
            raise ValueError(f"Missing provider fixture: {node.fixture_id}")
        if raw.get("league", {}).get("season") != snapshot.season:
            raise ValueError("Provider season mismatch")
        status = raw["fixture"]["status"]["short"]
        if status not in ("NS", "TBD", "FT", "AET", "PEN"):
            raise ValueError(
                "Live/postponed fixtures require explicit review; no live model is configured"
            )
        # Preserve the graph; verify resolved direct team slots against source facts.
        for side, source in (("home", node.home_source), ("away", node.away_source)):
            if source.startswith("team:") and source[5:] != raw["teams"][side]["name"]:
                raise ValueError("Team mapping changed; review canonical team IDs before refresh")
        winner = None
        if status in ("FT", "AET", "PEN"):
            for side in ("home", "away"):
                if raw["teams"][side].get("winner") is True:
                    winner = raw["teams"][side]["name"]
            if winner is None:
                raise ValueError("Finished knockout fixture has no explicit winner")
        fixtures.append(
            {
                **node.model_dump(mode="json"),
                "status": "finished" if winner else "scheduled",
                "actual_winner": winner,
                "kickoff": raw["fixture"]["date"],
            }
        )
    return TournamentInput.model_validate(
        {
            **snapshot.model_dump(mode="json"),
            "fixtures": fixtures,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "source": snapshot.source + "; API-Football refreshed",
            "warnings": list(snapshot.warnings)
            + ["Refresh changes fixtures only; history retains its original provenance"],
        }
    )
