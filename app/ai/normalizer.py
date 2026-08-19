"""Stage 1–2 of the pipeline: INPUT NORMALIZER → CONSTRAINT EXTRACTION.

The heuristic pass always runs and always produces a usable intent. The LLM pass
is additive: it can enrich tags, name conflicts and read phrasing the rules miss,
but it can never take away what the rules were sure about. If the model is off,
slow or wrong, the product does not notice.
"""

from __future__ import annotations

import json
import logging

from app.ai.llm import LLMClient
from app.ai.prompts import INPUT_NORMALIZER
from app.ai.schemas import NormalizedIntent
from app.domain.destinations import (
    DESTINATIONS_BY_NAME,
    clean_origin_name,
    find_destination,
    normalize_origin,
    origin_display_name,
)
from app.domain.models import EscapeRequest, Mood, MOOD_LABELS
from app.utils import text as T
from app.utils.currency import format_rub
from app.utils.dates import humanize_duration_hours

logger = logging.getLogger(__name__)

# Cities that are plausible starting points, checked before destinations.
_ORIGIN_HINTS = ("москва", "мск", "питер", "спб", "петербург", "санкт-петербург")


def heuristic_intent(request: EscapeRequest) -> NormalizedIntent:
    """Rule-based extraction. Deterministic, fast, fully unit-tested."""
    wishes = request.wishes
    blob = T.normalize(" ".join(wishes))

    origin_name = clean_origin_name(request.origin)
    origin_key = normalize_origin(request.origin)
    if not request.origin:
        for hint in _ORIGIN_HINTS:
            if hint in blob:
                origin_key = normalize_origin(hint)
                origin_name = origin_display_name(origin_key)
                break

    preferred, avoided = T.infer_transport(wishes)
    inferred_moods = T.infer_moods(wishes)
    moods = list(request.moods) + [m for m in inferred_moods if m not in request.moods]

    named: list[str] = []
    for city_key in DESTINATIONS_BY_NAME:
        if city_key in blob and city_key not in _ORIGIN_HINTS:
            destination = find_destination(city_key)
            if destination:
                named.append(destination.name)

    tags: list[str] = []
    for wish in wishes:
        for token in T.tokens(wish):
            if len(token) > 2 and token not in tags:
                tags.append(token)

    intent = NormalizedIntent(
        origin=origin_name,
        tags=tags[:12],
        moods=moods[:6],
        named_places=named[:4],
        preferred_transport=sorted(preferred, key=lambda k: k.value),
        avoided_transport=sorted(avoided, key=lambda k: k.value),
        wants_sea=T.mentions_any(wishes, T.SEA_WORDS),
        wants_warmth=T.mentions_any(wishes, T.WARM_WORDS),
        wants_cheap=T.mentions_any(wishes, T.CHEAP_WORDS),
        wants_daytime_travel=T.mentions_any(wishes, T.DAYTIME_WORDS),
        no_car=T.mentions_any(wishes, T.NO_CAR_WORDS),
    )
    intent.summary = _summarize(request, intent)
    intent.conflicts = detect_conflicts(request, intent)
    return intent


def detect_conflicts(request: EscapeRequest, intent: NormalizedIntent) -> list[str]:
    """Name the impossible combinations out loud instead of failing.

    A conflict is never an error state: it is a compromise the product explains.
    """
    conflicts: list[str] = []

    if intent.wants_sea and request.duration_hours < 30:
        conflicts.append(
            "До моря за это время не доехать — держим воду и набережные, но уже речные."
        )
    if intent.wants_sea and request.budget_rub < 12_000:
        conflicts.append(
            "Море при таком бюджете возможно, только если пожертвовать временем дороги."
        )
    if intent.wants_warmth and request.duration_hours < 40:
        conflicts.append("За тёплым климатом нужно лететь — на это уйдёт почти всё время.")
    if intent.wants_cheap and request.budget_rub > 40_000:
        conflicts.append("«Недорого» при таком бюджете читаем как «без переплат», а не как экономию.")
    if request.budget_rub < 6_000 and request.duration_hours > 48:
        conflicts.append(
            "Бюджета хватает на дорогу, но не на несколько ночей — ищем варианты покороче или подешевле."
        )
    if intent.named_places and len(intent.named_places) > 1:
        conflicts.append("Названо несколько городов — берём их как ориентир, а не как маршрут.")
    if intent.avoided_transport and len(intent.avoided_transport) >= 3:
        conflicts.append("Почти весь транспорт отклонён — оставили то, что реально доедет.")
    return conflicts[:4]


def _summarize(request: EscapeRequest, intent: NormalizedIntent) -> str:
    """One line describing the request, shown under the results headline."""
    parts = [format_rub(request.budget_rub), humanize_duration_hours(request.duration_hours)]
    if request.moods:
        parts.append(" + ".join(MOOD_LABELS[m] for m in request.moods[:3]))
    if request.wishes:
        parts.append(" · ".join(request.wishes))
    return " · ".join(parts)


async def normalize_request(
    request: EscapeRequest, llm: LLMClient | None = None
) -> NormalizedIntent:
    """Stage 1: interpret the request.

    The language model is the primary interpreter — it reads the free-text
    wishes, infers mood, transport preference and conflicts. The rule-based
    :func:`heuristic_intent` only runs as a fallback, for when no API key is
    configured or the model call fails, so the product still works end-to-end
    without ever going down.
    """
    if llm is not None and llm.enabled:
        payload = {
            "budget_rub": request.budget_rub,
            "duration_hours": request.duration_hours,
            "moods": [m.value for m in request.moods],
            "wishes": request.wishes,
            "origin": request.origin or "Москва",
        }
        result = await llm.ask_model(
            system=INPUT_NORMALIZER,
            user=json.dumps(payload, ensure_ascii=False),
            schema=NormalizedIntent,
            temperature=0.2,
        )
        if result is not None:
            if request.origin:
                result.origin = clean_origin_name(request.origin)
            elif result.origin:
                result.origin = clean_origin_name(result.origin)
            else:
                result.origin = origin_display_name(normalize_origin(request.origin))
            if not result.summary:
                result.summary = _summarize(request, result)
            return result
        logger.warning("llm normalization failed — falling back to rules")

    return heuristic_intent(request)


def merge_intents(base: NormalizedIntent, extra: NormalizedIntent) -> NormalizedIntent:
    """Union of both readings, with the deterministic one winning on conflicts."""
    merged = base.model_copy(deep=True)

    merged.tags = _union(base.tags, extra.tags, limit=12)
    merged.named_places = _union(base.named_places, extra.named_places, limit=4)
    merged.conflicts = _union(base.conflicts, extra.conflicts, limit=4)

    for mood in extra.moods:
        if isinstance(mood, Mood) and mood not in merged.moods and len(merged.moods) < 6:
            merged.moods.append(mood)

    # The rules own transport, because a mis-read "не ночью" is a ruined trip.
    for kind in extra.preferred_transport:
        if kind not in merged.preferred_transport and kind not in merged.avoided_transport:
            merged.preferred_transport.append(kind)

    merged.wants_sea = base.wants_sea or extra.wants_sea
    merged.wants_warmth = base.wants_warmth or extra.wants_warmth
    merged.wants_cheap = base.wants_cheap or extra.wants_cheap
    merged.wants_daytime_travel = base.wants_daytime_travel or extra.wants_daytime_travel
    merged.no_car = base.no_car or extra.no_car
    if extra.summary:
        merged.summary = extra.summary
    return merged


def _union(first: list[str], second: list[str], *, limit: int) -> list[str]:
    result = list(first)
    for item in second:
        if item and item not in result:
            result.append(item)
    return result[:limit]
