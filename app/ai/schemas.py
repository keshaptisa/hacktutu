"""Schemas for the AI layer.

Every LLM call is contract-first: the model is asked for JSON and the JSON is
validated here before anything downstream touches it. A validation failure is
not an outage — the planner falls back to its deterministic path.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.domain.models import Mood, ScenarioKind, TransportKind


class NormalizedIntent(BaseModel):
    """Stage 1 output — constraints extracted from a very loose request."""

    origin: str = "Москва"
    summary: str = Field(default="", max_length=240)
    tags: list[str] = Field(default_factory=list, max_length=12)
    moods: list[Mood] = Field(default_factory=list, max_length=6)
    named_places: list[str] = Field(default_factory=list, max_length=4)
    preferred_transport: list[TransportKind] = Field(default_factory=list, max_length=4)
    avoided_transport: list[TransportKind] = Field(default_factory=list, max_length=4)
    wants_sea: bool = False
    wants_warmth: bool = False
    wants_cheap: bool = False
    wants_daytime_travel: bool = False
    no_car: bool = False
    conflicts: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("tags", "named_places", mode="before")
    @classmethod
    def _clean(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(v).strip()[:40] for v in value if str(v).strip()][:12]


class DestinationIdea(BaseModel):
    """One candidate city proposed before any MCP call is made."""

    city: str = Field(min_length=2, max_length=60)
    archetype: ScenarioKind | None = None
    reason: str = Field(default="", max_length=200)
    novelty: int = Field(default=50, ge=0, le=100)


class DestinationShortlist(BaseModel):
    """Stage 2 output — where we are going to ask Tutu about."""

    ideas: list[DestinationIdea] = Field(default_factory=list, max_length=12)


class ScenarioCopy(BaseModel):
    """Stage 4 output — the words for one scenario card.

    Deliberately contains no prices, no times and no links: those are ours and
    come from MCP. The model only writes about *meaning*.
    """

    tagline: str = Field(default="", max_length=240)
    reasons: list[str] = Field(default_factory=list, max_length=5)
    why_ai_picked: str = Field(default="", max_length=400)
    day_headlines: list[str] = Field(default_factory=list, max_length=8)
    activities: list[str] = Field(default_factory=list, max_length=14)

    @field_validator("reasons", "day_headlines", "activities", mode="before")
    @classmethod
    def _strings(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(v).strip()[:120] for v in value if str(v).strip()]


class RefinementPlan(BaseModel):
    """Stage 5 output — a structured reading of one free-text refinement."""

    avoid_night_transport: bool = False
    prefer_night_transport: bool = False
    preferred_transport: list[TransportKind] = Field(default_factory=list, max_length=4)
    hotel_near_center: bool = False
    hotel_quality_up: bool = False
    new_budget_rub: int | None = Field(default=None, ge=1_000, le=500_000)
    slower_pace: bool = False
    denser_pace: bool = False
    less_walking: bool = False
    more_free_time: bool = False
    keep_destination: bool = True
    note: str = Field(default="", max_length=300)
    unmet: list[str] = Field(default_factory=list, max_length=4)

    @property
    def touches_hotel(self) -> bool:
        return self.hotel_near_center or self.hotel_quality_up


class EmailCopy(BaseModel):
    """Stage 5 output — the human paragraphs of the itinerary email."""

    subject: str = Field(default="", max_length=120)
    intro: str = Field(default="", max_length=400)
    closing: str = Field(default="", max_length=240)
