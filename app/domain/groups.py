"""2026 group-stage inputs; rankings must be supplied as-of the snapshot."""

from datetime import datetime, timezone
from itertools import combinations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GroupMatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    fixture_id: str
    group: str = Field(pattern="^[A-L]$")
    home: str
    away: str
    kickoff: datetime
    neutral: bool = True
    home_score: int | None = Field(default=None, ge=0, le=30)
    away_score: int | None = Field(default=None, ge=0, le=30)
    home_conduct: int = Field(default=0, le=0)
    away_conduct: int = Field(default=0, le=0)

    @model_validator(mode="after")
    def validate_result(self):
        if (self.home_score is None) != (self.away_score is None) or self.home == self.away:
            raise ValueError("Invalid group match result/participants")
        if (
            self.home_score is not None
            and not {"home_conduct", "away_conduct"} <= self.model_fields_set
        ):
            raise ValueError(
                "Completed group matches require explicit conduct deductions, including zero"
            )
        return self


class GroupStage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    groups: dict[str, tuple[str, str, str, str]]
    matches: tuple[GroupMatch, ...] = Field(min_length=72, max_length=72)
    # Most recent published ranking first; older editions resolve an exact tie.
    fifa_rankings: dict[str, tuple[int, ...]]
    ranking_date: datetime
    ranking_source: str = Field(min_length=1)
    knockout_winners: dict[str, str] = {}
    knockout_completed_at: dict[str, datetime] = {}

    @model_validator(mode="after")
    def complete_schedule(self):
        if set(self.groups) != set("ABCDEFGHIJKL"):
            raise ValueError("2026 requires groups A through L")
        teams = [t for group in self.groups.values() for t in group]
        if len(set(teams)) != 48 or set(self.fifa_rankings) != set(teams):
            raise ValueError("48 unique teams and complete ranking coverage required")
        if any(not ranks or any(r < 1 for r in ranks) for ranks in self.fifa_rankings.values()):
            raise ValueError("Invalid FIFA ranking history")
        if len({len(r) for r in self.fifa_rankings.values()}) != 1:
            raise ValueError("All teams must use the same ranking editions")
        if len({m.fixture_id for m in self.matches}) != 72:
            raise ValueError("Duplicate group fixture IDs")
        for group, members in self.groups.items():
            matches = [m for m in self.matches if m.group == group]
            pairs = [tuple(sorted((m.home, m.away))) for m in matches]
            if len(pairs) != 6 or set(pairs) != {
                tuple(sorted(p)) for p in combinations(members, 2)
            }:
                raise ValueError("Each group must contain exactly one match per pair")
        if self.knockout_winners and any(m.home_score is None for m in self.matches):
            raise ValueError("Knockout results require a completed group stage")
        from app.tournament.group_rules import KNOCKOUT

        edges = {m[0]: m[1:] for m in KNOCKOUT}
        if set(self.knockout_winners) != set(self.knockout_completed_at) or not set(
            self.knockout_winners
        ) <= set(edges):
            raise ValueError("Completed knockout matches require timestamps and official IDs")
        for match_id in self.knockout_winners:
            for source in edges[match_id]:
                if source.startswith(("W", "L")) and source[1:] not in self.knockout_winners:
                    raise ValueError("Completed knockout match has an unresolved predecessor")
        return self

    def validate_as_of(self, as_of, provider_fixtures=()):
        def utc(value):
            return (
                value.replace(tzinfo=timezone.utc)
                if value.tzinfo is None
                else value.astimezone(timezone.utc)
            )

        if utc(self.ranking_date) > as_of:
            raise ValueError("FIFA ranking was unavailable at snapshot time")
        if any(utc(value) >= as_of for value in self.knockout_completed_at.values()):
            raise ValueError("Knockout result was unavailable at snapshot time")
        for match in self.matches:
            if (match.home_score is None) != (utc(match.kickoff) >= as_of):
                evidence = next(
                    (r for r in provider_fixtures if r.get("fixture_id") == match.fixture_id), None
                )
                if (
                    match.home_score is None
                    and evidence
                    and evidence.get("status") in ("NS", "TBD", "PST")
                ):
                    continue
                raise ValueError("Group result availability conflicts with as_of")
