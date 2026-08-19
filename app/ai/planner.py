"""The ESCAPE pipeline.

    USER INPUT
      → INPUT NORMALIZER        (ai/normalizer.py)
      → CONSTRAINT EXTRACTION   (ai/normalizer.py)
      → DESTINATION SHORTLIST   (here — decides *where to ask Tutu about*)
      → TUTU MCP SEARCH         (mcp/adapter.py)
      → CANDIDATE GENERATION    (here)
      → CANDIDATE SCORING       (ai/scorer.py)
      → THREE ESCAPE SCENARIOS  (ai/scorer.py diversity + ai/narrator.py copy)
      → STRUCTURED JSON         (domain/models.py)
      → UI

Each arrow is a function with a typed input and a typed output, which is why the
whole thing can run with the LLM switched off and still produce three coherent,
differentiated scenarios.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from app.ai.llm import LLMClient
from app.ai.narrator import build_itinerary, write_copy
from app.ai.normalizer import normalize_request
from app.ai.prompts import CANDIDATE_EVALUATION
from app.ai.schemas import DestinationShortlist, NormalizedIntent
from app.ai.scorer import ScoredCandidate, select_diverse
from app.core.config import Settings
from app.domain.candidate import Candidate
from app.domain.destinations import (
    DESTINATIONS,
    Destination,
    clean_origin_name,
    find_destination,
    normalize_origin,
    origin_display_name,
)
from app.domain.models import (
    DataOrigin,
    EscapeRequest,
    EscapeResult,
    EscapeScenario,
    ScenarioKind,
    SCENARIO_TITLES,
    TransportKind,
)
from app.mcp.adapter import SearchReport, TutuTravelClient
from app.services.demo_data import demo_candidate
from app.utils.dates import next_friday, nights_for

logger = logging.getLogger(__name__)

SHORTLIST_SIZE = 7
MAX_PARALLEL_DESTINATIONS = 4


@dataclass
class PlanOutcome:
    """The result plus the context needed to keep working on it later."""

    result: EscapeResult
    intent: NormalizedIntent
    start_date: date


class EscapePlanner:
    """Owns the pipeline. Stateless between requests apart from its clients."""

    def __init__(
        self,
        settings: Settings,
        travel: TutuTravelClient,
        llm: LLMClient | None = None,
    ):
        self._settings = settings
        self._travel = travel
        self._llm = llm

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    async def plan(self, request: EscapeRequest) -> PlanOutcome:
        """Run the full pipeline for one 'СБЕЖАТЬ'."""
        started = time.perf_counter()
        intent = await normalize_request(request, self._llm)

        origin_name = clean_origin_name(intent.origin or request.origin)
        origin_key = normalize_origin(request.origin or intent.origin)
        start = request.start_date or next_friday()
        nights = nights_for(request.duration_hours)

        shortlist = await self._shortlist(request, intent, origin_key)
        report = SearchReport()

        candidates: list[Candidate] = []
        degraded = False
        degraded_reason: str | None = None

        if self._settings.demo_mode:
            degraded_reason = "DEMO_MODE включён — данные не из живого поиска"
            degraded = True
        else:
            candidates = await self._gather_from_mcp(
                shortlist, origin_name, start, nights, report
            )
            if not candidates:
                degraded = True
                degraded_reason = (
                    "Туту не ответил — показываем заранее подготовленный образец"
                    if not self._travel.available
                    else "Живой поиск не дал вариантов — показываем образец"
                )

        if not candidates:
            candidates = self._gather_demo(shortlist, origin_key, origin_name, start, nights)

        picked = select_diverse(candidates, request, intent)
        scenarios = await self._build_scenarios(picked, request, intent, start)

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        data_origin = (
            DataOrigin.DEMO
            if all(s.data_origin is DataOrigin.DEMO for s in scenarios) and scenarios
            else DataOrigin.MCP
        )

        result = EscapeResult(
            id=uuid.uuid4().hex[:12],
            request=request,
            scenarios=scenarios,
            origin_city=origin_name,
            normalized_summary=intent.summary,
            conflicts=intent.conflicts,
            data_origin=data_origin,
            degraded=degraded,
            degraded_reason=degraded_reason,
            search_ms=elapsed_ms,
        )
        logger.info(
            "escape planned",
            extra={
                "escape_id": result.id,
                "scenarios": len(scenarios),
                "candidates": len(candidates),
                "mcp_calls": report.calls,
                "mcp_failures": report.failures,
                "ms": elapsed_ms,
                "origin": data_origin.value,
            },
        )
        return PlanOutcome(result=result, intent=intent, start_date=start)

    # ------------------------------------------------------------------
    # Stage: destination shortlist
    # ------------------------------------------------------------------

    async def _shortlist(
        self, request: EscapeRequest, intent: NormalizedIntent, origin_key: str
    ) -> list[tuple[Destination, TransportKind, float]]:
        """Decide which cities to ask Tutu about, and by which mode."""
        reachable = self._reachable(request, intent, origin_key)
        if not reachable:
            # Nothing fits the time budget: fall back to the closest options so
            # the user gets an honest "too tight" answer instead of a blank page.
            reachable = self._reachable(request, intent, origin_key, relax=True)

        ranked = sorted(
            reachable,
            key=lambda item: self._shortlist_score(item[0], request, intent),
            reverse=True,
        )
        chosen = ranked[:SHORTLIST_SIZE]

        # Guarantee that the UNEXPECTED card has something to work with.
        novel = [item for item in ranked if item[0].novelty >= 70]
        for item in novel[:2]:
            if item not in chosen:
                chosen.append(item)

        chosen = await self._llm_reorder(chosen, ranked, request, intent)
        logger.info(
            "shortlist built",
            extra={"cities": ",".join(d.name for d, _, _ in chosen) or "none"},
        )
        return chosen[: SHORTLIST_SIZE + 2]

    def _reachable(
        self,
        request: EscapeRequest,
        intent: NormalizedIntent,
        origin_key: str,
        *,
        relax: bool = False,
    ) -> list[tuple[Destination, TransportKind, float]]:
        """Destinations whose round trip leaves enough time to be there."""
        budget_hours = request.duration_hours
        max_share = 0.55 if request.duration_hours > 24 else 0.35
        if relax:
            max_share = 0.75

        supported = set(self._travel.supported_transport()) or set(TransportKind)
        result: list[tuple[Destination, TransportKind, float]] = []

        for destination in DESTINATIONS:
            reach = destination.reach_from(origin_key)
            if not reach:
                continue
            best: tuple[TransportKind, float] | None = None
            for kind, hours in reach.items():
                if kind in intent.avoided_transport:
                    continue
                if kind not in supported and not self._settings.demo_mode:
                    continue
                if hours * 2 > budget_hours * max_share:
                    continue
                preference_bonus = -0.5 if kind in intent.preferred_transport else 0.0
                if best is None or hours + preference_bonus < best[1]:
                    best = (kind, hours)
            if best:
                result.append((destination, best[0], best[1]))
        return result

    def _shortlist_score(
        self, destination: Destination, request: EscapeRequest, intent: NormalizedIntent
    ) -> float:
        """Cheap pre-MCP ranking: mood, tags, named places, novelty."""
        score = 0.0
        wanted = set(request.moods) | set(intent.moods)
        if wanted:
            score += 3.0 * len(wanted & set(destination.moods)) / len(wanted)
        if intent.tags:
            from app.utils.text import overlap_score

            score += 3.0 * overlap_score(" ".join(intent.tags), destination.tags)
        if destination.name in intent.named_places:
            score += 4.0
        if intent.wants_sea and "море" in destination.tags:
            score += 2.0
        if intent.wants_warmth and "тепло" in destination.tags:
            score += 1.5
        if intent.wants_cheap and "недорого" in destination.tags:
            score += 1.0
        if intent.no_car and "без машины" in destination.tags:
            score += 1.0
        score += destination.novelty / 100
        return score

    async def _llm_reorder(
        self,
        chosen: list[tuple[Destination, TransportKind, float]],
        ranked: list[tuple[Destination, TransportKind, float]],
        request: EscapeRequest,
        intent: NormalizedIntent,
    ) -> list[tuple[Destination, TransportKind, float]]:
        """Let the model pick from the *allowed* list — never outside it."""
        if self._llm is None or not self._llm.enabled or not ranked:
            return chosen

        allowed = {d.name: (d, k, h) for d, k, h in ranked}
        payload = {
            "origin": intent.origin,
            "budget_rub": request.budget_rub,
            "duration_hours": request.duration_hours,
            "moods": [m.value for m in request.moods],
            "tags": intent.tags,
            "allowed_cities": [
                {
                    "city": d.name,
                    "region": d.region,
                    "tags": list(d.tags),
                    "novelty": d.novelty,
                    "hours_one_way": round(h, 1),
                }
                for d, _, h in ranked[:16]
            ],
        }
        shortlist = await self._llm.ask_model(
            system=CANDIDATE_EVALUATION,
            user=json.dumps(payload, ensure_ascii=False),
            schema=DestinationShortlist,
            temperature=0.6,
        )
        if shortlist is None or not shortlist.ideas:
            return chosen

        reordered: list[tuple[Destination, TransportKind, float]] = []
        for idea in shortlist.ideas:
            entry = allowed.get(idea.city) or (
                allowed.get(found.name) if (found := find_destination(idea.city)) else None
            )
            if entry and entry not in reordered:
                reordered.append(entry)
        for entry in chosen:
            if entry not in reordered:
                reordered.append(entry)
        return reordered

    # ------------------------------------------------------------------
    # Stage: candidate generation
    # ------------------------------------------------------------------

    async def _gather_from_mcp(
        self,
        shortlist: list[tuple[Destination, TransportKind, float]],
        origin_name: str,
        start: date,
        nights: int,
        report: SearchReport,
    ) -> list[Candidate]:
        """Ask Tutu about every shortlisted city, in bounded parallel."""
        if not await self._travel.connect():
            return []

        semaphore = asyncio.Semaphore(MAX_PARALLEL_DESTINATIONS)

        async def one(entry: tuple[Destination, TransportKind, float]) -> Candidate | None:
            async with semaphore:
                return await self._candidate_for(entry, origin_name, start, nights, report)

        results = await asyncio.gather(
            *(one(entry) for entry in shortlist), return_exceptions=True
        )
        candidates: list[Candidate] = []
        for item in results:
            if isinstance(item, Exception):
                logger.warning("candidate build failed", extra={"error": str(item)})
                continue
            if item is not None:
                candidates.append(item)
        return candidates

    async def _candidate_for(
        self,
        entry: tuple[Destination, TransportKind, float],
        origin_name: str,
        start: date,
        nights: int,
        report: SearchReport,
    ) -> Candidate | None:
        """Build one candidate from live MCP data, or nothing at all."""
        destination, kind, _hours = entry
        back_date = start + timedelta(days=max(nights, 1))

        outbound_task = self._travel.search_transport(
            origin=origin_name,
            destination=destination.name,
            when=start,
            kinds=[kind],
            limit=4,
            report=report,
        )
        inbound_task = self._travel.search_transport(
            origin=destination.name,
            destination=origin_name,
            when=back_date,
            kinds=[kind],
            limit=4,
            report=report,
        )
        hotels_task = self._travel.search_hotels(
            city=destination.name,
            check_in=start,
            nights=nights,
            limit=4,
            report=report,
        )
        outbound, inbound, hotels = await asyncio.gather(
            outbound_task, inbound_task, hotels_task
        )
        if not outbound:
            return None

        best_out = _cheapest(outbound)
        best_back = _cheapest(inbound) if inbound else None
        hotel = _best_hotel(hotels)

        candidate = Candidate(
            destination=destination,
            outbound=best_out,
            inbound=best_back,
            hotel=hotel,
            nights=nights,
            origin=origin_name,
            data_origin=DataOrigin.MCP,
        )
        if best_back is None and nights >= 0:
            candidate.note("обратный билет не нашёлся — цена только в одну сторону")
        if nights > 0 and hotel is None:
            candidate.note("проживание не подтвердилось в Туту")
        return candidate

    def _gather_demo(
        self,
        shortlist: list[tuple[Destination, TransportKind, float]],
        origin_key: str,
        origin_name: str,
        start: date,
        nights: int,
    ) -> list[Candidate]:
        """Offline candidates, explicitly labelled as demo."""
        return [
            demo_candidate(destination, origin_key, origin_name, kind, hours, start, nights)
            for destination, kind, hours in shortlist
        ]

    # ------------------------------------------------------------------
    # Stage: scenarios
    # ------------------------------------------------------------------

    async def _build_scenarios(
        self,
        picked: list[ScoredCandidate],
        request: EscapeRequest,
        intent: NormalizedIntent,
        start: date,
    ) -> list[EscapeScenario]:
        """Turn three scored candidates into three finished cards."""
        return list(
            await asyncio.gather(
                *(
                    self.build_scenario(item, request, intent, start)
                    for item in picked
                )
            )
        )

    async def build_scenario(
        self,
        scored: ScoredCandidate,
        request: EscapeRequest,
        intent: NormalizedIntent,
        start: date,
        *,
        scenario_id: str | None = None,
    ) -> EscapeScenario:
        """One card: real numbers from MCP, words from the narrator."""
        candidate = scored.candidate
        copy = await write_copy(candidate, request, intent, scored.kind, self._llm)
        itinerary = build_itinerary(candidate, copy, scored.kind, start)

        compromises = list(intent.conflicts)
        compromises.extend(note for note in scored.score.notes if note not in compromises)

        return EscapeScenario(
            id=scenario_id or f"{scored.kind.value}_{uuid.uuid4().hex[:8]}",
            kind=scored.kind,
            title=SCENARIO_TITLES[scored.kind],
            destination=candidate.destination.name,
            region=candidate.destination.region,
            tagline=copy.tagline,
            reasons=copy.reasons or ["подходит под запрос"],
            total_price_rub=candidate.total_price,
            duration_hours=request.duration_hours,
            nights=candidate.nights,
            transport=candidate.outbound,
            return_transport=candidate.inbound,
            hotel=candidate.hotel,
            itinerary=itinerary,
            score=scored.score,
            why_ai_picked=copy.why_ai_picked,
            compromises=compromises[:4],
            data_origin=candidate.data_origin,
            warnings=candidate.warnings,
        )


# ----------------------------------------------------------------------
# Selection helpers
# ----------------------------------------------------------------------


def _cheapest(options: list) -> object:
    """Cheapest option, preferring ones that actually have a price."""
    priced = [o for o in options if o.price_rub]
    pool = priced or options
    return min(pool, key=lambda o: (o.price_rub or 10**9, o.transfers))


def _best_hotel(hotels: list):
    """Cheap-but-decent: price first, rating as the tie-breaker."""
    if not hotels:
        return None
    priced = [h for h in hotels if h.price_per_night_rub]
    pool = priced or hotels
    return min(pool, key=lambda h: (h.price_per_night_rub or 10**9, -(h.rating or 0)))


def relax_request(request: EscapeRequest, parameter: str) -> tuple[EscapeRequest, str]:
    """Loosen exactly one constraint after an empty result.

    Returns the new request plus a human sentence describing what we changed,
    which the UI shows so the user always knows what was given up.
    """
    data = request.model_dump()
    if parameter == "budget":
        data["budget_rub"] = int(request.budget_rub * 1.4)
        message = f"Подняли бюджет до {data['budget_rub']:,} ₽".replace(",", " ")
    elif parameter == "time":
        data["duration_hours"] = min(336, int(request.duration_hours * 1.5))
        message = "Добавили времени на дорогу"
    elif parameter == "transport":
        message = "Разрешили любой транспорт, включая перелёты"
    elif parameter == "wish":
        data["wishes"] = request.wishes[:-1] if request.wishes else []
        dropped = request.wishes[-1] if request.wishes else ""
        message = f"Убрали пожелание «{dropped}»" if dropped else "Сняли ограничение по пожеланиям"
    else:
        message = "Ничего не меняли"
    return EscapeRequest.model_validate(data), message
