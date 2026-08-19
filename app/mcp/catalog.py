"""Capability discovery for Tutu MCP.

The brief is explicit: *do not invent MCP tool names*. So we don't. At startup
ESCAPE calls ``tools/list`` and classifies whatever the server advertises into
the capabilities the product needs, using the server's own names, descriptions
and JSON schemas.

Two escape hatches keep this honest:

* ``MCP_TOOL_MAP`` — a JSON env override, e.g.
  ``{"search_train": "tutu_trains_search"}``, wins over any guess;
* ``scripts/discover_mcp.py`` — prints the real catalog so a human can verify
  what got matched.

If a capability cannot be matched, it is simply reported as missing and the
product degrades gracefully instead of calling something that may not exist.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from app.mcp.client import MCPTool

logger = logging.getLogger(__name__)


class Capability(str, Enum):
    """What ESCAPE needs from a travel MCP, expressed product-side."""

    SEARCH_TRAIN = "search_train"
    SEARCH_PLANE = "search_plane"
    SEARCH_BUS = "search_bus"
    SEARCH_SUBURBAN = "search_suburban"
    SEARCH_HOTEL = "search_hotel"
    HOTEL_REVIEWS = "hotel_reviews"
    RESOLVE_PLACE = "resolve_place"


@dataclass(frozen=True)
class Signature:
    """Keyword weights that identify a capability in free-form tool metadata."""

    strong: tuple[str, ...]
    weak: tuple[str, ...] = ()
    veto: tuple[str, ...] = ()


SIGNATURES: dict[Capability, Signature] = {
    Capability.SEARCH_TRAIN: Signature(
        strong=("train", "railway", "поезд", "жд", "rzd"),
        weak=("ticket", "билет", "search", "поиск", "seat", "место"),
        veto=("suburban", "электрич", "пригород", "hotel", "отел"),
    ),
    Capability.SEARCH_PLANE: Signature(
        strong=("avia", "flight", "airline", "самол", "перелет", "перелёт", "рейс", "air"),
        weak=("ticket", "билет", "search", "поиск", "fare"),
        veto=("hotel", "отел", "airport transfer"),
    ),
    Capability.SEARCH_BUS: Signature(
        strong=("bus", "автобус", "coach"),
        weak=("ticket", "билет", "search", "поиск"),
        veto=("hotel", "отел"),
    ),
    Capability.SEARCH_SUBURBAN: Signature(
        strong=("suburban", "электрич", "пригород", "commuter"),
        weak=("schedule", "расписан", "search", "поиск"),
        veto=("hotel", "отел"),
    ),
    Capability.SEARCH_HOTEL: Signature(
        strong=("hotel", "отел", "accommodation", "гостиниц", "жиль", "stay", "room", "номер"),
        weak=("search", "поиск", "book", "availability", "review", "отзыв"),
        veto=(),
    ),
    Capability.HOTEL_REVIEWS: Signature(
        strong=("review", "отзыв", "rating", "рейтинг"),
        weak=("hotel", "отел"),
        veto=(),
    ),
    Capability.RESOLVE_PLACE: Signature(
        strong=("suggest", "autocomplete", "geo", "подсказ"),
        weak=("resolve", "lookup", "search", "place", "city", "станци", "город"),
        veto=("hotel", "отел", "ticket", "weather", "forecast", "погод"),
    ),
}


# Canonical argument names -> synonyms we look for in a tool's JSON schema.
ARG_SYNONYMS: dict[str, tuple[str, ...]] = {
    "origin": (
        "origin", "from", "from_id", "from_code", "departure", "departure_point",
        "source", "fromcity", "from_city", "from_station", "otkuda", "откуда",
        "departure_city", "origin_code", "point_from",
    ),
    "destination": (
        "destination", "to", "to_id", "to_code", "arrival", "arrival_point",
        "target", "tocity", "to_city", "to_station", "kuda", "куда",
        "arrival_city", "destination_code", "point_to",
    ),
    "date": (
        "date", "depart_date", "departure_date", "date_from", "start_date",
        "when", "outbound_date", "checkin", "check_in", "check_in_date", "дата",
    ),
    "return_date": (
        "return_date", "date_back", "back_date", "date_to", "end_date",
        "inbound_date", "checkout", "check_out", "check_out_date",
    ),
    "city": ("city", "location", "place", "region", "destination", "город", "query"),
    "adults": ("adults", "passengers", "pax", "guests", "adult_count", "persons"),
    "nights": ("nights", "night_count", "duration_nights"),
    "limit": ("limit", "count", "max_results", "size", "per_page", "top"),
    "query": ("query", "q", "text", "name", "search", "term", "input"),
}


@dataclass
class BoundTool:
    """A discovered tool plus the argument mapping we resolved for it."""

    capability: Capability
    tool: MCPTool
    arg_map: dict[str, str]
    confidence: float
    forced: bool = False

    def build_arguments(self, values: dict[str, Any]) -> dict[str, Any]:
        """Translate canonical values into this tool's own parameter names.

        Unknown canonical keys are dropped; required parameters the tool asks
        for but we cannot fill are left out so the server can complain clearly
        rather than us guessing a value.
        """
        arguments: dict[str, Any] = {}
        properties = self.tool.properties
        for canonical, value in values.items():
            if value is None:
                continue
            real = self.arg_map.get(canonical)
            if not real:
                continue
            arguments[real] = _coerce(value, properties.get(real, {}))
        return arguments

    @property
    def missing_required(self) -> list[str]:
        """Required params of the tool that our mapping cannot supply."""
        mapped = set(self.arg_map.values())
        return [name for name in self.tool.required if name not in mapped]


def _coerce(value: Any, schema: dict[str, Any]) -> Any:
    """Best-effort coercion to the type the tool's schema asks for."""
    expected = schema.get("type")
    try:
        if expected == "integer":
            return int(value)
        if expected == "number":
            return float(value)
        if expected == "string":
            return str(value)
        if expected == "boolean":
            return bool(value)
        if expected == "array" and not isinstance(value, list):
            return [value]
    except (TypeError, ValueError):
        return value
    return value


def _score(tool: MCPTool, signature: Signature) -> float:
    """How strongly a tool matches a capability signature (0..1+)."""
    text = tool.searchable_text
    if any(word in text for word in signature.veto):
        return 0.0
    strong_hits = sum(1 for word in signature.strong if word in text)
    if not strong_hits:
        return 0.0
    weak_hits = sum(1 for word in signature.weak if word in text)
    return min(1.0, 0.6 + 0.15 * (strong_hits - 1) + 0.1 * weak_hits)


def _map_arguments(tool: MCPTool) -> dict[str, str]:
    """Resolve canonical argument names against the tool's real schema."""
    properties = {name.lower(): name for name in tool.properties}
    resolved: dict[str, str] = {}
    used: set[str] = set()
    for canonical, synonyms in ARG_SYNONYMS.items():
        for synonym in synonyms:
            real = properties.get(synonym)
            if real and real not in used:
                resolved[canonical] = real
                used.add(real)
                break
        if canonical in resolved:
            continue
        # second pass: substring match (e.g. "fromStationCode")
        for lowered, real in properties.items():
            if real in used:
                continue
            if any(synonym in lowered for synonym in synonyms):
                resolved[canonical] = real
                used.add(real)
                break
    return resolved


class ToolCatalog:
    """Resolved mapping from product capabilities to real MCP tools."""

    def __init__(self, bound: dict[Capability, BoundTool], all_tools: list[MCPTool]):
        self._bound = bound
        self.all_tools = all_tools

    # -- construction ----------------------------------------------------

    @classmethod
    def from_tools(
        cls, tools: Iterable[MCPTool], *, overrides_json: str = ""
    ) -> "ToolCatalog":
        """Classify a discovered tool list, honouring env overrides first."""
        tools = list(tools)
        by_name = {tool.name: tool for tool in tools}
        overrides = _parse_overrides(overrides_json)

        bound: dict[Capability, BoundTool] = {}

        for capability, tool_name in overrides.items():
            tool = by_name.get(tool_name)
            if tool is None:
                logger.warning(
                    "tool override points at an unknown tool",
                    extra={"capability": capability.value, "tool": tool_name},
                )
                continue
            bound[capability] = BoundTool(
                capability=capability,
                tool=tool,
                arg_map=_map_arguments(tool),
                confidence=1.0,
                forced=True,
            )

        for capability, signature in SIGNATURES.items():
            if capability in bound:
                continue
            best: tuple[float, MCPTool] | None = None
            for tool in tools:
                score = _score(tool, signature)
                if score and (best is None or score > best[0]):
                    best = (score, tool)
            if best:
                bound[capability] = BoundTool(
                    capability=capability,
                    tool=best[1],
                    arg_map=_map_arguments(best[1]),
                    confidence=best[0],
                )

        catalog = cls(bound, tools)
        logger.info(
            "mcp capabilities resolved",
            extra={
                "resolved": ",".join(
                    f"{c.value}->{b.tool.name}" for c, b in sorted(bound.items())
                )
                or "none",
                "missing": ",".join(c.value for c in Capability if c not in bound) or "none",
            },
        )
        return catalog

    # -- lookups ---------------------------------------------------------

    def get(self, capability: Capability) -> BoundTool | None:
        return self._bound.get(capability)

    def has(self, capability: Capability) -> bool:
        return capability in self._bound

    @property
    def resolved(self) -> dict[Capability, BoundTool]:
        return dict(self._bound)

    @property
    def missing(self) -> list[Capability]:
        return [c for c in Capability if c not in self._bound]

    def describe(self) -> dict[str, Any]:
        """Human-readable snapshot for /api/health and docs."""
        return {
            "tools_discovered": [t.name for t in self.all_tools],
            "capabilities": {
                capability.value: {
                    "tool": bound.tool.name,
                    "confidence": round(bound.confidence, 2),
                    "forced": bound.forced,
                    "arguments": bound.arg_map,
                    "unfilled_required": bound.missing_required,
                }
                for capability, bound in sorted(self._bound.items())
            },
            "missing": [c.value for c in self.missing],
        }


def _parse_overrides(raw: str) -> dict[Capability, str]:
    """Parse the ``MCP_TOOL_MAP`` env override, ignoring nonsense safely."""
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("MCP_TOOL_MAP is not valid JSON — ignoring it")
        return {}
    result: dict[Capability, str] = {}
    for key, value in (data or {}).items():
        try:
            result[Capability(key)] = str(value)
        except ValueError:
            logger.warning("unknown capability in MCP_TOOL_MAP", extra={"key": key})
    return result
