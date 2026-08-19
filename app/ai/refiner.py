"""'УТОЧНИТЬ ПЛАН' — re-optimise one already-chosen scenario.

This is deliberately *not* a new search. The user picked a city; we keep it
unless they explicitly ask otherwise, and only re-query the parts their note
touches. That is the difference between a product and a chat: the context is
carried for them.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from app.ai.llm import LLMClient
from app.ai.narrator import build_itinerary, write_copy
from app.ai.prompts import REFINEMENT
from app.ai.schemas import NormalizedIntent, RefinementPlan
from app.ai.scorer import ScoredCandidate, score_candidate
from app.core.config import Settings
from app.domain.candidate import Candidate
from app.domain.destinations import find_destination
from app.domain.models import (
    DataOrigin,
    EscapeRequest,
    EscapeScenario,
    HotelOption,
    RefinedEscape,
    RefinementChange,
    RefinementRequest,
    ScenarioKind,
    TransportKind,
    TransportOption,
)
from app.mcp.adapter import SearchReport, TutuTravelClient
from app.services.demo_data import demo_hotel, demo_transport_options
from app.utils import text as T
from app.utils.currency import format_rub, parse_rub
from app.utils.dates import humanize_minutes, plural_nights

logger = logging.getLogger(__name__)

_CENTER_WORDS = ("центр", "исторический центр", "в центре", "рядом с центром")
_QUALITY_WORDS = ("красивый отель", "хороший отель", "получше", "поприличнее", "звезд")
_SLOWER_WORDS = ("медленнее", "спокойнее", "не хочу много ходить", "меньше ходить", "свободного времени", "больше времени")
_DENSER_WORDS = ("плотнее", "больше активностей", "насыщеннее", "успеть больше")
_NIGHT_OK_WORDS = ("ночной поезд", "ночью", "чтобы поспать в поезде")


def parse_refinement_heuristic(note: str) -> RefinementPlan:
    """Rule-based reading of the refinement note. Always runs, never fails."""
    blob = T.normalize(note)
    preferred, avoided = T.infer_transport([note])

    plan = RefinementPlan(
        avoid_night_transport=T.mentions_any([note], T.DAYTIME_WORDS),
        prefer_night_transport=any(word in blob for word in _NIGHT_OK_WORDS),
        preferred_transport=sorted(preferred, key=lambda k: k.value),
        hotel_near_center=any(word in blob for word in _CENTER_WORDS),
        hotel_quality_up=any(word in blob for word in _QUALITY_WORDS),
        new_budget_rub=parse_rub(note),
        slower_pace=any(word in blob for word in _SLOWER_WORDS),
        denser_pace=any(word in blob for word in _DENSER_WORDS),
        less_walking="не хочу много ходить" in blob or "меньше ходить" in blob,
        more_free_time="свободн" in blob,
        keep_destination=True,
        note=T.truncate(note, 200),
    )
    if plan.avoid_night_transport:
        plan.prefer_night_transport = False
    return plan


async def parse_refinement(note: str, llm: LLMClient | None) -> RefinementPlan:
    """Stage 5: read the free-text refinement note.

    The model is the primary reader here too — free text like "хочу дневной
    поезд и отель в центре" is exactly what it is good at. The rule-based
    reading only kicks in when there is no working model.
    """
    if llm is not None and llm.enabled:
        parsed = await llm.ask_model(
            system=REFINEMENT,
            user=json.dumps({"note": note}, ensure_ascii=False),
            schema=RefinementPlan,
            temperature=0.2,
        )
        if parsed is not None:
            if not parsed.note:
                parsed.note = T.truncate(note, 200)
            if parsed.avoid_night_transport:
                parsed.prefer_night_transport = False
            return parsed
        logger.warning("llm refinement parsing failed — falling back to rules")

    return parse_refinement_heuristic(note)


class ScenarioRefiner:
    """Applies a :class:`RefinementPlan` to an existing scenario."""

    def __init__(
        self,
        settings: Settings,
        travel: TutuTravelClient,
        llm: LLMClient | None = None,
    ):
        self._settings = settings
        self._travel = travel
        self._llm = llm

    async def refine(
        self,
        *,
        scenario: EscapeScenario,
        request: EscapeRequest,
        intent: NormalizedIntent,
        refinement: RefinementRequest,
        start: date,
    ) -> RefinedEscape:
        """Re-optimise one scenario against a free-text note."""
        plan = await parse_refinement(refinement.note, self._llm)
        if refinement.budget_rub:
            plan.new_budget_rub = refinement.budget_rub

        destination = find_destination(scenario.destination)
        if destination is None:
            return RefinedEscape(
                escape_id=scenario.id,
                scenario=scenario,
                unmet=["Не удалось перестроить этот маршрут — направление вне каталога"],
                note=plan.note,
            )

        new_request = request.model_copy(
            update={"budget_rub": plan.new_budget_rub or request.budget_rub}
        )
        report = SearchReport()
        is_demo = scenario.data_origin is DataOrigin.DEMO or self._settings.demo_mode

        kinds = plan.preferred_transport or [scenario.transport.kind if scenario.transport else TransportKind.TRAIN]
        original_kind = scenario.transport.kind if scenario.transport else None
        sane_kinds, rejected = _sane_transport_kinds(destination, kinds, request.duration_hours)
        if not sane_kinds:
            # The requested mode would blow the trip up (e.g. a 34-hour train to
            # a city normally reached by plane) — keep what worked and say so,
            # instead of silently multiplying the price by four.
            sane_kinds = [original_kind] if original_kind else [TransportKind.TRAIN]
            if rejected:
                plan.unmet = list(plan.unmet) + [
                    f"{TRANSPORT_RU.get(rejected[0], 'этот транспорт')} до {destination.name} "
                    "займёт непропорционально много времени — оставили прежний вариант"
                ]
        kinds = sane_kinds
        outbound = await self._pick_transport(
            destination_name=destination.name,
            origin=scenario.transport.from_place if scenario.transport else "Москва",
            when=start,
            kinds=kinds,
            plan=plan,
            report=report,
            is_demo=is_demo,
            destination=destination,
            outbound=True,
        )
        back_date = start + timedelta(days=max(scenario.nights, 1))
        inbound = await self._pick_transport(
            destination_name=scenario.transport.from_place if scenario.transport else "Москва",
            origin=destination.name,
            when=back_date,
            kinds=kinds,
            plan=plan,
            report=report,
            is_demo=is_demo,
            destination=destination,
            outbound=False,
        )
        hotel = await self._pick_hotel(
            destination=destination,
            nights=scenario.nights,
            check_in=start,
            plan=plan,
            budget=new_request.budget_rub,
            report=report,
            is_demo=is_demo,
        )

        candidate = Candidate(
            destination=destination,
            outbound=outbound or scenario.transport,
            inbound=inbound or scenario.return_transport,
            hotel=hotel or scenario.hotel,
            nights=scenario.nights,
            origin=scenario.transport.from_place if scenario.transport else "Москва",
            data_origin=DataOrigin.DEMO if is_demo else DataOrigin.MCP,
        )
        if candidate.outbound is None:
            return RefinedEscape(
                escape_id=scenario.id,
                scenario=scenario,
                unmet=["Не удалось найти новый вариант — оставили прежний"],
                note=plan.note,
            )

        kind = _pace_kind(scenario.kind, plan)
        score = score_candidate(candidate, new_request, intent, kind)
        scored = ScoredCandidate(candidate=candidate, kind=scenario.kind, score=score)

        copy = await write_copy(candidate, new_request, intent, scenario.kind, self._llm)
        itinerary = build_itinerary(candidate, copy, kind, start)

        updated = scenario.model_copy(
            update={
                "transport": candidate.outbound,
                "return_transport": candidate.inbound,
                "hotel": candidate.hotel,
                "total_price_rub": candidate.total_price,
                "itinerary": itinerary,
                "score": score,
                "tagline": copy.tagline or scenario.tagline,
                "reasons": copy.reasons or scenario.reasons,
                "why_ai_picked": copy.why_ai_picked or scenario.why_ai_picked,
                "warnings": candidate.warnings,
            }
        )
        changes = _diff(scenario, updated, plan)
        unmet = list(plan.unmet)
        unmet.extend(_unmet_checks(plan, updated))

        logger.info(
            "scenario refined",
            extra={
                "scenario": scenario.id,
                "changes": len(changes),
                "mcp_calls": report.calls,
            },
        )
        return RefinedEscape(
            escape_id=scenario.id,
            scenario=updated,
            changes=changes,
            unmet=unmet[:4],
            note=plan.note,
        )

    # -- pieces ----------------------------------------------------------

    async def _pick_transport(
        self,
        *,
        destination_name: str,
        origin: str,
        when: date,
        kinds: list[TransportKind],
        plan: RefinementPlan,
        report: SearchReport,
        is_demo: bool,
        destination,
        outbound: bool,
    ) -> TransportOption | None:
        """Search again with the note's transport constraints applied."""
        if is_demo:
            options = []
            for kind in kinds:
                hours = _reach_hours(destination, kind)
                options.extend(
                    demo_transport_options(
                        destination,
                        origin if outbound else destination_name,
                        kind,
                        hours,
                        when,
                        outbound=outbound,
                    )
                )
        else:
            options = await self._travel.search_transport(
                origin=origin,
                destination=destination_name,
                when=when,
                kinds=kinds,
                limit=6,
                report=report,
            )
        if not options:
            return None

        def rank(option: TransportOption) -> tuple[int, int]:
            penalty = 0
            if plan.avoid_night_transport and option.is_night_ride:
                penalty += 100
            if plan.prefer_night_transport and not option.is_night_ride:
                penalty += 40
            penalty += option.transfers * 20
            return penalty, option.price_rub or 10**9

        return min(options, key=rank)

    async def _pick_hotel(
        self,
        *,
        destination,
        nights: int,
        check_in: date,
        plan: RefinementPlan,
        budget: int,
        report: SearchReport,
        is_demo: bool,
    ) -> HotelOption | None:
        """Re-pick a hotel when the note is about where or how you sleep."""
        if nights <= 0 or not plan.touches_hotel:
            return None
        if is_demo:
            hotels = [demo_hotel(destination, nights, index=i) for i in range(4)]
            hotels = [h for h in hotels if h is not None]
        else:
            hotels = await self._travel.search_hotels(
                city=destination.name,
                check_in=check_in,
                nights=nights,
                limit=6,
                report=report,
            )
        if not hotels:
            return None

        cap = int(budget * 0.5)

        def rank(hotel: HotelOption) -> tuple[float, float]:
            distance = hotel.distance_to_center_km
            central = distance if distance is not None else 3.0
            if plan.hotel_near_center and hotel.district and "центр" in hotel.district.lower():
                central -= 1.0
            quality = -(hotel.rating or 0) - (hotel.stars or 0)
            over_budget = max(0, (hotel.total_price_rub or 0) - cap) / 1000
            if plan.hotel_quality_up:
                return (quality + over_budget, central)
            return (central + over_budget, quality)

        return min(hotels, key=rank)


def _reach_hours(destination, kind: TransportKind) -> float:
    """One-way hours for a mode, across whichever origin the catalog knows."""
    for reach in destination.reach.values():
        if kind in reach:
            return reach[kind]
    return 4.0


TRANSPORT_RU = {
    TransportKind.TRAIN: "поезд",
    TransportKind.PLANE: "самолёт",
    TransportKind.BUS: "автобус",
    TransportKind.SUBURBAN: "электричка",
}


def _sane_transport_kinds(
    destination, kinds: list[TransportKind], duration_hours: int
) -> tuple[list[TransportKind], list[TransportKind]]:
    """Drop modes whose one-way reach would eat the whole trip.

    A refinement note can ask for a mode that technically exists for a
    destination (a two-day train to somewhere normally reached by plane) but
    would leave no time for the destination itself. We keep such a mode only
    if it still fits in a sane share of the trip; otherwise it is rejected and
    reported back as an unmet wish rather than silently applied.
    """
    accepted: list[TransportKind] = []
    rejected: list[TransportKind] = []
    for kind in kinds:
        hours = None
        for reach in destination.reach.values():
            if kind in reach:
                hours = reach[kind]
                break
        if hours is None:
            rejected.append(kind)
            continue
        if hours * 2 > duration_hours * 0.65:
            rejected.append(kind)
            continue
        accepted.append(kind)
    return accepted, rejected


def _pace_kind(original: ScenarioKind, plan: RefinementPlan) -> ScenarioKind:
    """Which timeline density to rebuild with."""
    if plan.slower_pace or plan.less_walking or plan.more_free_time:
        return ScenarioKind.SILENCE
    if plan.denser_pace:
        return ScenarioKind.MADNESS
    return original


def _diff(
    before: EscapeScenario, after: EscapeScenario, plan: RefinementPlan
) -> list[RefinementChange]:
    """Build the 'Было / Стало' rows the final screen shows."""
    changes: list[RefinementChange] = []

    if before.total_price_rub != after.total_price_rub:
        changes.append(
            RefinementChange(
                label="Стоимость",
                before=format_rub(before.total_price_rub),
                after=format_rub(after.total_price_rub),
            )
        )
    if before.transport and after.transport:
        old_time = _departure_label(before.transport)
        new_time = _departure_label(after.transport)
        if old_time != new_time:
            changes.append(
                RefinementChange(label="Отправление", before=old_time, after=new_time)
            )
        if before.transport.total_duration_minutes != after.transport.total_duration_minutes:
            changes.append(
                RefinementChange(
                    label="Время в пути",
                    before=humanize_minutes(before.transport.total_duration_minutes),
                    after=humanize_minutes(after.transport.total_duration_minutes),
                )
            )
    if _hotel_signature(before.hotel) != _hotel_signature(after.hotel):
        changes.append(
            RefinementChange(
                label="Отель",
                before=before.hotel.name if before.hotel else "не выбран",
                after=after.hotel.name if after.hotel else "не выбран",
            )
        )
    if before.score.total != after.score.total:
        changes.append(
            RefinementChange(
                label="ESCAPE SCORE",
                before=str(before.score.total),
                after=str(after.score.total),
            )
        )
    if plan.slower_pace or plan.more_free_time:
        changes.append(
            RefinementChange(
                label="Ритм", before="как было", after="больше свободного времени"
            )
        )
    elif plan.denser_pace:
        changes.append(
            RefinementChange(label="Ритм", before="как было", after="плотнее программа")
        )
    if not changes:
        changes.append(
            RefinementChange(
                label="Маршрут",
                before=before.destination,
                after=f"{after.destination} · {plural_nights(after.nights)}",
            )
        )
    return changes


def _unmet_checks(plan: RefinementPlan, scenario: EscapeScenario) -> list[str]:
    """Say plainly which asks we could not satisfy."""
    unmet: list[str] = []
    if plan.avoid_night_transport and scenario.transport and scenario.transport.is_night_ride:
        unmet.append("Дневного выезда в этот день не нашлось — оставили ближайший вариант")
    if plan.new_budget_rub and scenario.total_price_rub > plan.new_budget_rub:
        unmet.append("Уложиться в новый бюджет не вышло — вариант дороже на "
                     f"{format_rub(scenario.total_price_rub - plan.new_budget_rub)}")
    if plan.hotel_near_center and scenario.hotel and scenario.hotel.distance_to_center_km:
        if scenario.hotel.distance_to_center_km > 2.5:
            unmet.append("Ближе к центру свободных номеров не нашлось")
    return unmet


def _departure_label(option: TransportOption) -> str:
    """'18:40' or a graceful placeholder."""
    if option.segments and option.segments[0].departure:
        return option.segments[0].departure.strftime("%H:%M")
    return "время уточняется"


def _hotel_signature(hotel: HotelOption | None) -> tuple[str | None, int | None, str | None, float | None, int | None, float | None] | None:
    """Meaningful hotel identity for refine diffs, ignoring unstable raw ids."""
    if hotel is None:
        return None
    return (
        hotel.name,
        hotel.price_per_night_rub,
        hotel.district,
        hotel.distance_to_center_km,
        hotel.stars,
        hotel.rating,
    )
