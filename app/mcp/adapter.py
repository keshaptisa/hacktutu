"""``TutuTravelClient`` — the only place that knows Tutu MCP exists.

Everything above this layer speaks domain objects. Everything below speaks
JSON-RPC. A per-call failure degrades that one search (empty list + a warning)
instead of taking down the whole request.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.core.config import Settings
from app.core.errors import EscapeError
from app.domain.models import DataOrigin, HotelOption, TransportKind, TransportOption
from app.mcp.catalog import Capability, ToolCatalog
from app.mcp.client import MCPClient
from app.mcp.normalize import find_records, to_hotel_option, to_transport_option

logger = logging.getLogger(__name__)

KIND_CAPABILITY: dict[TransportKind, Capability] = {
    TransportKind.TRAIN: Capability.SEARCH_TRAIN,
    TransportKind.PLANE: Capability.SEARCH_PLANE,
    TransportKind.BUS: Capability.SEARCH_BUS,
    TransportKind.SUBURBAN: Capability.SEARCH_SUBURBAN,
}


@dataclass
class SearchReport:
    """What actually happened during one MCP round — surfaced in the UI."""

    calls: int = 0
    failures: int = 0
    warnings: list[str] = field(default_factory=list)
    used_tools: list[str] = field(default_factory=list)

    def note(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    @property
    def all_failed(self) -> bool:
        return self.calls > 0 and self.failures == self.calls


class TutuTravelClient:
    """Travel-shaped facade over the Tutu MCP server."""

    def __init__(self, settings: Settings, client: MCPClient | None = None):
        self._settings = settings
        self._client = client or MCPClient(settings)
        self._catalog: ToolCatalog | None = None
        self._connect_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max(1, settings.mcp_max_parallel))
        self.available = False
        self.last_error: str | None = None

    # -- lifecycle -------------------------------------------------------

    async def connect(self) -> bool:
        """Discover the MCP tool catalog. Returns False if MCP is unusable."""
        if not self._settings.mcp_enabled:
            self.last_error = "MCP disabled by configuration"
            return False
        async with self._connect_lock:
            if self._catalog is not None:
                return self.available
            try:
                tools = await self._client.list_tools()
            except EscapeError as exc:
                self.last_error = str(exc)
                self.available = False
                logger.warning("mcp connect failed", extra={"error": str(exc)})
                return False
            self._catalog = ToolCatalog.from_tools(
                tools, overrides_json=self._settings.mcp_tool_map
            )
            self.available = bool(self._catalog.resolved)
            if not self.available:
                self.last_error = "no usable travel tools found in MCP catalog"
            return self.available

    async def aclose(self) -> None:
        await self._client.aclose()

    @property
    def catalog(self) -> ToolCatalog | None:
        return self._catalog

    def describe(self) -> dict[str, Any]:
        """Snapshot for the health endpoint and the docs."""
        return {
            "url": self._settings.mcp_url,
            "enabled": self._settings.mcp_enabled,
            "available": self.available,
            "server": self._client.server_info,
            "last_error": self.last_error,
            **(self._catalog.describe() if self._catalog else {"capabilities": {}}),
        }

    def supported_transport(self) -> list[TransportKind]:
        """Transport modes the connected server can actually search."""
        if not self._catalog:
            return []
        return [k for k, c in KIND_CAPABILITY.items() if self._catalog.has(c)]

    # -- searches --------------------------------------------------------

    async def search_transport(
        self,
        *,
        origin: str,
        destination: str,
        when: date,
        kinds: list[TransportKind],
        limit: int = 5,
        report: SearchReport | None = None,
    ) -> list[TransportOption]:
        """Search every requested mode in parallel and merge the results."""
        if not await self.connect() or self._catalog is None:
            return []
        report = report or SearchReport()

        tasks = [
            self._search_one_kind(
                kind=kind,
                origin=origin,
                destination=destination,
                when=when,
                limit=limit,
                report=report,
            )
            for kind in kinds
            if kind in KIND_CAPABILITY and self._catalog.has(KIND_CAPABILITY[kind])
        ]
        if not tasks:
            report.note(f"MCP не умеет искать этот транспорт до «{destination}»")
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        options: list[TransportOption] = []
        for item in results:
            if isinstance(item, Exception):
                report.failures += 1
                logger.warning("transport search failed", extra={"error": str(item)})
                continue
            options.extend(item)
        return options

    async def _search_one_kind(
        self,
        *,
        kind: TransportKind,
        origin: str,
        destination: str,
        when: date,
        limit: int,
        report: SearchReport,
    ) -> list[TransportOption]:
        assert self._catalog is not None
        bound = self._catalog.get(KIND_CAPABILITY[kind])
        if bound is None:
            return []

        arguments = bound.build_arguments(
            {
                "origin": origin,
                "destination": destination,
                "date": when.isoformat(),
                "adults": 1,
                "limit": limit,
            }
        )
        payload = await self._call(bound.tool.name, arguments, report)
        if payload is None:
            return []

        options: list[TransportOption] = []
        for record in find_records(payload)[: limit * 3]:
            option = to_transport_option(
                record, kind=kind, from_place=origin, to_place=destination
            )
            if option is not None:
                options.append(option)
        if not options:
            report.note(f"{kind.value}: MCP не вернул подходящих вариантов")
        return options[:limit]

    async def search_hotels(
        self,
        *,
        city: str,
        check_in: date,
        nights: int,
        limit: int = 5,
        report: SearchReport | None = None,
    ) -> list[HotelOption]:
        """Find places to sleep in one city."""
        if nights <= 0:
            return []
        if not await self.connect() or self._catalog is None:
            return []
        report = report or SearchReport()
        bound = self._catalog.get(Capability.SEARCH_HOTEL)
        if bound is None:
            report.note("MCP не отдаёт поиск отелей — сценарии собраны без проживания")
            return []

        check_out = date.fromordinal(check_in.toordinal() + max(nights, 1))
        arguments = bound.build_arguments(
            {
                "city": city,
                "destination": city,
                "query": city,
                "date": check_in.isoformat(),
                "return_date": check_out.isoformat(),
                "nights": nights,
                "adults": 1,
                "limit": limit,
            }
        )
        payload = await self._call(bound.tool.name, arguments, report)
        if payload is None:
            return []

        hotels: list[HotelOption] = []
        for record in find_records(payload)[: limit * 3]:
            hotel = to_hotel_option(record, city=city, nights=nights)
            if hotel is not None:
                hotels.append(hotel)
        return hotels[:limit]

    # -- plumbing --------------------------------------------------------

    async def _call(
        self, tool_name: str, arguments: dict[str, Any], report: SearchReport
    ) -> Any:
        """Call one tool, counting it in the report and swallowing its failure."""
        report.calls += 1
        if tool_name not in report.used_tools:
            report.used_tools.append(tool_name)
        try:
            async with self._semaphore:
                return await self._client.call_tool(tool_name, arguments)
        except EscapeError as exc:
            report.failures += 1
            self.last_error = str(exc)
            report.note("Туту ответил не на все запросы — показываем то, что нашли")
            logger.warning(
                "mcp tool call failed", extra={"tool": tool_name, "error": str(exc)}
            )
            return None
        except Exception as exc:  # pragma: no cover - unexpected client bug
            report.failures += 1
            logger.exception("unexpected mcp failure", extra={"tool": tool_name})
            self.last_error = str(exc)
            return None
