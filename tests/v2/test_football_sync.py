from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import pytest

from app.core.config import Settings
from app.data.football_sync import conduct, normalize, provider_error, sync, to_snapshot
from app.domain.contracts import PredictionRequest
from app.models.distributions import from_matrix, poisson_matrix
from app.tournament.full_simulator import simulate_full
from scripts.release_v2 import released_snapshot


@pytest.fixture
def original():
    return released_snapshot()


def provider_rows(original, complete=False):
    rows = []
    for i, m in enumerate(original.group_stage.matches):
        rows.append(
            {
                "fixture": {
                    "id": 1000 + i,
                    "date": m.kickoff.isoformat(),
                    "status": {"short": "FT" if complete else "NS"},
                },
                "league": {"id": 1, "season": 2026, "round": "Group Stage - 1"},
                "teams": {
                    "home": {"id": i * 2, "name": m.home, "winner": True if complete else None},
                    "away": {
                        "id": i * 2 + 1,
                        "name": m.away,
                        "winner": False if complete else None,
                    },
                },
                "goals": {"home": 1 if complete else None, "away": 0 if complete else None},
                "score": {
                    "fulltime": {"home": 1 if complete else None, "away": 0 if complete else None}
                },
                "events": [],
            }
        )
    return rows


def transport_for(rows, covered=True, errors=None, calls=None):
    def respond(req):
        if calls is not None:
            calls.append(dict(req.url.params))
        if errors:
            return httpx.Response(200, json={"errors": errors})
        if req.url.path == "/leagues":
            data = [{"seasons": [{"year": 2026, "coverage": {"fixtures": {"events": covered}}}]}]
        elif "ids" in req.url.params:
            ids = req.url.params["ids"].split("-")
            assert len(ids) <= 20
            data = [r for r in rows if str(r["fixture"]["id"]) in ids]
        else:
            data = rows
        return httpx.Response(200, json={"response": data})

    return httpx.MockTransport(respond)


def test_real_group_scores_are_persisted_added_to_history_and_locked(service, original):
    rows = provider_rows(original, complete=True)
    calls = []
    feed = sync(
        service.store, Settings(API_FOOTBALL="test"), original, transport_for(rows, calls=calls)
    )
    assert feed["prediction_ready"], feed.get("prediction_error")
    assert len(calls) == 6  # fixtures + coverage + four batches, not 72 requests
    updated = service.store.get_input(feed["snapshot_id"])
    assert all(m.home_score == 1 for m in updated.group_stage.matches)
    assert len(updated.history) == len(original.history) + 72
    dist = from_matrix(poisson_matrix(1, 1))
    result = simulate_full(updated.group_stage, lambda *args: dist, count=100)
    assert all(
        m["home_score"] == 1 and m["away_score"] == 0
        for m in result["representative_group_matches"]
    )
    calls.clear()
    again = sync(
        service.store, Settings(API_FOOTBALL="test"), updated, transport_for(rows, calls=calls)
    )
    assert len(calls) == 1  # Completed details cached; history does not duplicate.
    assert len(service.store.get_input(again["snapshot_id"]).history) == len(updated.history)


def test_missing_discipline_coverage_shows_scores_without_fabricating_prediction(service, original):
    feed = sync(
        service.store,
        Settings(API_FOOTBALL="test"),
        original,
        transport_for(provider_rows(original, True), covered=False),
    )
    assert len(feed["fixtures"]) == 72
    assert not feed["prediction_ready"]
    assert "纪律" in feed["prediction_error"]
    assert service.store.feed(2026)["fixtures"][0]["score"]["home"] == 1


def test_provider_failure_preserves_last_success_and_redacts_errors(service, original):
    rows = provider_rows(original)
    first = sync(service.store, Settings(API_FOOTBALL="secret"), original, transport_for(rows))
    with pytest.raises(ValueError):
        sync(
            service.store,
            Settings(API_FOOTBALL="secret"),
            original,
            transport_for(rows, errors={"key": "secret"}),
        )
    feed = service.store.feed(2026)
    assert feed["fetched_at"] == first["fetched_at"]
    assert feed["fixtures"] == first["fixtures"]
    assert "secret" not in feed["last_error"]


def test_live_scores_remain_visible_but_are_not_treated_as_final(service, original):
    rows = provider_rows(original)
    rows[0]["fixture"]["status"]["short"] = "2H"
    rows[0]["goals"] = {"home": 2, "away": 1}
    feed = sync(service.store, Settings(API_FOOTBALL="test"), original, transport_for(rows))
    assert not feed["prediction_ready"]
    assert feed["fixtures"][0]["score"] == {"home": 2, "away": 1}
    assert "进行中" in feed["prediction_error"]


def test_short_schedule_never_overwrites_complete_prediction_input(service, original):
    service.store.put_input(original)
    feed = sync(
        service.store,
        Settings(API_FOOTBALL="test"),
        original,
        transport_for(provider_rows(original)[:5]),
    )
    assert not feed["prediction_ready"]
    assert "5/72" in feed["prediction_error"]
    assert service.store.get_input(original.snapshot_id) == original


def test_90_minutes_extra_time_and_penalties_are_separate(original):
    row = provider_rows(original, True)[0]
    row["fixture"]["status"]["short"] = "PEN"
    row["score"] = {
        "fulltime": {"home": 1, "away": 1},
        "extratime": {"home": 2, "away": 2},
        "penalty": {"home": 5, "away": 4},
    }
    row["goals"] = {"home": 2, "away": 2}
    r = normalize(row, 2026)
    assert r["score_90"] == {"home": 1, "away": 1}
    assert r["score_penalties"] == {"home": 5, "away": 4}
    assert r["winner"] == row["teams"]["home"]["name"]


def test_conduct_second_yellow_and_direct_red_are_mutually_exclusive(original):
    raw = provider_rows(original, True)[0]

    def event(person, detail, minute, comments=None):
        return {
            "type": "Card",
            "team": {"id": 0},
            "player": {"id": person},
            "detail": detail,
            "time": {"elapsed": minute},
            "comments": comments,
        }

    raw["events"] = [
        event(1, "Yellow Card", 10),
        event(1, "Red Card", 40, "Second yellow card"),
        event(2, "Yellow Card", 10),
        event(2, "Red Card", 40),
    ]
    assert conduct(raw) == (-8, 0)
    raw["events"].append(deepcopy(raw["events"][-1]))
    assert conduct(raw) == (-8, 0)
    raw["events"][0]["player"]["id"] = None
    with pytest.raises(ValueError, match="ID"):
        conduct(raw)


def test_refresh_workflow_uses_new_snapshot_not_old_replay(service, original):
    service.store.put_input(original)
    settings = Settings(API_FOOTBALL="test")
    feed = sync(service.store, settings, original, transport_for(provider_rows(original)))
    expected = {"run_id": "new", "snapshot_id": feed["snapshot_id"]}
    with (
        patch.object(
            service.jobs, "execute", return_value={"status": "completed", "run_id": "new"}
        ) as execute,
        patch.object(service.store, "result", return_value=expected),
    ):
        result = service.jobs.submit_refresh(
            PredictionRequest(snapshot_id=original.snapshot_id), settings, synchronous=True
        )
    assert result == expected
    assert execute.call_args.args[1].snapshot_id == feed["snapshot_id"]


def test_full_observed_tournament_locks_champion_and_rejects_wrong_pair(service, original):
    rows = provider_rows(original, True)
    feed = sync(service.store, Settings(API_FOOTBALL="test"), original, transport_for(rows))
    updated = service.store.get_input(feed["snapshot_id"])
    dist = from_matrix(poisson_matrix(1, 1))
    path = simulate_full(updated.group_stage, lambda *args: dist, count=100)["representative_path"]
    labels = {
        "round_of_32": "Round of 32",
        "round_of_16": "Round of 16",
        "quarter_finals": "Quarter-finals",
        "semi_finals": "Semi-finals",
        "third_place": "3rd Place Final",
        "final": "Final",
    }
    for i, match in enumerate(path):
        row = deepcopy(rows[0])
        row["fixture"].update(
            id=2000 + i, date=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        )
        row["league"]["round"] = labels[match["stage"]]
        row["teams"]["home"].update(name=match["home"], winner=match["winner"] == match["home"])
        row["teams"]["away"].update(name=match["away"], winner=match["winner"] == match["away"])
        feed["fixtures"].append(normalize(row, 2026))
    completed = to_snapshot(original, feed)
    result = simulate_full(completed.group_stage, lambda *args: dist, count=100)
    assert result["champion_probability"] == 1
    assert all(m["source"] == "observed" for m in result["representative_path"])
    feed["fixtures"][-1]["home"] = "Unknown team"
    with pytest.raises(ValueError, match="不一致"):
        to_snapshot(original, feed)


def test_provider_error_classification_never_echoes_credentials():
    assert "套餐" in provider_error(
        {"plan": "Free plans do not have access to this season, try from 2022 to 2024"}
    )
    assert "2022" in provider_error(
        {"plan": "Free plans do not have access to this season, try from 2022 to 2024"}
    )
    assert "配额" in provider_error({"requests": "You have reached the request limit for the day"})
    assert "认证" in provider_error({"token": "Invalid API key: secret-do-not-echo"})
    assert "secret" not in provider_error({"unexpected": "secret-do-not-echo"})


def test_secondary_api_remains_available_when_primary_rejects(service, original):
    def respond(request):
        if request.url.host == "v3.football.api-sports.io":
            return httpx.Response(
                200, json={"errors": {"plan": "No access to season on free plan"}}
            )
        assert request.url.params["season"] == "2026"
        assert request.headers["X-Auth-Token"] == "secondary-test"
        return httpx.Response(
            200,
            json={
                "matches": [
                    {
                        "id": 1,
                        "competition": {"code": "WC"},
                        "utcDate": "2026-06-11T19:00:00Z",
                        "status": "FINISHED",
                        "stage": "GROUP_STAGE",
                        "homeTeam": {"name": "Mexico"},
                        "awayTeam": {"name": "South Africa"},
                        "score": {
                            "duration": "REGULAR",
                            "winner": "HOME_TEAM",
                            "fullTime": {"home": 2, "away": 0},
                        },
                    }
                ]
            },
        )

    with pytest.raises(ValueError, match="套餐"):
        sync(
            service.store,
            Settings(API_FOOTBALL="primary-test", FOOTBALL_DATA_API="secondary-test"),
            original,
            httpx.MockTransport(respond),
        )
    feed = service.store.feed(2026)
    assert feed["fallback"]["fixtures"][0]["score_90"] == {"home": 2, "away": 0}
    assert feed["fallback"]["provider"] == "football-data.org"
    assert not feed["fallback"]["prediction_ready"]
