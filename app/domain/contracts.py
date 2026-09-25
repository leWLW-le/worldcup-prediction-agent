"""Versioned public contracts. Numeric facts are never supplied by the LLM."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.groups import GroupStage


def utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def digest(value) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, default=str).encode()
    ).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class HistoricalGame(StrictModel):
    match_id: str
    date: datetime
    home: str
    away: str
    home_score: int = Field(ge=0, le=99)
    away_score: int = Field(ge=0, le=99)
    neutral: bool = True
    competition: str = "unknown"
    source: str
    score_basis: Literal["90_minutes"]

    @field_validator("date")
    @classmethod
    def normalize_date(cls, value):
        return utc(value)

    @model_validator(mode="after")
    def distinct(self):
        if self.home == self.away:
            raise ValueError("A team cannot play itself")
        return self


class FixtureNode(StrictModel):
    fixture_id: str
    stage: Literal["round_of_32", "round_of_16", "quarter_finals", "semi_finals", "final"]
    # Each source is team:<canonical ID/name> or winner:<fixture_id>.
    home_source: str
    away_source: str
    kickoff: datetime
    neutral: bool = True
    status: Literal["scheduled", "finished"] = "scheduled"
    actual_winner: str | None = None

    @field_validator("kickoff")
    @classmethod
    def normalize_date(cls, value):
        return utc(value)

    @model_validator(mode="after")
    def result_consistent(self):
        if (self.status == "finished") != (self.actual_winner is not None):
            raise ValueError("Only finished matches must have an actual winner")
        for source in (self.home_source, self.away_source):
            kind, sep, name = source.partition(":")
            if sep != ":" or kind not in ("team", "winner") or not name.strip():
                raise ValueError("Invalid bracket source")
        return self


class TournamentInput(StrictModel):
    season: int = Field(ge=1930, le=2200)
    as_of: datetime
    source: str = Field(min_length=1)
    provenance: Literal["verified", "unverified", "synthetic"]
    history: tuple[HistoricalGame, ...] = Field(default=(), max_length=100000)
    fixtures: tuple[FixtureNode, ...] = Field(default=(), max_length=31)
    group_stage: GroupStage | None = None
    warnings: tuple[str, ...] = ()

    @field_validator("as_of")
    @classmethod
    def normalize_date(cls, value):
        return utc(value)

    @model_validator(mode="after")
    def time_boundary(self):
        if self.group_stage:
            if self.season != 2026 or self.fixtures:
                raise ValueError(
                    "Full-group format is 2026 only and supplies its official knockout graph"
                )
            self.group_stage.validate_as_of(self.as_of)
        elif not self.fixtures:
            raise ValueError("A fixed bracket or complete group-stage input is required")
        if any(f.status == "finished" and f.kickoff >= self.as_of for f in self.fixtures):
            raise ValueError("Future result cannot be known at as_of")
        if any(f.status == "scheduled" and f.kickoff < self.as_of for f in self.fixtures):
            raise ValueError(
                "Past/live fixture needs a final result; live prediction is unsupported"
            )
        if len({g.match_id for g in self.history}) != len(self.history):
            raise ValueError("Duplicate historical match IDs")
        return self

    @property
    def snapshot_id(self):
        payload = self.model_dump(mode="json")
        if self.group_stage is None:
            payload.pop("group_stage")
        return digest(payload)


class PredictionRequest(StrictModel):
    snapshot_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    simulation_count: int = Field(default=1000, ge=100, le=20000)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)


class ScenarioRequest(PredictionRequest):
    fixture_id: str
    forced_winner: str


class CompareRequest(StrictModel):
    run_ids: tuple[str, ...] = Field(min_length=2, max_length=5)


class ExplainRequest(StrictModel):
    run_id: str


def validate_distribution(probabilities):
    import math

    if len(probabilities) != 3 or any(not math.isfinite(p) or p < 0 for p in probabilities):
        raise ValueError("Invalid outcome distribution")
    if abs(sum(probabilities) - 1) > 1e-8:
        raise ValueError("Outcome probabilities must sum to one")
