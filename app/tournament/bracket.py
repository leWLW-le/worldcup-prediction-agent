"""A fixed knockout graph. Unknown paths are errors, never random draws."""

from collections import Counter

ORDER = {"round_of_32": 0, "round_of_16": 1, "quarter_finals": 2, "semi_finals": 3, "final": 4}


class BracketGraph:
    def __init__(self, fixtures):
        self.nodes = sorted(fixtures, key=lambda f: (ORDER[f.stage], f.fixture_id))
        by_id = {n.fixture_id: n for n in self.nodes}
        if len(by_id) != len(self.nodes):
            raise ValueError("Duplicate fixture IDs")
        finals = [n for n in self.nodes if n.stage == "final"]
        if len(finals) != 1:
            raise ValueError("Exactly one final is required")
        consumers, teams, possible = Counter(), Counter(), {}
        for node in self.nodes:
            sides = []
            for source in (node.home_source, node.away_source):
                kind, value = source.split(":", 1)
                if kind == "team":
                    teams[value] += 1
                    sides.append({value})
                else:
                    if value not in possible:
                        raise ValueError("Missing or cyclic predecessor")
                    parent = by_id[value]
                    if node.status == "finished" and parent.status != "finished":
                        raise ValueError("Finished fixture has an unresolved predecessor")
                    if (
                        ORDER[parent.stage] + 1 != ORDER[node.stage]
                        or parent.kickoff >= node.kickoff
                    ):
                        raise ValueError("Invalid stage/time transition")
                    consumers[value] += 1
                    sides.append(possible[value])
            if sides[0] & sides[1]:
                raise ValueError("A team can appear on both sides of a match")
            if node.actual_winner and node.actual_winner not in set.union(*sides):
                raise ValueError("Actual winner not reachable")
            possible[node.fixture_id] = (
                {node.actual_winner} if node.actual_winner else set.union(*sides)
            )
        if any(v != 1 for v in teams.values()):
            raise ValueError("Duplicate direct team entries")
        if any(consumers[n.fixture_id] != (0 if n.stage == "final" else 1) for n in self.nodes):
            raise ValueError("Disconnected graph or duplicated advancement")
        self.possible = possible
        self.teams = sorted(teams)
        self.final_id = finals[0].fixture_id
        self.by_id = by_id

    def known_participant(self, source):
        kind, value = source.split(":", 1)
        if kind == "team":
            return value
        return self.by_id[value].actual_winner

    @staticmethod
    def resolve(source, winners):
        kind, value = source.split(":", 1)
        return value if kind == "team" else winners[value]
