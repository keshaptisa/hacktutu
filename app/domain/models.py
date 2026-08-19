"""Domain models — the single vocabulary shared by MCP adapter, AI and API.

Everything the UI ever sees is one of these types. Raw MCP payloads stop at the
adapter boundary and never reach the presentation layer.
"""

from __future__ import annotations

import datetime as dt
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------


class Mood(str, Enum):
    """The six moods offered on the first screen."""

    SILENCE = "silence"
    ENERGY = "energy"
    ROMANCE = "romance"
    SPONTANEITY = "spontaneity"
    NIGHTLIFE = "nightlife"
    IMPRESSIONS = "impressions"


class ScenarioKind(str, Enum):
    """The three archetypes every search resolves into."""

    SILENCE = "silence"
    MADNESS = "madness"
    UNEXPECTED = "unexpected"


class TransportKind(str, Enum):
    """Transport modes exposed by Tutu MCP."""

    TRAIN = "train"
    PLANE = "plane"
    BUS = "bus"
    SUBURBAN = "suburban"
    UNKNOWN = "unknown"


class DataOrigin(str, Enum):
    """Provenance of a piece of data. Rendered in the UI, never hidden."""

    MCP = "mcp"          # came from Tutu MCP as-is
    DEMO = "demo"        # curated offline sample, explicitly labelled
    DERIVED = "derived"  # computed by us from MCP data (e.g. totals)


SCENARIO_TITLES: dict[ScenarioKind, str] = {
    ScenarioKind.SILENCE: "ТИШИНА",
    ScenarioKind.MADNESS: "БЕЗУМСТВО",
    ScenarioKind.UNEXPECTED: "НЕОЖИДАННОСТЬ",
}

MOOD_LABELS: dict[Mood, str] = {
    Mood.SILENCE: "Тишина",
    Mood.ENERGY: "Энергия",
    Mood.ROMANCE: "Романтика",
    Mood.SPONTANEITY: "Спонтанность",
    Mood.NIGHTLIFE: "Ночная жизнь",
    Mood.IMPRESSIONS: "Впечатления",
}


# --------------------------------------------------------------------------
# Request side
# --------------------------------------------------------------------------


class EscapeRequest(BaseModel):
    """What the user gives us on the first screen. Almost everything optional."""

    budget_rub: int = Field(ge=1_000, le=500_000, description="Total budget, ₽")
    duration_hours: int = Field(ge=6, le=336, description="Trip length in hours")
    moods: list[Mood] = Field(default_factory=list, max_length=6)
    wishes: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Up to three free-form hints. Empty is a valid request.",
    )
    origin: str | None = Field(default=None, max_length=64)
    start_date: date | None = None

    @field_validator("wishes", mode="before")
    @classmethod
    def _clean_wishes(cls, value: Any) -> list[str]:
        """Drop blanks and clamp length — never reject the user's phrasing."""
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        cleaned: list[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                cleaned.append(text[:120])
        return cleaned[:3]

    @field_validator("moods", mode="before")
    @classmethod
    def _dedupe_moods(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        seen: list[Any] = []
        for item in value:
            if item not in seen:
                seen.append(item)
        return seen

    @property
    def duration_days(self) -> float:
        """Trip length in fractional days."""
        return round(self.duration_hours / 24, 2)


class RefinementRequest(BaseModel):
    """Free-text tweak applied to one already-chosen scenario."""

    note: str = Field(min_length=1, max_length=600)
    budget_rub: int | None = Field(default=None, ge=1_000, le=500_000)


class EmailRequest(BaseModel):
    """Address to send the finished escape to."""

    email: str = Field(min_length=5, max_length=254)

    @field_validator("email")
    @classmethod
    def _looks_like_email(cls, value: str) -> str:
        value = value.strip()
        local, sep, domain = value.partition("@")
        if not sep or not local or "." not in domain or " " in value:
            raise ValueError("Похоже, в адресе опечатка")
        return value


class RelaxRequest(BaseModel):
    """Ask the system to loosen exactly one constraint after an empty result."""

    parameter: Literal["budget", "time", "transport", "wish"]


# --------------------------------------------------------------------------
# Travel primitives (normalised MCP output)
# --------------------------------------------------------------------------


class PurchaseLink(BaseModel):
    """A booking URL that came from MCP. We never synthesise these."""

    label: str
    url: str
    source: DataOrigin = DataOrigin.MCP

    @field_validator("url")
    @classmethod
    def _http_only(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("booking url must be absolute http(s)")
        return value


class TransportSegment(BaseModel):
    """One leg of a journey."""

    kind: TransportKind = TransportKind.UNKNOWN
    carrier: str | None = None
    number: str | None = None
    from_place: str
    to_place: str
    departure: datetime | None = None
    arrival: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=0, le=10_000)
    price_rub: int | None = Field(default=None, ge=0)


class TransportOption(BaseModel):
    """A full there-and-back (or one-way) transport proposal."""

    id: str
    kind: TransportKind = TransportKind.UNKNOWN
    from_place: str
    to_place: str
    segments: list[TransportSegment] = Field(default_factory=list)
    transfers: int = Field(default=0, ge=0, le=10)
    total_duration_minutes: int | None = Field(default=None, ge=0)
    price_rub: int | None = Field(default=None, ge=0)
    is_night_ride: bool = False
    purchase: PurchaseLink | None = None
    source: DataOrigin = DataOrigin.MCP
    raw_hint: str | None = Field(
        default=None, description="Short human note about missing/odd MCP fields"
    )

    @property
    def duration_hours(self) -> float | None:
        if self.total_duration_minutes is None:
            return None
        return round(self.total_duration_minutes / 60, 1)


class HotelOption(BaseModel):
    """A place to sleep."""

    id: str
    name: str
    city: str
    image_url: str | None = None
    stars: int | None = Field(default=None, ge=0, le=5)
    rating: float | None = Field(default=None, ge=0, le=10)
    reviews_count: int | None = Field(default=None, ge=0)
    price_per_night_rub: int | None = Field(default=None, ge=0)
    nights: int = Field(default=0, ge=0, le=30)
    district: str | None = None
    distance_to_center_km: float | None = Field(default=None, ge=0)
    purchase: PurchaseLink | None = None
    source: DataOrigin = DataOrigin.MCP

    @property
    def total_price_rub(self) -> int | None:
        if self.price_per_night_rub is None:
            return None
        return self.price_per_night_rub * max(self.nights, 1)


# --------------------------------------------------------------------------
# Itinerary
# --------------------------------------------------------------------------


class ItineraryEvent(BaseModel):
    """One point on the visual timeline."""

    time: str = Field(description="HH:MM or a soft label like 'вечер'")
    title: str
    detail: str | None = None
    icon: Literal[
        "train", "plane", "bus", "hotel", "walk", "food", "view", "night", "free"
    ] = "free"


class ItineraryDay(BaseModel):
    """A single day of the escape."""

    index: int = Field(ge=1, le=14)
    weekday: str
    date: dt.date | None = None
    headline: str | None = None
    events: list[ItineraryEvent] = Field(default_factory=list, max_length=12)


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------


class ScoreBreakdown(BaseModel):
    """Explainable components of the ESCAPE SCORE (each 0–100)."""

    budget: int = Field(ge=0, le=100)
    time: int = Field(ge=0, le=100)
    wishes: int = Field(ge=0, le=100)
    mood: int = Field(ge=0, le=100)
    convenience: int = Field(ge=0, le=100)
    total: int = Field(ge=0, le=100)
    notes: list[str] = Field(default_factory=list, max_length=6)

    @property
    def as_rows(self) -> list[tuple[str, int]]:
        """Ordered rows for the UI panel."""
        return [
            ("Бюджет", self.budget),
            ("Время", self.time),
            ("Пожелания", self.wishes),
            ("Настроение", self.mood),
            ("Удобство", self.convenience),
        ]


# --------------------------------------------------------------------------
# Scenario & result
# --------------------------------------------------------------------------


class EscapeScenario(BaseModel):
    """One of the three interpretations of a single request."""

    id: str
    kind: ScenarioKind
    title: str
    destination: str
    region: str | None = None
    tagline: str = Field(max_length=280)
    reasons: list[str] = Field(default_factory=list, min_length=1, max_length=5)
    total_price_rub: int = Field(ge=0)
    duration_hours: int = Field(ge=0)
    nights: int = Field(ge=0, le=30)
    transport: TransportOption | None = None
    return_transport: TransportOption | None = None
    hotel: HotelOption | None = None
    itinerary: list[ItineraryDay] = Field(default_factory=list)
    score: ScoreBreakdown
    why_ai_picked: str = ""
    compromises: list[str] = Field(default_factory=list, max_length=4)
    data_origin: DataOrigin = DataOrigin.MCP
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _fill_title(self) -> "EscapeScenario":
        if not self.title:
            self.title = SCENARIO_TITLES[self.kind]
        return self

    @property
    def duration_label(self) -> str:
        """'3 дня' / '18 часов' — whatever reads naturally."""
        if self.duration_hours < 24:
            return f"{self.duration_hours} ч"
        days = round(self.duration_hours / 24)
        if days % 10 == 1 and days != 11:
            return f"{days} день"
        if days % 10 in (2, 3, 4) and days not in (12, 13, 14):
            return f"{days} дня"
        return f"{days} дней"

    def purchase_links(self) -> list[PurchaseLink]:
        """Only links that genuinely came from MCP."""
        links = [
            item.purchase
            for item in (self.transport, self.return_transport, self.hotel)
            if item is not None and item.purchase is not None
        ]
        return links


class EscapeResult(BaseModel):
    """The full response to one 'СБЕЖАТЬ'."""

    id: str
    request: EscapeRequest
    scenarios: list[EscapeScenario] = Field(default_factory=list, max_length=3)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    origin_city: str = "Москва"
    normalized_summary: str = ""
    conflicts: list[str] = Field(default_factory=list)
    data_origin: DataOrigin = DataOrigin.MCP
    degraded: bool = Field(
        default=False, description="True when MCP or LLM was unavailable"
    )
    degraded_reason: str | None = None
    relaxations_applied: list[str] = Field(default_factory=list)
    search_ms: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.scenarios


class RefinedEscape(BaseModel):
    """A scenario after 'ДОПИЛИТЬ МОЙ ПОБЕГ'."""

    escape_id: str
    scenario: EscapeScenario
    changes: list["RefinementChange"] = Field(default_factory=list)
    unmet: list[str] = Field(default_factory=list)
    note: str = ""


class RefinementChange(BaseModel):
    """A single before/after pair shown in the 'Что изменилось' block."""

    label: str
    before: str
    after: str


RefinedEscape.model_rebuild()
