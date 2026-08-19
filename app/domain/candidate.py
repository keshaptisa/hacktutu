"""The intermediate object between "MCP returned things" and "here is a card".

A :class:`Candidate` is one concrete way to spend the user's time and money:
a destination, a way there, a way back, optionally a bed. It is deliberately
plain data — the scorer must stay a pure function of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.destinations import Destination
from app.domain.models import (
    DataOrigin,
    HotelOption,
    TransportKind,
    TransportOption,
)


@dataclass
class Candidate:
    """One priced, timed, bookable-ish option."""

    destination: Destination
    outbound: TransportOption
    inbound: TransportOption | None = None
    hotel: HotelOption | None = None
    nights: int = 0
    origin: str = "Москва"
    data_origin: DataOrigin = DataOrigin.MCP
    warnings: list[str] = field(default_factory=list)

    # -- money -----------------------------------------------------------

    @property
    def transport_price(self) -> int:
        """Total ticket cost. Missing prices count as zero and raise a warning."""
        total = 0
        for leg in (self.outbound, self.inbound):
            if leg is not None and leg.price_rub:
                total += leg.price_rub
        return total

    @property
    def stay_price(self) -> int:
        if self.hotel is None:
            return 0
        return self.hotel.total_price_rub or 0

    @property
    def total_price(self) -> int:
        """What the trip costs before food and local transport."""
        return self.transport_price + self.stay_price

    @property
    def has_full_pricing(self) -> bool:
        """True when every component we show actually has a price from MCP."""
        legs = [leg for leg in (self.outbound, self.inbound) if leg is not None]
        if any(leg.price_rub is None for leg in legs):
            return False
        if self.hotel is not None and self.hotel.price_per_night_rub is None:
            return False
        return True

    # -- time ------------------------------------------------------------

    @property
    def travel_minutes(self) -> int:
        """Door-to-door time spent moving, both ways."""
        total = 0
        for leg in (self.outbound, self.inbound):
            if leg is not None and leg.total_duration_minutes:
                total += leg.total_duration_minutes
        return total

    @property
    def transfers(self) -> int:
        return sum(
            leg.transfers for leg in (self.outbound, self.inbound) if leg is not None
        )

    @property
    def kind(self) -> TransportKind:
        return self.outbound.kind

    @property
    def is_night_ride(self) -> bool:
        return bool(self.outbound.is_night_ride)

    # -- identity --------------------------------------------------------

    @property
    def key(self) -> str:
        """Identity used for de-duplication inside one search."""
        return f"{self.destination.name}|{self.kind.value}|{self.nights}"

    def note(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)
