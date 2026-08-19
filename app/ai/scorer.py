"""ESCAPE SCORE — the product metric, and the diversity rule behind the three cards.

Design constraints, in order of importance:

* **explainable** — every number traces to one readable function;
* **testable** — pure functions of ``(Candidate, EscapeRequest, NormalizedIntent)``,
  no I/O, no randomness;
* **reproducible** — same inputs, same score, forever.

The score is a *heuristic product metric*, not an objective measure of how good
a trip is. It exists to rank comparable options and to show the user which
constraint is being stretched. See ``docs/ai.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.schemas import NormalizedIntent
from app.domain.candidate import Candidate
from app.domain.models import (
    EscapeRequest,
    Mood,
    ScenarioKind,
    ScoreBreakdown,
    TransportKind,
)
from app.utils.text import overlap_score

# Component weights per archetype. They sum to 1.0 in every column, which is why
# the three cards genuinely optimise for different things instead of being the
# same ranking sliced three ways.
WEIGHTS: dict[ScenarioKind, dict[str, float]] = {
    ScenarioKind.SILENCE: {
        "budget": 0.20, "time": 0.15, "wishes": 0.20, "mood": 0.15, "convenience": 0.30,
    },
    ScenarioKind.MADNESS: {
        "budget": 0.15, "time": 0.30, "wishes": 0.20, "mood": 0.25, "convenience": 0.10,
    },
    ScenarioKind.UNEXPECTED: {
        "budget": 0.20, "time": 0.20, "wishes": 0.15, "mood": 0.15, "convenience": 0.30,
    },
}

# Which moods each archetype is built to satisfy.
ARCHETYPE_MOODS: dict[ScenarioKind, tuple[Mood, ...]] = {
    ScenarioKind.SILENCE: (Mood.SILENCE, Mood.ROMANCE),
    ScenarioKind.MADNESS: (Mood.ENERGY, Mood.NIGHTLIFE, Mood.IMPRESSIONS),
    ScenarioKind.UNEXPECTED: (Mood.SPONTANEITY, Mood.IMPRESSIONS),
}

COMFORT_BY_KIND: dict[TransportKind, int] = {
    TransportKind.TRAIN: 88,
    TransportKind.PLANE: 78,
    TransportKind.SUBURBAN: 72,
    TransportKind.BUS: 58,
    TransportKind.UNKNOWN: 60,
}


@dataclass(frozen=True)
class ScoredCandidate:
    """A candidate with its score under one archetype."""

    candidate: Candidate
    kind: ScenarioKind
    score: ScoreBreakdown

    @property
    def total(self) -> int:
        return self.score.total


# --------------------------------------------------------------------------
# Components
# --------------------------------------------------------------------------


def budget_fit(candidate: Candidate, request: EscapeRequest) -> tuple[int, str | None]:
    """100 when the trip uses the budget well; falls off sharply above it."""
    budget = request.budget_rub
    price = candidate.total_price
    if price <= 0:
        return 55, "часть цен не пришла из Туту — оценка приблизительная"
    ratio = price / budget
    if ratio > 1.0:
        overshoot = min((ratio - 1.0) / 0.25, 1.0)
        return max(0, int(55 - 55 * overshoot)), "выходит за бюджет"
    if ratio >= 0.60:
        # Using 60–100% of the budget is the sweet spot: it buys the best trip
        # available without pretending the user wanted to save money.
        return int(88 + 12 * (1 - abs(0.82 - ratio) / 0.22)), None
    if ratio >= 0.30:
        return int(70 + 18 * ((ratio - 0.30) / 0.30)), None
    return int(55 + 15 * (ratio / 0.30)), "заметно дешевле, чем можно себе позволить"


def time_fit(candidate: Candidate, request: EscapeRequest) -> tuple[int, str | None]:
    """How much of the available time is left for the place itself."""
    total_minutes = request.duration_hours * 60
    travel = candidate.travel_minutes
    if travel <= 0:
        return 55, "время в пути не пришло из Туту"
    if travel >= total_minutes * 0.8:
        return 5, "почти всё время уходит на дорогу"
    share_on_place = 1 - travel / total_minutes
    # 0.55–0.85 of time on the ground is the comfortable band.
    if share_on_place >= 0.85:
        return 100, None
    if share_on_place >= 0.55:
        return int(80 + 20 * ((share_on_place - 0.55) / 0.30)), None
    return int(25 + 55 * ((share_on_place - 0.20) / 0.35)) if share_on_place > 0.20 else 20, (
        "дорога съедает больше половины времени"
    )


def wish_fit(candidate: Candidate, intent: NormalizedIntent) -> tuple[int, str | None]:
    """Overlap between free-text wishes and what this destination actually is."""
    tags = candidate.destination.tags
    if not intent.tags:
        return 80, None  # nothing asked for — nothing unmet

    matched = 0.0
    for tag in intent.tags:
        matched += overlap_score(tag, tags + tuple(candidate.destination.name.split()))
    base = min(1.0, matched / max(1, len(intent.tags)))

    score = int(45 + 55 * base)
    if intent.named_places and candidate.destination.name in intent.named_places:
        score = min(100, score + 20)
    if intent.no_car and "без машины" in tags:
        score = min(100, score + 6)
    if intent.wants_cheap and candidate.total_price and candidate.total_price < 12_000:
        score = min(100, score + 6)
    note = None if score >= 70 else "пожелания учтены частично"
    return score, note


def mood_fit(candidate: Candidate, request: EscapeRequest, kind: ScenarioKind) -> tuple[int, str | None]:
    """Match between the requested moods, the archetype and the destination."""
    destination_moods = set(candidate.destination.moods)
    wanted = set(request.moods) or set(ARCHETYPE_MOODS[kind])
    archetype = set(ARCHETYPE_MOODS[kind])

    user_hit = len(wanted & destination_moods) / max(1, len(wanted))
    archetype_hit = len(archetype & destination_moods) / max(1, len(archetype))
    score = int(40 + 35 * user_hit + 25 * archetype_hit)
    note = None if score >= 65 else "настроение совпадает не полностью"
    return min(100, score), note


def convenience(candidate: Candidate, intent: NormalizedIntent) -> tuple[int, str | None]:
    """Transfers, comfort of the mode, night departures, a bed that exists."""
    score = COMFORT_BY_KIND.get(candidate.kind, 60)
    notes: list[str] = []

    score -= candidate.transfers * 14
    if candidate.transfers:
        notes.append("есть пересадки")

    if candidate.is_night_ride:
        if intent.wants_daytime_travel:
            score -= 22
            notes.append("ночной выезд, хотя просили дневной")
        else:
            score += 4  # a night train saves a hotel night

    if candidate.kind in intent.avoided_transport:
        score -= 25
        notes.append("транспорт, которого просили избежать")
    elif candidate.kind in intent.preferred_transport:
        score += 10

    if candidate.nights > 0 and candidate.hotel is None:
        score -= 12
        notes.append("проживание не подтвердилось в Туту")
    elif candidate.hotel is not None and candidate.hotel.distance_to_center_km is not None:
        if candidate.hotel.distance_to_center_km <= 1.5:
            score += 6

    if not candidate.has_full_pricing:
        score -= 6

    score = max(0, min(100, score))
    return score, notes[0] if notes else None


# --------------------------------------------------------------------------
# Aggregate
# --------------------------------------------------------------------------


def score_candidate(
    candidate: Candidate,
    request: EscapeRequest,
    intent: NormalizedIntent,
    kind: ScenarioKind,
) -> ScoreBreakdown:
    """Compute the full ESCAPE SCORE for one candidate under one archetype."""
    budget, budget_note = budget_fit(candidate, request)
    time_, time_note = time_fit(candidate, request)
    wishes, wish_note = wish_fit(candidate, intent)
    mood, mood_note = mood_fit(candidate, request, kind)
    conv, conv_note = convenience(candidate, intent)

    weights = WEIGHTS[kind]
    total = (
        budget * weights["budget"]
        + time_ * weights["time"]
        + wishes * weights["wishes"]
        + mood * weights["mood"]
        + conv * weights["convenience"]
    )

    if kind is ScenarioKind.UNEXPECTED:
        # Novelty is what this card is for: a well-known city cannot win it.
        total = total * 0.65 + candidate.destination.novelty * 0.35

    notes = [n for n in (budget_note, time_note, wish_note, mood_note, conv_note) if n]

    return ScoreBreakdown(
        budget=budget,
        time=time_,
        wishes=wishes,
        mood=mood,
        convenience=conv,
        total=max(0, min(100, int(round(total)))),
        notes=notes[:4],
    )


def score_all(
    candidates: list[Candidate], request: EscapeRequest, intent: NormalizedIntent
) -> dict[ScenarioKind, list[ScoredCandidate]]:
    """Score every candidate under every archetype, best first."""
    table: dict[ScenarioKind, list[ScoredCandidate]] = {}
    for kind in ScenarioKind:
        scored = [
            ScoredCandidate(candidate=c, kind=kind, score=score_candidate(c, request, intent, kind))
            for c in candidates
        ]
        scored.sort(key=lambda s: (s.total, s.candidate.destination.novelty), reverse=True)
        table[kind] = scored
    return table


def select_diverse(
    candidates: list[Candidate], request: EscapeRequest, intent: NormalizedIntent
) -> list[ScoredCandidate]:
    """Pick three cards that are genuinely different, not the top-3 of one list.

    Order matters: SILENCE and MADNESS claim their best option first, then
    UNEXPECTED takes the best *remaining* one — which is exactly the card whose
    job is to be something you would not have picked. Destinations are never
    repeated across cards; if the pool is too small we relax that rule for the
    last slot rather than showing two cards instead of three.
    """
    if not candidates:
        return []

    table = score_all(candidates, request, intent)
    picked: list[ScoredCandidate] = []
    used_cities: set[str] = set()
    used_kinds: set[TransportKind] = set()

    for kind in (ScenarioKind.SILENCE, ScenarioKind.MADNESS, ScenarioKind.UNEXPECTED):
        choice = _first_free(table[kind], used_cities, used_kinds, strict=True)
        if choice is None:
            choice = _first_free(table[kind], used_cities, used_kinds, strict=False)
        if choice is None and table[kind]:
            choice = table[kind][0]  # last resort: repeat a city rather than lose a card
        if choice is not None:
            picked.append(choice)
            used_cities.add(choice.candidate.destination.name)
            used_kinds.add(choice.candidate.kind)
    return picked


def _first_free(
    scored: list[ScoredCandidate],
    used_cities: set[str],
    used_kinds: set[TransportKind],
    *,
    strict: bool,
) -> ScoredCandidate | None:
    """First option whose city (and, when strict, transport) is still unused."""
    for item in scored:
        if item.candidate.destination.name in used_cities:
            continue
        if strict and len(used_kinds) < 2 and item.candidate.kind in used_kinds:
            continue
        return item
    return None


def diversity_index(picked: list[ScoredCandidate]) -> float:
    """0..1 measure of how different the three cards are. Used in tests."""
    if len(picked) < 2:
        return 0.0
    cities = {p.candidate.destination.name for p in picked}
    kinds = {p.candidate.kind for p in picked}
    tags = [set(p.candidate.destination.tags) for p in picked]
    shared = set.intersection(*tags) if tags else set()
    union = set.union(*tags) if tags else set()
    tag_diversity = 1 - (len(shared) / len(union)) if union else 0.0
    return round(
        0.5 * (len(cities) / len(picked))
        + 0.2 * (len(kinds) / len(picked))
        + 0.3 * tag_diversity,
        3,
    )
