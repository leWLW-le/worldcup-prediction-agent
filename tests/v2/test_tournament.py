import pytest

from app.models.distributions import from_matrix, poisson_matrix
from app.tournament.bracket import BracketGraph
from app.tournament.simulator import simulate


def balanced(*args):
    return from_matrix(poisson_matrix(1, 1), [0.35, 0.3, 0.35])


def test_four_team_exact_probability_and_stage_counts(snapshot):
    graph = BracketGraph(snapshot.fixtures)
    result = simulate(graph, balanced, count=10000)
    for p in result["champion_distribution"].values():
        assert p == pytest.approx(0.25, abs=0.02)
    assert sum(result["stage_probabilities"]["semi_finals"].values()) == 4
    assert sum(result["stage_probabilities"]["final"].values()) == 2
    assert {tuple(x["teams"]) for x in result["final_matchups"]} == {
        ("A", "C"),
        ("A", "D"),
        ("B", "C"),
        ("B", "D"),
    }


def test_scenario_preserves_other_side(snapshot):
    graph = BracketGraph(snapshot.fixtures)
    result = simulate(graph, balanced, count=5000, forced={"sf1": "A"})
    assert result["champion_distribution"]["B"] == 0
    assert result["champion_distribution"]["A"] == pytest.approx(0.5, abs=0.025)
    assert {tuple(x["teams"]) for x in result["final_matchups"]} == {("A", "C"), ("A", "D")}


def test_repeatable_rng(snapshot):
    graph = BracketGraph(snapshot.fixtures)
    assert simulate(graph, balanced, count=100) == simulate(graph, balanced, count=100)


def test_invalid_or_finished_constraint(snapshot):
    graph = BracketGraph(snapshot.fixtures)
    with pytest.raises(ValueError):
        simulate(graph, balanced, forced={"sf1": "C"})
    with pytest.raises(ValueError):
        simulate(graph, balanced, forced={"f": "A"})


def test_actual_winner_locked(snapshot):
    first = snapshot.fixtures[0].model_copy(update={"status": "finished", "actual_winner": "B"})
    graph = BracketGraph((first, *snapshot.fixtures[1:]))
    result = simulate(graph, balanced, count=100)
    assert result["champion_distribution"]["A"] == 0


def test_missing_bracket_fails_instead_of_shuffle(snapshot):
    with pytest.raises(ValueError):
        BracketGraph(snapshot.fixtures[:2])


def test_duplicate_team_rejected(snapshot):
    second = snapshot.fixtures[1].model_copy(update={"home_source": "team:A"})
    with pytest.raises(ValueError):
        BracketGraph((snapshot.fixtures[0], second, snapshot.fixtures[2]))


def test_cancel_and_timeout(snapshot):
    graph = BracketGraph(snapshot.fixtures)
    with pytest.raises(RuntimeError, match="cancelled"):
        simulate(graph, balanced, cancelled=lambda: True)
    with pytest.raises(TimeoutError):
        simulate(graph, balanced, timeout=-1)
