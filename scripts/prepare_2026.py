"""Reconstruct the dated fixture-only pre-tournament view, excluding every result."""

import csv
import json
from pathlib import Path

ANCHORS = dict(
    zip(
        "ABCDEFGHIJKL",
        [
            "Mexico",
            "Canada",
            "Brazil",
            "United States",
            "Germany",
            "Netherlands",
            "Belgium",
            "Spain",
            "France",
            "Argentina",
            "Portugal",
            "England",
        ],
    )
)
RANKS = {
    "France": 1,
    "Spain": 2,
    "Argentina": 3,
    "England": 4,
    "Portugal": 5,
    "Brazil": 6,
    "Netherlands": 7,
    "Morocco": 8,
    "Belgium": 9,
    "Germany": 10,
    "Croatia": 11,
    "Colombia": 13,
    "Senegal": 14,
    "Mexico": 15,
    "United States": 16,
    "Uruguay": 17,
    "Japan": 18,
    "Switzerland": 19,
    "Iran": 21,
    "Turkey": 22,
    "Ecuador": 23,
    "Austria": 24,
    "South Korea": 25,
    "Australia": 27,
    "Algeria": 28,
    "Egypt": 29,
    "Canada": 30,
    "Norway": 31,
    "Panama": 33,
    "Ivory Coast": 34,
    "Sweden": 38,
    "Paraguay": 40,
    "Czech Republic": 41,
    "Scotland": 43,
    "Tunisia": 44,
    "DR Congo": 46,
    "Uzbekistan": 50,
    "Qatar": 55,
    "Iraq": 57,
    "South Africa": 60,
    "Saudi Arabia": 61,
    "Jordan": 63,
    "Bosnia and Herzegovina": 65,
    "Cape Verde": 69,
    "Ghana": 74,
    "Curaçao": 82,
    "Haiti": 83,
    "New Zealand": 85,
}


def prepare(path, output):
    with Path(path).open(encoding="utf-8") as file:
        rows = [
            r
            for r in csv.DictReader(file)
            if r["tournament"] == "FIFA World Cup" and "2026-06-11" <= r["date"] <= "2026-06-27"
        ]
    groups = {}
    for group, anchor in ANCHORS.items():
        members = {anchor}
        for _ in range(4):
            for row in rows:
                if row["home_team"] in members or row["away_team"] in members:
                    members.update([row["home_team"], row["away_team"]])
        if len(members) != 4:
            raise ValueError("Invalid group component")
        groups[group] = sorted(members)
    if {t for members in groups.values() for t in members} != set(RANKS):
        raise ValueError("Ranking/team mapping mismatch")
    matches = [
        {
            "fixture_id": "group-" + str(i + 1),
            "group": next(g for g, ts in groups.items() if r["home_team"] in ts),
            "home": r["home_team"],
            "away": r["away_team"],
            "kickoff": r["date"] + "T00:00:00Z",
            "neutral": r["neutral"] == "TRUE",
        }
        for i, r in enumerate(rows)
    ]
    stage = {
        "groups": groups,
        "matches": matches,
        "fifa_rankings": {t: [r] for t, r in RANKS.items()},
        "ranking_date": "2026-04-01T00:00:00Z",
        "ranking_source": "https://wildstat.com/p/7001/ddate/2026-04-01 ; publication: https://inside.fifa.com/fifa-world-ranking/men?dateId=id13433",
    }
    from app.domain.groups import GroupStage

    GroupStage.model_validate(stage)
    Path(output).write_text(json.dumps(stage, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("results_csv")
    parser.add_argument("output")
    args = parser.parse_args()
    prepare(args.results_csv, args.output)
