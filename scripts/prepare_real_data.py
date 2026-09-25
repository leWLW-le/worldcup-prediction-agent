"""Audit CC0 international results; retain only unambiguous 90-minute targets."""

import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.request import urlopen

REVISION = "394fe81893b062fbc2cf6257e988ac7cc4c039a1"
EXPECTED_HASHES = {
    "results.csv": "df35268f8fc341ff7fb93d448b4e40356676ac35300a6b4461fd199a99ac1514",
    "goalscorers.csv": "38cbc8007fb4aef7dd9f57e354623dca2abaf03a859530565ccf368e86a9f614",
}
BASE = f"https://raw.githubusercontent.com/martj42/international_results/{REVISION}/"


def prepare(cache, output):
    cache, output = Path(cache), Path(output)
    cache.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name in ("results.csv", "goalscorers.csv"):
        path = cache / name
        if not path.exists():
            path.write_bytes(urlopen(BASE + name, timeout=60).read())
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        if hashes[name] != EXPECTED_HASHES[name]:
            raise ValueError(f"Pinned source checksum mismatch: {name}")
    events = defaultdict(list)
    for g in csv.DictReader((cache / "goalscorers.csv").open(encoding="utf-8")):
        events[(g["date"], g["home_team"], g["away_team"])].append(g)
    kept, excluded = [], Counter()
    for row in csv.DictReader((cache / "results.csv").open(encoding="utf-8")):
        if not "1990-01-01" <= row["date"] < "2026-06-01":
            excluded["outside_window"] += 1
            continue
        key = (row["date"], row["home_team"], row["away_team"])
        try:
            hs, aws = int(row["home_score"]), int(row["away_score"])
        except ValueError:
            excluded["missing_result"] += 1
            continue
        goals = events[key]
        # For a scoreless match the 90-minute label remains 0-0 even if extra time occurred.
        if hs + aws:
            if Counter(g["team"] for g in goals) != Counter(
                {row["home_team"]: hs, row["away_team"]: aws}
            ):
                excluded["incomplete_goal_events"] += 1
                continue
            try:
                minutes = [int(g["minute"]) for g in goals]
            except ValueError:
                excluded["unknown_goal_minutes"] += 1
                continue
            if any(m < 1 or m > 90 for m in minutes):
                excluded["extra_time_or_ambiguous_minutes"] += 1
                continue
        elif goals:
            excluded["inconsistent_zero_score"] += 1
            continue
        kept.append(
            {
                "match_id": "real-" + hashlib.sha256("|".join(key).encode()).hexdigest()[:20],
                "date": row["date"],
                "home": row["home_team"],
                "away": row["away_team"],
                "home_score": hs,
                "away_score": aws,
                "neutral": row["neutral"] == "TRUE",
                "competition": "International Friendly"
                if row["tournament"] == "Friendly"
                else row["tournament"],
                "source": "martj42/international_results@" + REVISION,
                "score_basis": "90_minutes",
            }
        )
    if len({r["match_id"] for r in kept}) != len(kept):
        raise ValueError("Duplicate source match identity")
    with (output / "history.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(kept[0]))
        writer.writeheader()
        writer.writerows(kept)
    manifest = {
        "provenance": "verified",
        "source": "https://github.com/martj42/international_results",
        "revision": REVISION,
        "license": "CC0-1.0",
        "raw_sha256": hashes,
        "history_sha256": hashlib.sha256((output / "history.csv").read_bytes()).hexdigest(),
        "retained": len(kept),
        "excluded": dict(excluded),
        "start": kept[0]["date"],
        "end": kept[-1]["date"],
        "audit": "Nonzero scores require complete team goal counts and known minutes 1-90. Extra-time/ambiguous games excluded. Scoreless labels are unchanged by extra time.",
        "limitations": [
            "Selection favors competitions with goal-event coverage; missingness is not random.",
            "Retrospectively collected/corrected data, not historical publication snapshots.",
            "Verified means schema and source checks passed, not independent verification of every event.",
        ],
    }
    (output / "provenance.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "history.csv.gz").write_bytes(
        gzip.compress((output / "history.csv").read_bytes(), mtime=0)
    )
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("cache")
    parser.add_argument("output")
    args = parser.parse_args()
    print(json.dumps(prepare(args.cache, args.output), indent=2))
