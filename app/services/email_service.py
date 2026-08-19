"""Email delivery with an honest fallback.

If SMTP credentials exist, the letter is sent. If they do not — which is the
normal state on a hackathon laptop — the same HTML is written to disk and
returned as a preview URL. The user gets the itinerary either way and never
sees a stack trace.

Delivery runs in a worker thread: ``smtplib`` is blocking, and blocking the
event loop on a 1-core VPS is how a demo dies.
"""

from __future__ import annotations

import asyncio
import json
import logging
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.ai.llm import LLMClient
from app.ai.prompts import EMAIL_ITINERARY
from app.ai.schemas import EmailCopy
from app.core.config import Settings
from app.core.errors import EmailDeliveryError
from app.domain.models import DataOrigin, EscapeRequest, EscapeScenario
from app.utils.currency import format_rub
from app.utils.dates import format_date_range, humanize_minutes, plural_nights

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


@dataclass
class EmailOutcome:
    """What happened to the letter — surfaced verbatim in the UI."""

    delivered: bool
    mode: str  # "smtp" | "preview"
    message: str
    preview_url: str | None = None
    file_path: str | None = None


class EmailService:
    """Renders and delivers the itinerary email."""

    def __init__(self, settings: Settings, llm: LLMClient | None = None):
        self._settings = settings
        self._llm = llm
        self._env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=select_autoescape(["html"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    # -- rendering -------------------------------------------------------

    async def render(
        self, scenario: EscapeScenario, request: EscapeRequest, *, origin: str
    ) -> tuple[str, str]:
        """Return ``(subject, html)`` for a finished scenario."""
        copy = await self._copy(scenario, request)
        template = self._env.get_template("email.html")

        first_day = scenario.itinerary[0].date if scenario.itinerary else None
        last_day = scenario.itinerary[-1].date if scenario.itinerary else None
        dates = (
            format_date_range(first_day, last_day)
            if first_day and last_day
            else "даты уточняются"
        )

        transport_bits: list[str] = []
        if scenario.transport:
            label = {
                "train": "Поезд", "plane": "Самолёт", "bus": "Автобус",
                "suburban": "Электричка", "unknown": "Транспорт",
            }[scenario.transport.kind.value]
            transport_bits.append(f"{origin} → {scenario.destination}: {label}")
            if scenario.transport.total_duration_minutes:
                transport_bits.append(humanize_minutes(scenario.transport.total_duration_minutes))
        transport = " · ".join(transport_bits) or "уточняется"

        hotel = None
        if scenario.hotel:
            hotel = f"{scenario.hotel.name} · {plural_nights(scenario.nights)}"
            if scenario.hotel.total_price_rub:
                hotel += f" · {format_rub(scenario.hotel.total_price_rub)}"

        html = template.render(
            subject=copy.subject,
            scenario_title=scenario.title,
            destination=scenario.destination,
            intro=copy.intro,
            closing=copy.closing,
            dates=dates,
            duration=scenario.duration_label,
            transport=transport,
            hotel=hotel,
            price=format_rub(scenario.total_price_rub, approx=True),
            score=scenario.score.total,
            score_rows=" · ".join(f"{k} {v}" for k, v in scenario.score.as_rows),
            days=scenario.itinerary,
            links=scenario.purchase_links(),
            wishes=" · ".join(request.wishes),
            demo=scenario.data_origin is DataOrigin.DEMO,
        )
        return copy.subject, html

    async def _copy(self, scenario: EscapeScenario, request: EscapeRequest) -> EmailCopy:
        """Model-written paragraphs, with a solid deterministic fallback."""
        fallback = EmailCopy(
            subject=f"Твой побег: {scenario.destination}",
            intro=scenario.tagline
            or f"{scenario.destination} — тот вариант, который ты выбрал. Вот как он выглядит целиком.",
            closing="Если решишься — вот ссылки на оформление. Они ведут прямо на Туту.",
        )
        if self._llm is None or not self._llm.enabled:
            return fallback

        payload = {
            "city": scenario.destination,
            "scenario": scenario.kind.value,
            "nights": scenario.nights,
            "price_rub": scenario.total_price_rub,
            "wishes": request.wishes,
            "reasons": scenario.reasons,
        }
        generated = await self._llm.ask_model(
            system=EMAIL_ITINERARY,
            user=json.dumps(payload, ensure_ascii=False),
            schema=EmailCopy,
            temperature=0.6,
        )
        if generated is None:
            return fallback
        return EmailCopy(
            subject=generated.subject or fallback.subject,
            intro=generated.intro or fallback.intro,
            closing=generated.closing or fallback.closing,
        )

    # -- delivery --------------------------------------------------------

    async def send(
        self, *, to: str, subject: str, html: str, escape_id: str
    ) -> EmailOutcome:
        """Send via SMTP, or fall back to a saved preview. Never raises."""
        path = self._save(escape_id, html)

        if not self._settings.smtp_ready:
            logger.info("email fallback used", extra={"escape_id": escape_id})
            return EmailOutcome(
                delivered=False,
                mode="preview",
                message=(
                    "SMTP не настроен, поэтому письмо не отправлено. "
                    "Оно собрано целиком — открой предпросмотр."
                ),
                preview_url=f"/api/escape/{escape_id}/email/preview",
                file_path=str(path),
            )

        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._send_blocking, to, subject, html),
                timeout=self._settings.smtp_timeout_s + 5,
            )
        except asyncio.TimeoutError:
            logger.warning("smtp timeout", extra={"escape_id": escape_id})
            return EmailOutcome(
                delivered=False,
                mode="preview",
                message="Почтовый сервер не ответил вовремя. Письмо доступно в предпросмотре.",
                preview_url=f"/api/escape/{escape_id}/email/preview",
                file_path=str(path),
            )
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning("smtp failure", extra={"escape_id": escape_id, "error": str(exc)})
            return EmailOutcome(
                delivered=False,
                mode="preview",
                message="Письмо не ушло — почтовый сервер отказал. Открой предпросмотр.",
                preview_url=f"/api/escape/{escape_id}/email/preview",
                file_path=str(path),
            )

        logger.info("email sent", extra={"escape_id": escape_id})
        return EmailOutcome(
            delivered=True,
            mode="smtp",
            message=f"Письмо ушло на {to}.",
            preview_url=f"/api/escape/{escape_id}/email/preview",
            file_path=str(path),
        )

    def _send_blocking(self, to: str, subject: str, html: str) -> None:
        """Blocking SMTP call, executed off the event loop."""
        settings = self._settings
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings.smtp_from
        message["To"] = to
        message.set_content(
            "Твой маршрут ESCAPE. Для просмотра нужен почтовый клиент с поддержкой HTML."
        )
        message.add_alternative(html, subtype="html")

        context = ssl.create_default_context()
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port,
                timeout=settings.smtp_timeout_s, context=context,
            ) as server:
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(message)
            return

        with smtplib.SMTP(
            settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_s
        ) as server:
            if settings.smtp_starttls:
                server.starttls(context=context)
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)

    def _save(self, escape_id: str, html: str) -> Path:
        """Persist the rendered letter so the preview endpoint can serve it."""
        directory = Path(self._settings.email_outbox_dir)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = directory / f"escape-{escape_id}-{stamp}.html"
        path.write_text(html, encoding="utf-8")
        return path
