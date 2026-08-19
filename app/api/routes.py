"""HTTP API.

Routes parse, delegate and serialise. Business rules live in services; errors
are raised as :class:`EscapeError` subclasses and turned into clean JSON by the
handler registered in ``app.main``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.api.deps import Container, get_container, get_trips
from app.domain.models import (
    EmailRequest,
    EscapeRequest,
    EscapeResult,
    EscapeScenario,
    MOOD_LABELS,
    Mood,
    RefinedEscape,
    RefinementRequest,
    RelaxRequest,
)
from app.services.trip_service import TripService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["escape"])


class EmailResponse(BaseModel):
    """Outcome of an email attempt — never an error, always a next step."""

    delivered: bool
    mode: str
    message: str
    preview_url: str | None = None


class PurchaseItemResponse(BaseModel):
    """One real Tutu booking link for the basket page."""

    kind: str
    title: str
    label: str
    url: str


class PurchaseResponse(BaseModel):
    """All booking links we can honestly show for one chosen scenario."""

    escape_id: str
    scenario_id: str
    destination: str
    title: str
    total_price_rub: int
    items: list[PurchaseItemResponse]
    missing: list[str]


class MoodOption(BaseModel):
    """One mood chip on the first screen."""

    value: Mood
    label: str
    emoji: str


class MetaResponse(BaseModel):
    """Everything the frontend needs to render screen one."""

    app: str
    demo_mode: bool
    llm_enabled: bool
    mcp_enabled: bool
    default_origin: str
    budget_min: int
    budget_max: int
    duration_min_hours: int
    duration_max_hours: int
    moods: list[MoodOption]


MOOD_EMOJI = {
    Mood.SILENCE: "🌿",
    Mood.ENERGY: "🔥",
    Mood.ROMANCE: "❤️",
    Mood.SPONTANEITY: "🎲",
    Mood.NIGHTLIFE: "🌃",
    Mood.IMPRESSIONS: "🏛️",
}


@router.get("/meta", response_model=MetaResponse)
async def meta(container: Container = Depends(get_container)) -> MetaResponse:
    """Configuration for the first screen. Cheap, cacheable, no MCP call."""
    settings = container.settings
    return MetaResponse(
        app=settings.app_name,
        demo_mode=settings.demo_mode,
        llm_enabled=settings.llm_ready,
        mcp_enabled=settings.mcp_enabled,
        default_origin=settings.default_origin,
        budget_min=5_000,
        budget_max=500_000,
        duration_min_hours=6,
        duration_max_hours=168,
        moods=[
            MoodOption(value=mood, label=MOOD_LABELS[mood], emoji=MOOD_EMOJI[mood])
            for mood in Mood
        ],
    )


@router.get("/health")
async def health(container: Container = Depends(get_container)) -> dict:
    """Liveness plus a full picture of what MCP actually gave us."""
    await container.travel.connect()
    return {
        "status": "ok",
        "demo_mode": container.settings.demo_mode,
        "escapes_in_memory": container.trips.stored,
        "llm": {
            "enabled": container.settings.llm_ready,
            "provider": container.settings.llm_provider,
            "model": container.settings.llm_model if container.settings.llm_ready else None,
            "calls": container.llm.calls,
            "failures": container.llm.failures,
        },
        "mcp": container.travel.describe(),
    }


@router.post("/escape", response_model=EscapeResult)
async def create_escape(
    request: EscapeRequest, trips: TripService = Depends(get_trips)
) -> EscapeResult:
    """СБЕЖАТЬ — run the pipeline and return three scenarios."""
    return await trips.create(request)


@router.get("/escape/{escape_id}", response_model=EscapeResult)
async def get_escape(
    escape_id: str, trips: TripService = Depends(get_trips)
) -> EscapeResult:
    """Re-read a search — used on refresh and deep links."""
    return trips.get(escape_id)


@router.post("/escape/{escape_id}/relax", response_model=EscapeResult)
async def relax_escape(
    escape_id: str, payload: RelaxRequest, trips: TripService = Depends(get_trips)
) -> EscapeResult:
    """ОСЛАБИТЬ ОГРАНИЧЕНИЯ — loosen exactly one constraint and search again."""
    return await trips.relax(escape_id, payload.parameter)


@router.get("/escape/{escape_id}/scenario/{scenario_id}", response_model=EscapeScenario)
async def get_scenario(
    escape_id: str, scenario_id: str, trips: TripService = Depends(get_trips)
) -> EscapeScenario:
    """The detail page behind ПОСМОТРЕТЬ →."""
    return trips.get_scenario(escape_id, scenario_id)


@router.get(
    "/escape/{escape_id}/scenario/{scenario_id}/purchase",
    response_model=PurchaseResponse,
)
async def get_purchase_links(
    escape_id: str, scenario_id: str, trips: TripService = Depends(get_trips)
) -> PurchaseResponse:
    """Real Tutu booking links for the chosen scenario, if MCP returned them."""
    scenario = trips.get_scenario(escape_id, scenario_id)
    items: list[PurchaseItemResponse] = []
    missing: list[str] = []

    if scenario.transport and scenario.transport.purchase:
        items.append(
            PurchaseItemResponse(
                kind="outbound",
                title="Туда",
                label=scenario.transport.purchase.label,
                url=scenario.transport.purchase.url,
            )
        )
    else:
        missing.append("Поездка туда")

    if scenario.return_transport and scenario.return_transport.purchase:
        items.append(
            PurchaseItemResponse(
                kind="return",
                title="Обратно",
                label=scenario.return_transport.purchase.label,
                url=scenario.return_transport.purchase.url,
            )
        )
    else:
        missing.append("Поездка обратно")

    if scenario.hotel and scenario.hotel.purchase:
        items.append(
            PurchaseItemResponse(
                kind="hotel",
                title="Отель",
                label=scenario.hotel.purchase.label,
                url=scenario.hotel.purchase.url,
            )
        )
    elif scenario.hotel:
        missing.append("Отель")

    return PurchaseResponse(
        escape_id=escape_id,
        scenario_id=scenario_id,
        destination=scenario.destination,
        title=scenario.title,
        total_price_rub=scenario.total_price_rub,
        items=items,
        missing=missing,
    )


@router.post(
    "/escape/{escape_id}/scenario/{scenario_id}/refine", response_model=RefinedEscape
)
async def refine_scenario(
    escape_id: str,
    scenario_id: str,
    payload: RefinementRequest,
    trips: TripService = Depends(get_trips),
) -> RefinedEscape:
    """ДОПИЛИТЬ МОЙ ПОБЕГ — re-optimise the chosen scenario in place."""
    return await trips.refine(escape_id, scenario_id, payload)


@router.post(
    "/escape/{escape_id}/scenario/{scenario_id}/email", response_model=EmailResponse
)
async def email_scenario(
    escape_id: str,
    scenario_id: str,
    payload: EmailRequest,
    trips: TripService = Depends(get_trips),
) -> EmailResponse:
    """ОТПРАВИТЬ МНЕ НА ПОЧТУ — send, or fall back to a saved preview."""
    outcome = await trips.send_email(escape_id, scenario_id, payload)
    return EmailResponse(
        delivered=outcome.delivered,
        mode=outcome.mode,
        message=outcome.message,
        preview_url=outcome.preview_url,
    )


@router.get("/escape/{escape_id}/email/preview", response_class=HTMLResponse)
async def email_preview(
    escape_id: str, trips: TripService = Depends(get_trips)
) -> HTMLResponse:
    """Render the last generated letter in the browser."""
    return HTMLResponse(trips.email_preview(escape_id))
