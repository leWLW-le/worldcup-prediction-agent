"""Shared baseline/scenario simulator with cancellation and exact stage counts."""

import time
from collections import Counter, defaultdict

import numpy as np

from app.domain.contracts import digest


def simulate(
    graph, distribution, count=1000, seed=42, forced=None, cancelled=lambda: False, timeout=120
):
    if not 100 <= count <= 20000:
        raise ValueError("Simulation count must be between 100 and 20000")
    forced = forced or {}
    by_id = {n.fixture_id: n for n in graph.nodes}
    for fixture_id, team in forced.items():
        if fixture_id not in by_id or by_id[fixture_id].status == "finished":
            raise ValueError("Scenario must target a scheduled fixture")
        node = by_id[fixture_id]
        # Future participants must already be resolved, not speculative names.
        home = graph.known_participant(node.home_source)
        away = graph.known_participant(node.away_source)
        if home is None or away is None:
            raise ValueError("Scenario participants must be known")
        if team not in (home, away):
            raise ValueError("Forced winner is not a participant")
    rng = np.random.default_rng(seed)
    champion, reached, finals = Counter(), defaultdict(Counter), Counter()
    cache = {}
    start = time.monotonic()

    def get_distribution(node, home, away):
        key = (home, away, node.neutral)
        if key not in cache:
            cache[key] = distribution(home, away, node.neutral)
        return cache[key]

    representative = []
    for iteration in range(count + 1):
        if cancelled():
            raise RuntimeError("Task cancelled")
        if time.monotonic() - start > timeout:
            raise TimeoutError("Simulation time budget exceeded")
        winners = {}
        is_path = iteration == count
        for node in graph.nodes:
            h = graph.resolve(node.home_source, winners)
            a = graph.resolve(node.away_source, winners)
            if node.status == "finished":
                winner = node.actual_winner
                if winner not in (h, a):
                    raise ValueError("Recorded result conflicts with resolved participants")
            elif node.fixture_id in forced:
                winner = forced[node.fixture_id]
            else:
                dist = get_distribution(node, h, a)
                if is_path:
                    winner = h if dist.home_advancement >= 0.5 else a
                else:
                    winner = h if rng.random() < dist.home_advancement else a
            winners[node.fixture_id] = winner
            if is_path:
                forecast = {}
                if node.status != "finished":
                    dist = get_distribution(node, h, a)
                    outcome = int(np.argmax(dist.probabilities))
                    forecast = {
                        "probabilities_90_minutes": dict(
                            zip(("home", "draw", "away"), dist.probabilities)
                        ),
                        "home_advancement_probability": dist.home_advancement,
                        "representative_score_90_minutes": list(dist.representative_score(outcome)),
                    }
                representative.append(
                    {
                        "fixture_id": node.fixture_id,
                        "stage": node.stage,
                        "home": h,
                        "away": a,
                        "winner": winner,
                        "source": "observed"
                        if node.status == "finished"
                        else "scenario"
                        if node.fixture_id in forced
                        else "representative",
                        **forecast,
                    }
                )
            else:
                reached[node.stage][h] += 1
                reached[node.stage][a] += 1
                if node.stage == "final":
                    finals[tuple(sorted((h, a)))] += 1
        if not is_path:
            champion[winners[graph.final_id]] += 1
    probabilities = {t: champion[t] / count for t in graph.teams}
    ordered = sorted(probabilities, key=lambda t: (-probabilities[t], t))
    stages = {
        stage: {t: counts[t] / count for t in graph.teams} for stage, counts in reached.items()
    }
    return {
        "champion": ordered[0],
        "champion_probability": probabilities[ordered[0]],
        "champion_distribution": probabilities,
        "top5": [{"team": t, "probability": probabilities[t]} for t in ordered[:5]],
        "stage_probabilities": stages,
        "final_matchups": [
            {"teams": list(pair), "probability": n / count} for pair, n in sorted(finals.items())
        ],
        "representative_path": representative,
        "representative_path_champion": representative[-1]["winner"],
        "simulation_count": count,
        "seed": seed,
        "constraints": forced,
        "sampling_standard_error": {
            t: float(np.sqrt(p * (1 - p) / count)) for t, p in probabilities.items()
        },
        "bracket_version": digest([n.model_dump(mode="json") for n in graph.nodes]),
    }
