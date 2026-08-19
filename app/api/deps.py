"""Composition root.

All objects with a lifetime longer than one request are built once here and
hung off ``app.state``. Routes ask for them through ``Depends``, so tests can
swap any piece (a fake MCP, a stub LLM) without touching route code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import Request

from app.ai.llm import LLMClient
from app.ai.planner import EscapePlanner
from app.ai.refiner import ScenarioRefiner
from app.core.config import Settings, get_settings
from app.mcp.adapter import TutuTravelClient
from app.services.email_service import EmailService
from app.services.store import EscapeStore
from app.services.trip_service import TripService

logger = logging.getLogger(__name__)


@dataclass
class Container:
    """Everything the application needs, assembled once."""

    settings: Settings
    travel: TutuTravelClient
    llm: LLMClient
    store: EscapeStore
    trips: TripService

    async def aclose(self) -> None:
        await self.travel.aclose()
        await self.llm.aclose()


def build_container(settings: Settings | None = None) -> Container:
    """Wire the object graph. Pure construction — no I/O happens here."""
    settings = settings or get_settings()

    travel = TutuTravelClient(settings)
    llm = LLMClient(settings)
    store = EscapeStore(
        ttl_minutes=settings.escape_ttl_minutes, max_items=settings.max_stored_escapes
    )
    planner = EscapePlanner(settings, travel, llm)
    refiner = ScenarioRefiner(settings, travel, llm)
    email = EmailService(settings, llm)
    trips = TripService(settings, planner, refiner, email, store)

    logger.info(
        "container built",
        extra={
            "demo_mode": settings.demo_mode,
            "llm": settings.llm_ready,
            "mcp": settings.mcp_enabled,
        },
    )
    return Container(settings=settings, travel=travel, llm=llm, store=store, trips=trips)


def get_container(request: Request) -> Container:
    """FastAPI dependency: the process-wide container."""
    return request.app.state.container


def get_trips(request: Request) -> TripService:
    """FastAPI dependency: the application service."""
    return request.app.state.container.trips
