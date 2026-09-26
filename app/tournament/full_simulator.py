"""All 104 matches: 12 groups, official Annex C, and the fixed knockout tree."""

import time
from collections import Counter, defaultdict

import numpy as np

from app.domain.contracts import digest
from app.tournament.group_rules import KNOCKOUT, qualified_slots, rank_group


def simulate_full(
    stage, distribution, count=1000, seed=42, forced=None, cancelled=lambda: False, timeout=120
):
    if not 100 <= count <= 20000:
        raise ValueError("Simulation count must be between 100 and 20000")
    forced = forced or {}
    by_id = {m.fixture_id: m for m in stage.matches}
    knockout_ids = {m[0] for m in KNOCKOUT}
    for match_id, team in forced.items():
        if match_id in knockout_ids:
            if match_id in stage.knockout_winners:
                raise ValueError("Cannot override a completed knockout match")
            if any(m.home_score is None for m in stage.matches):
                raise ValueError("Knockout scenarios require completed groups")
            continue
        if match_id not in by_id or by_id[match_id].home_score is not None:
            raise ValueError("Full-tournament scenarios target unplayed group matches")
        if team not in (by_id[match_id].home, by_id[match_id].away):
            raise ValueError("Forced winner is not a participant")
    if not set(stage.knockout_winners) <= {m[0] for m in KNOCKOUT}:
        raise ValueError("Unknown official knockout match ID")
    teams = sorted(t for members in stage.groups.values() for t in members)
    champion, reached, finals = Counter(), defaultdict(Counter), Counter()
    positions = {t: Counter() for t in teams}
    cache = {}
    rng = np.random.default_rng(seed)
    start = time.monotonic()

    def get(h, a, neutral=True):
        key = (h, a, neutral)
        if key not in cache:
            cache[key] = distribution(h, a, neutral)
        return cache[key]

    def group_score(match, path):
        if match.home_score is not None:
            return match.home_score, match.away_score
        dist = get(match.home, match.away, match.neutral)
        if match.fixture_id in forced:
            mask = (
                np.tril(np.ones_like(dist.scores), -1)
                if forced[match.fixture_id] == match.home
                else np.triu(np.ones_like(dist.scores), 1)
            )
            matrix = dist.scores * mask
            matrix /= matrix.sum()
            index = int(np.argmax(matrix)) if path else rng.choice(matrix.size, p=matrix.ravel())
            return tuple(int(x) for x in np.unravel_index(index, matrix.shape))
        return (
            dist.representative_score(int(np.argmax(dist.probabilities)))
            if path
            else dist.sample(rng)
        )

    for iteration in range(count + 1):
        if cancelled():
            raise RuntimeError("Task cancelled")
        if time.monotonic() - start > timeout:
            raise TimeoutError("Simulation time budget exceeded")
        path = iteration == count
        matches = []
        for match in stage.matches:
            hs, aws = group_score(match, path)
            matches.append({**match.model_dump(mode="json"), "home_score": hs, "away_score": aws})
        tables = {
            g: rank_group(members, [m for m in matches if m["group"] == g], stage.fifa_rankings)
            for g, members in stage.groups.items()
        }
        slots, thirds = qualified_slots(tables, stage.fifa_rankings)
        if not path:
            for table in tables.values():
                for pos, row in enumerate(table, 1):
                    positions[row["team"]][pos] += 1
        representative = []
        for match_id, home_slot, away_slot in KNOCKOUT:
            h, a = slots[home_slot], slots[away_slot]
            num = int(match_id)
            round_name = (
                "round_of_32"
                if num <= 88
                else "round_of_16"
                if num <= 96
                else "quarter_finals"
                if num <= 100
                else "semi_finals"
                if num <= 102
                else "third_place"
                if num == 103
                else "final"
            )
            observed = stage.knockout_winners.get(match_id)
            if observed:
                if observed not in (h, a):
                    raise ValueError(
                        "Observed knockout winner conflicts with qualified participants"
                    )
                winner = observed
            elif match_id in forced:
                if forced[match_id] not in (h, a):
                    raise ValueError("Scenario participant is not guaranteed to reach this match")
                winner = forced[match_id]
            else:
                dist = get(h, a)
                winner = (
                    h
                    if (
                        dist.home_advancement >= 0.5
                        if path
                        else rng.random() < dist.home_advancement
                    )
                    else a
                )
            slots["W" + match_id] = winner
            slots["L" + match_id] = a if winner == h else h
            if path:
                representative.append(
                    {
                        "fixture_id": match_id,
                        "stage": round_name,
                        "home": h,
                        "away": a,
                        "winner": winner,
                        "source": "observed" if observed else "representative",
                    }
                )
            else:
                reached[round_name][h] += 1
                reached[round_name][a] += 1
                if round_name == "final":
                    finals[tuple(sorted((h, a)))] += 1
        if not path:
            champion[slots["W104"]] += 1
    probs = {t: champion[t] / count for t in teams}
    order = sorted(teams, key=lambda t: (-probs[t], t))
    return {
        "champion": order[0],
        "champion_probability": probs[order[0]],
        "champion_distribution": probs,
        "top5": [{"team": t, "probability": probs[t]} for t in order[:5]],
        "stage_probabilities": {s: {t: c[t] / count for t in teams} for s, c in reached.items()},
        "group_position_probabilities": {
            t: {str(p): positions[t][p] / count for p in range(1, 5)} for t in teams
        },
        "representative_group_tables": tables,
        "representative_group_matches": matches,
        "representative_third_place_ranking": thirds,
        "final_matchups": [
            {"teams": list(pair), "probability": n / count} for pair, n in sorted(finals.items())
        ],
        "representative_path": representative,
        "representative_path_champion": slots["W104"],
        "simulation_count": count,
        "seed": seed,
        "constraints": forced,
        "sampling_standard_error": {
            t: float(np.sqrt(p * (1 - p) / count)) for t, p in probs.items()
        },
        "bracket_version": digest({"format": "fifa-2026", "stage": stage.model_dump(mode="json")}),
        "format": "fifa_2026_full",
        "rules_version": "FIFA-May-2026-articles12-13-annexC",
        "group_assumptions": [
            "Unplayed matches assume no additional conduct deductions; FIFA rankings are fixed at snapshot publication."
        ],
    }
