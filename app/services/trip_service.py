"""Application service — the only thing the API layer talks to.

Routes stay thin (parse, call, serialise) and every piece of orchestration lives
here, which is what keeps the HTTP layer swappable (a Telegram bot would reuse
this class untouched).
"""

from __future__ import annotations

import logging

from app.ai.planner import EscapePlanner, relax_request
from app.ai.refiner import ScenarioRefiner
from app.core.config import Settings
from app.core.errors import EscapeNotFoundError, NoResultsError
from app.domain.models import (
    EmailRequest,
    EscapeRequest,
    EscapeResult,
    EscapeScenario,
    RefinedEscape,
    RefinementRequest,
)
from app.services.email_service import EmailOutcome, EmailService
from app.services.store import EscapeSession, EscapeStore

logger = logging.getLogger(__name__)


class TripService:
    """Create, read, refine and deliver escapes."""

    def __init__(
        self,
        settings: Settings,
        planner: EscapePlanner,
        refiner: ScenarioRefiner,
        email: EmailService,
        store: EscapeStore,
    ):
        self._settings = settings
        self._planner = planner
        self._refiner = refiner
        self._email = email
        self._store = store

    # -- create ----------------------------------------------------------

    async def create(self, request: EscapeRequest) -> EscapeResult:
        """Run one search and remember it for the rest of the session."""
        outcome = await self._planner.plan(request)
        self._store.put(
            EscapeSession(
                result=outcome.result,
                intent=outcome.intent,
                start_date=outcome.start_date,
            )
        )
        return outcome.result

    async def relax(self, escape_id: str, parameter: str) -> EscapeResult:
        """Loosen one constraint and search again, keeping the audit trail."""
        session = self._session(escape_id)
        new_request, message = relax_request(session.result.request, parameter)
        outcome = await self._planner.plan(new_request)
        outcome.result.relaxations_applied = [
            *session.result.relaxations_applied,
            message,
        ]
        self._store.put(
            EscapeSession(
                result=outcome.result,
                intent=outcome.intent,
                start_date=outcome.start_date,
            )
        )
        logger.info(
            "constraint relaxed",
            extra={"escape_id": escape_id, "parameter": parameter, "new_id": outcome.result.id},
        )
        return outcome.result

    # -- read ------------------------------------------------------------

    def get(self, escape_id: str) -> EscapeResult:
        return self._session(escape_id).result

    def get_scenario(self, escape_id: str, scenario_id: str) -> EscapeScenario:
        session = self._session(escape_id)
        scenario = session.scenario(scenario_id)
        if scenario is None:
            raise EscapeNotFoundError(f"scenario {scenario_id} not found")
        return scenario

    # -- refine ----------------------------------------------------------

    async def refine(
        self, escape_id: str, scenario_id: str, refinement: RefinementRequest
    ) -> RefinedEscape:
        """Re-optimise one chosen scenario against a free-text note."""
        session = self._session(escape_id)
        scenario = session.scenario(scenario_id)
        if scenario is None:
            raise EscapeNotFoundError(f"scenario {scenario_id} not found")

        refined = await self._refiner.refine(
            scenario=scenario,
            request=session.result.request,
            intent=session.intent,
            refinement=refinement,
            start=session.start_date,
        )
        session.replace_scenario(refined.scenario)
        if refinement.budget_rub:
            session.result.request = session.result.request.model_copy(
                update={"budget_rub": refinement.budget_rub}
            )
        self._store.put(session)
        return refined

    # -- email -----------------------------------------------------------

    async def send_email(
        self, escape_id: str, scenario_id: str, payload: EmailRequest
    ) -> EmailOutcome:
        """Render the itinerary letter and try to deliver it."""
        session = self._session(escape_id)
        scenario = session.scenario(scenario_id)
        if scenario is None:
            raise EscapeNotFoundError(f"scenario {scenario_id} not found")

        subject, html = await self._email.render(
            scenario, session.result.request, origin=session.result.origin_city
        )
        session.email_html = html
        outcome = await self._email.send(
            to=payload.email, subject=subject, html=html, escape_id=escape_id
        )
        session.email_path = outcome.file_path
        self._store.put(session)
        return outcome

    def email_preview(self, escape_id: str) -> str:
        """The last rendered letter for this escape."""
        session = self._session(escape_id)
        if not session.email_html:
            raise EscapeNotFoundError("письмо для этого побега ещё не собрано")
        return session.email_html

    # -- internals -------------------------------------------------------

    def _session(self, escape_id: str) -> EscapeSession:
        session = self._store.get(escape_id)
        if session is None:
            raise EscapeNotFoundError(f"escape {escape_id} expired or unknown")
        return session

    @property
    def stored(self) -> int:
        return self._store.size()
