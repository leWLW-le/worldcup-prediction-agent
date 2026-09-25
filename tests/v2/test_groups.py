from itertools import combinations

import pytest

from app.domain.groups import GroupStage
from app.models.distributions import from_matrix, poisson_matrix
from app.tournament.full_simulator import simulate_full
from app.tournament.group_rules import annex_c, conduct_score, rank_group
from scripts.release_v2 import released_snapshot


def match(h, a, hs, aws, **extra):
    return dict(home=h, away=a, home_score=hs, away_score=aws, **extra)


def test_head_to_head_precedes_overall_goal_difference():
    matches = [
        match("A", "B", 1, 0),
        match("A", "C", 0, 1),
        match("A", "D", 1, 0),
        match("B", "C", 5, 0),
        match("B", "D", 5, 0),
        match("C", "D", 0, 1),
    ]
    table = rank_group(list("ABCD"), matches, {t: (i,) for i, t in enumerate("ABCD", 1)})
    assert [r["team"] for r in table][:2] == ["A", "B"]


def test_recursive_head_to_head_for_remaining_tied_teams():
    # A/B/C each have 6 points; mini-league goals separate A, then B beats C directly.
    matches = [
        match("A", "B", 3, 0),
        match("B", "C", 2, 0),
        match("C", "A", 2, 1),
        match("A", "D", 1, 0),
        match("B", "D", 1, 0),
        match("C", "D", 6, 0),
    ]
    table = rank_group(list("ABCD"), matches, {t: (i,) for i, t in enumerate("ABCD", 1)})
    assert [r["team"] for r in table][:3] == ["A", "B", "C"]


def test_conduct_then_historical_ranking():
    matches = [
        match(a, b, 0, 0, home_conduct=-1 if a == "A" else 0, away_conduct=0)
        for a, b in combinations("ABCD", 2)
    ]
    table = rank_group(list("ABCD"), matches, {"A": (1, 1), "B": (2, 3), "C": (2, 2), "D": (4, 4)})
    assert [r["team"] for r in table] == ["C", "B", "D", "A"]
    assert conduct_score([{"match_id": "1", "person_id": "p", "sanction": "yellow_and_red"}]) == -5
    with pytest.raises(ValueError, match="Duplicate"):
        conduct_score([{"match_id": "1", "person_id": "p", "sanction": "yellow"}] * 2)


def test_every_official_annex_combination_has_exactly_eight_distinct_eligible_opponents():
    table = annex_c()
    assert set(table) == {"".join(c) for c in combinations("ABCDEFGHIJKL", 8)}
    eligible = {
        "1A": "CEFHI",
        "1B": "EFGIJ",
        "1D": "BEFIJ",
        "1E": "ABCDF",
        "1G": "AEHIJ",
        "1I": "CDFGH",
        "1K": "DEIJL",
        "1L": "EHIJK",
    }
    for key, mapping in table.items():
        assert "".join(sorted(mapping.values())) == key
        assert all(group in eligible[winner] for winner, group in mapping.items())


def test_complete_tournament_invariants_and_scenario():
    stage = released_snapshot().group_stage
    dist = from_matrix(poisson_matrix(1.2, 1.2))
    result = simulate_full(stage, lambda *args: dist, count=100, seed=3)
    assert len(result["representative_group_matches"]) == 72
    assert len(result["representative_path"]) == 32
    assert sum(result["champion_distribution"].values()) == pytest.approx(1)
    for name, total in [
        ("round_of_32", 32),
        ("round_of_16", 16),
        ("quarter_finals", 8),
        ("semi_finals", 4),
        ("final", 2),
        ("third_place", 2),
    ]:
        assert sum(result["stage_probabilities"][name].values()) == pytest.approx(total)
    again = simulate_full(stage, lambda *args: dist, count=100, seed=3)
    assert result["champion_distribution"] == again["champion_distribution"]
    m = stage.matches[0]
    scenario = simulate_full(stage, lambda *args: dist, count=100, forced={m.fixture_id: m.home})
    score = scenario["representative_group_matches"][0]
    assert score["home_score"] > score["away_score"]
    with pytest.raises(ValueError):
        GroupStage.model_validate({**stage.model_dump(), "matches": stage.matches[:-1]})
