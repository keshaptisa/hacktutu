"""Session storage for escapes.

An in-process TTL + LRU dict. That is a deliberate choice for a hackathon MVP:
a single uvicorn worker on a small VPS holds a few hundred sessions in a few
megabytes, and there is no database to fail during a demo. The interface is
narrow on purpose — swapping in Redis later means implementing four methods.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from app.ai.schemas import NormalizedIntent
from app.domain.models import EscapeResult, EscapeScenario


@dataclass
class EscapeSession:
    """Everything needed to keep working on one escape after the first search."""

    result: EscapeResult
    intent: NormalizedIntent
    start_date: date
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    email_html: str | None = None
    email_path: str | None = None

    def scenario(self, scenario_id: str) -> EscapeScenario | None:
        for item in self.result.scenarios:
            if item.id == scenario_id:
                return item
        return None

    def replace_scenario(self, scenario: EscapeScenario) -> None:
        """Swap a refined scenario in place, keeping card order stable."""
        self.result.scenarios = [
            scenario if item.id == scenario.id else item for item in self.result.scenarios
        ]


class EscapeStore:
    """Thread-safe bounded store with time-based expiry."""

    def __init__(self, *, ttl_minutes: int = 180, max_items: int = 200):
        self._ttl = timedelta(minutes=ttl_minutes)
        self._max = max_items
        self._items: OrderedDict[str, EscapeSession] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, session: EscapeSession) -> None:
        with self._lock:
            self._items[session.result.id] = session
            self._items.move_to_end(session.result.id)
            self._evict()

    def get(self, escape_id: str) -> EscapeSession | None:
        with self._lock:
            session = self._items.get(escape_id)
            if session is None:
                return None
            if self._expired(session):
                del self._items[escape_id]
                return None
            self._items.move_to_end(escape_id)
            return session

    def delete(self, escape_id: str) -> None:
        with self._lock:
            self._items.pop(escape_id, None)

    def size(self) -> int:
        with self._lock:
            return len(self._items)

    # -- internals -------------------------------------------------------

    def _expired(self, session: EscapeSession) -> bool:
        return datetime.now(timezone.utc) - session.created_at > self._ttl

    def _evict(self) -> None:
        """Drop expired entries first, then the oldest ones over the cap."""
        for key in [k for k, v in self._items.items() if self._expired(v)]:
            del self._items[key]
        while len(self._items) > self._max:
            self._items.popitem(last=False)
