"""Transport-level MCP client (JSON-RPC 2.0 over Streamable HTTP).

This module knows *only* about the Model Context Protocol. It has no idea what
travel is. It performs the handshake, keeps the session alive, lists tools and
calls them, with timeouts, bounded retries and exponential backoff.

Tutu MCP speaks the standard protocol, so the same code works against any
compliant server, which is what makes it testable offline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

import httpx

from app.core.config import Settings
from app.core.errors import MCPProtocolError, MCPUnavailableError

logger = logging.getLogger(__name__)

JSONRPC = "2.0"


class MCPTool:
    """A tool as advertised by the server. We never invent these."""

    __slots__ = ("name", "description", "input_schema")

    def __init__(self, name: str, description: str, input_schema: dict[str, Any]):
        self.name = name
        self.description = description or ""
        self.input_schema = input_schema or {}

    @property
    def properties(self) -> dict[str, Any]:
        return self.input_schema.get("properties", {}) or {}

    @property
    def required(self) -> list[str]:
        return list(self.input_schema.get("required", []) or [])

    @property
    def searchable_text(self) -> str:
        """Everything we are allowed to classify on: the server's own words."""
        return f"{self.name} {self.description} {' '.join(self.properties)}".lower()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<MCPTool {self.name}>"


def _parse_sse(body: str) -> dict[str, Any]:
    """Extract the last JSON payload from a text/event-stream response."""
    payload: dict[str, Any] | None = None
    for line in body.splitlines():
        if line.startswith("data:"):
            chunk = line[5:].strip()
            if not chunk or chunk == "[DONE]":
                continue
            try:
                payload = json.loads(chunk)
            except json.JSONDecodeError:
                continue
    if payload is None:
        raise MCPProtocolError("event-stream contained no JSON payload")
    return payload


class MCPClient:
    """Async MCP client with one lazily-initialised session."""

    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None):
        self._settings = settings
        self._url = settings.mcp_url
        self._own_http = http is None
        self._http = http or httpx.AsyncClient(
            timeout=httpx.Timeout(
                settings.mcp_timeout_s, connect=settings.mcp_connect_timeout_s
            ),
            follow_redirects=True,
            headers={"User-Agent": "ESCAPE/1.0 (Tutu MCP hackathon)"},
        )
        self._session_id: str | None = None
        self._request_id = 0
        self._init_lock = asyncio.Lock()
        self._initialized = False
        self._tools: list[MCPTool] = []
        self.server_info: dict[str, Any] = {}
        self.last_error: str | None = None

    # -- lifecycle -------------------------------------------------------

    async def aclose(self) -> None:
        """Release the underlying HTTP pool."""
        if self._own_http:
            await self._http.aclose()

    @property
    def is_ready(self) -> bool:
        return self._initialized and bool(self._tools)

    # -- protocol --------------------------------------------------------

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self._settings.mcp_protocol_version,
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        if self._settings.mcp_auth_header:
            headers["Authorization"] = self._settings.mcp_auth_header
        return headers

    async def _post(self, payload: dict[str, Any], *, expect_result: bool) -> dict[str, Any]:
        """POST one JSON-RPC message with retries and backoff."""
        attempts = max(1, self._settings.mcp_retries + 1)
        last_exc: Exception | None = None

        for attempt in range(attempts):
            try:
                response = await self._http.post(
                    self._url, json=payload, headers=self._headers()
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                logger.warning(
                    "mcp transport failure", extra={"attempt": attempt, "error": str(exc)}
                )
            else:
                session = response.headers.get("mcp-session-id")
                if session:
                    self._session_id = session

                if response.status_code in (202, 204):
                    return {}
                if response.status_code == 404 and self._session_id:
                    # Session expired — drop it and let the caller re-handshake.
                    self._session_id = None
                    self._initialized = False
                    last_exc = MCPUnavailableError("mcp session expired")
                elif response.status_code >= 500 or response.status_code == 429:
                    last_exc = MCPUnavailableError(
                        f"mcp http {response.status_code}: {response.text[:200]}"
                    )
                    logger.warning(
                        "mcp server error",
                        extra={"status": response.status_code, "attempt": attempt},
                    )
                elif response.status_code >= 400:
                    raise MCPProtocolError(
                        f"mcp http {response.status_code}: {response.text[:300]}"
                    )
                else:
                    return self._decode(response, expect_result=expect_result)

            if attempt < attempts - 1:
                delay = self._settings.mcp_backoff_s * (2**attempt)
                await asyncio.sleep(delay + random.uniform(0, 0.2))

        self.last_error = str(last_exc)
        raise MCPUnavailableError(f"mcp unreachable: {last_exc}")

    def _decode(self, response: httpx.Response, *, expect_result: bool) -> dict[str, Any]:
        """Turn an HTTP response into a JSON-RPC result object."""
        content_type = response.headers.get("content-type", "")
        body = response.text.strip()
        if not body:
            return {}
        try:
            message = _parse_sse(body) if "event-stream" in content_type else json.loads(body)
        except json.JSONDecodeError as exc:
            raise MCPProtocolError(f"invalid json from mcp: {exc}") from exc

        if isinstance(message, list):  # batch response
            message = message[-1] if message else {}
        if "error" in message:
            error = message["error"] or {}
            raise MCPProtocolError(
                f"mcp error {error.get('code')}: {error.get('message')}"
            )
        result = message.get("result", {})
        if expect_result and not isinstance(result, dict):
            raise MCPProtocolError("mcp result is not an object")
        return result or {}

    async def initialize(self) -> None:
        """Handshake + tool discovery. Safe to call concurrently."""
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            result = await self._post(
                {
                    "jsonrpc": JSONRPC,
                    "id": self._next_id(),
                    "method": "initialize",
                    "params": {
                        "protocolVersion": self._settings.mcp_protocol_version,
                        "capabilities": {},
                        "clientInfo": {"name": "escape", "version": "1.0.0"},
                    },
                },
                expect_result=True,
            )
            self.server_info = result.get("serverInfo", {}) or {}
            await self._post(
                {"jsonrpc": JSONRPC, "method": "notifications/initialized"},
                expect_result=False,
            )
            self._initialized = True
            logger.info(
                "mcp initialized",
                extra={
                    "server": self.server_info.get("name", "unknown"),
                    "version": self.server_info.get("version", "?"),
                },
            )

    async def list_tools(self, *, force: bool = False) -> list[MCPTool]:
        """Discover the tools this server actually exposes."""
        if self._tools and not force:
            return self._tools
        await self.initialize()

        tools: list[MCPTool] = []
        cursor: str | None = None
        for _ in range(10):  # bounded pagination
            params: dict[str, Any] = {"cursor": cursor} if cursor else {}
            result = await self._post(
                {
                    "jsonrpc": JSONRPC,
                    "id": self._next_id(),
                    "method": "tools/list",
                    "params": params,
                },
                expect_result=True,
            )
            for item in result.get("tools", []) or []:
                tools.append(
                    MCPTool(
                        name=item.get("name", ""),
                        description=item.get("description", ""),
                        input_schema=item.get("inputSchema") or item.get("input_schema") or {},
                    )
                )
            cursor = result.get("nextCursor")
            if not cursor:
                break

        self._tools = [t for t in tools if t.name]
        logger.info("mcp tools discovered", extra={"count": len(self._tools)})
        return self._tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool and return its decoded content.

        MCP returns a content array; we unwrap JSON payloads where possible and
        fall back to raw text so the adapter can decide what to do.
        """
        await self.initialize()
        result = await self._post(
            {
                "jsonrpc": JSONRPC,
                "id": self._next_id(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
            expect_result=True,
        )
        if result.get("isError"):
            raise MCPProtocolError(f"tool {name} reported an error: {result}")
        if "structuredContent" in result:
            return result["structuredContent"]
        return unwrap_content(result.get("content", []))


def unwrap_content(content: Any) -> Any:
    """Turn an MCP content array into plain Python data.

    Text blocks that hold JSON are parsed; everything else is returned as text.
    A single item is unwrapped, several are returned as a list.
    """
    if not isinstance(content, list):
        return content
    decoded: list[Any] = []
    for block in content:
        if not isinstance(block, dict):
            decoded.append(block)
            continue
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text", "")
            try:
                decoded.append(json.loads(text))
            except (json.JSONDecodeError, TypeError):
                decoded.append(text)
        elif block_type == "resource":
            resource = block.get("resource", {})
            text = resource.get("text")
            if text:
                try:
                    decoded.append(json.loads(text))
                except (json.JSONDecodeError, TypeError):
                    decoded.append(text)
        else:
            decoded.append(block)
    if not decoded:
        return None
    return decoded[0] if len(decoded) == 1 else decoded
