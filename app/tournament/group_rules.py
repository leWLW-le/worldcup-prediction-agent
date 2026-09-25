"""FIFA May 2026 regulations articles 12-13 and Annex C."""

import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

RULES_URL = "https://digitalhub.fifa.com/m/636f5c9c6f29771f/original/FWC2026_regulations_EN.pdf"


def conduct_score(events):
    """One mutually exclusive deduction per player/official per match."""
    penalties = {"yellow": -1, "second_yellow": -3, "red": -4, "yellow_and_red": -5}
    if len({(e["match_id"], e["person_id"]) for e in events}) != len(events):
        raise ValueError("Duplicate conduct deduction for a person in the same match")
    return sum(penalties[e["sanction"]] for e in events)


def stats(teams, matches):
    table = {
        t: {"team": t, "points": 0, "gf": 0, "ga": 0, "gd": 0, "played": 0, "conduct": 0}
        for t in teams
    }
    for m in matches:
        h, a = m["home"], m["away"]
        if h not in table or a not in table:
            continue
        hs, aws = m["home_score"], m["away_score"]
        for team, gf, ga, conduct in (
            (h, hs, aws, m.get("home_conduct", 0)),
            (a, aws, hs, m.get("away_conduct", 0)),
        ):
            row = table[team]
            row["points"] += 3 if gf > ga else 1 if gf == ga else 0
            row["gf"] += gf
            row["ga"] += ga
            row["gd"] += gf - ga
            row["played"] += 1
            row["conduct"] += conduct
    return table


def partitions(teams, key):
    buckets = defaultdict(list)
    for team in teams:
        buckets[key(team)].append(team)
    return [buckets[k] for k in sorted(buckets, reverse=True)]


def rank_group(teams, matches, rankings):
    table = stats(teams, matches)
    if any(row["played"] != 3 for row in table.values()):
        raise ValueError("Final group ranking requires all six matches")

    def fallback(tied):
        def key(t):
            return (
                table[t]["gd"],
                table[t]["gf"],
                table[t]["conduct"],
                tuple(-r for r in rankings[t]),
            )

        groups = partitions(tied, key)
        if any(len(group) > 1 for group in groups):
            raise ValueError("Ranking tie remains; supply older FIFA ranking editions")
        return [group[0] for group in groups]

    def head_to_head(tied):
        if len(tied) == 1:
            return tied
        mini = stats(tied, matches)
        groups = partitions(tied, lambda t: (mini[t]["points"], mini[t]["gd"], mini[t]["gf"]))
        if len(groups) == 1:
            return fallback(tied)
        return [t for group in groups for t in head_to_head(group)]

    order = [
        t for tied in partitions(teams, lambda t: table[t]["points"]) for t in head_to_head(tied)
    ]
    return [table[t] for t in order]


def rank_thirds(tables, rankings):
    rows = [{**table[2], "group": group} for group, table in tables.items()]

    def key(row):
        return (
            -row["points"],
            -row["gd"],
            -row["gf"],
            -row["conduct"],
            tuple(rankings[row["team"]]),
        )

    rows.sort(key=key)
    if len({key(r) for r in rows}) != len(rows):
        raise ValueError("Third-place tie requires older FIFA ranking editions")
    return rows


@lru_cache
def annex_c():
    data = json.loads(Path(__file__).with_name("annex_c_2026.json").read_text(encoding="utf-8"))
    return data["combinations"]


def qualified_slots(tables, rankings):
    thirds = rank_thirds(tables, rankings)
    advancing = thirds[:8]
    assignment = annex_c()["".join(sorted(r["group"] for r in advancing))]
    slots = {
        f"{position}{group}": table[position - 1]["team"]
        for group, table in tables.items()
        for position in (1, 2)
    }
    slots.update(
        {f"third:{winner}": tables[group][2]["team"] for winner, group in assignment.items()}
    )
    return slots, thirds


# Match IDs and edges are the official schedule, never a random pairing.
KNOCKOUT = [
    ("73", "2A", "2B"),
    ("74", "1E", "third:1E"),
    ("75", "1F", "2C"),
    ("76", "1C", "2F"),
    ("77", "1I", "third:1I"),
    ("78", "2E", "2I"),
    ("79", "1A", "third:1A"),
    ("80", "1L", "third:1L"),
    ("81", "1D", "third:1D"),
    ("82", "1G", "third:1G"),
    ("83", "2K", "2L"),
    ("84", "1H", "2J"),
    ("85", "1B", "third:1B"),
    ("86", "1J", "2H"),
    ("87", "1K", "third:1K"),
    ("88", "2D", "2G"),
    ("89", "W74", "W77"),
    ("90", "W73", "W75"),
    ("91", "W76", "W78"),
    ("92", "W79", "W80"),
    ("93", "W83", "W84"),
    ("94", "W81", "W82"),
    ("95", "W86", "W88"),
    ("96", "W85", "W87"),
    ("97", "W89", "W90"),
    ("98", "W93", "W94"),
    ("99", "W91", "W92"),
    ("100", "W95", "W96"),
    ("101", "W97", "W98"),
    ("102", "W99", "W100"),
    ("103", "L101", "L102"),
    ("104", "W101", "W102"),
]
