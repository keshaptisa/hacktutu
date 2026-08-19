"""Offline demo data.

Used when ``DEMO_MODE=true`` or when Tutu MCP is unreachable and we would
otherwise show the user nothing. Everything produced here is stamped
``DataOrigin.DEMO`` and the UI labels it in red — a demo trip never pretends to
be a live search result.

Two things this module will *not* do, ever:

* invent a booking URL — demo candidates carry no purchase link at all;
* claim availability — the UI says "образец данных", not "мест: 4".

Numbers are derived deterministically from the destination table so the demo is
byte-identical on every machine, which matters when nine judges open it at once.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta

from app.domain.candidate import Candidate
from app.domain.destinations import Destination
from app.domain.models import (
    DataOrigin,
    HotelOption,
    TransportKind,
    TransportOption,
    TransportSegment,
)

# Roughly what a seat costs per hour of travel, by mode (₽/h). Demo only.
PRICE_PER_HOUR: dict[TransportKind, int] = {
    TransportKind.TRAIN: 620,
    TransportKind.PLANE: 2_900,
    TransportKind.BUS: 380,
    TransportKind.SUBURBAN: 190,
    TransportKind.UNKNOWN: 500,
}

HOTEL_BASE_PER_NIGHT = 3_400

HOTEL_NAMES = (
    "Отель на Соборной",
    "Гостиница «Старый двор»",
    "Апарт-отель «Тихий этаж»",
    "Бутик-отель «Купеческий»",
    "Мини-отель «Набережная»",
)

DISTRICTS = ("Исторический центр", "У кремля", "Набережная", "Старый город")


def _seed(*parts: str) -> int:
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _variation(seed: int, spread: float = 0.22) -> float:
    """Stable pseudo-variation in ``[1-spread, 1+spread]``."""
    return 1 + ((seed % 1000) / 1000 - 0.5) * 2 * spread


def demo_transport(
    destination: Destination,
    origin: str,
    kind: TransportKind,
    hours: float,
    when: date,
    *,
    outbound: bool = True,
    variant: int = 0,
) -> TransportOption:
    """Build one plausible, clearly-labelled demo leg.

    ``variant`` shifts the departure across the day (and the price with it) so a
    destination has an early, a daytime and a night option like a real timetable.
    """
    seed = _seed(destination.name, kind.value, str(when), "out" if outbound else "back", str(variant))
    minutes = int(hours * 60 * _variation(seed, 0.08))
    price = int(PRICE_PER_HOUR[kind] * hours * _variation(seed, 0.25) / 50) * 50

    # variant 0 = утро, 1 = день, 2 = вечер, 3 = ночь. Ночь традиционно дешевле,
    # поэтому «самый дешёвый» вариант по умолчанию оказывается ночным — и именно
    # его человек потом просит заменить на дневной.
    slot_hours = (7, 11, 18, 23)
    slot_price = (1.00, 1.12, 1.06, 0.72)
    depart_hour = slot_hours[variant % len(slot_hours)]
    price = int(price * slot_price[variant % len(slot_price)] / 50) * 50
    departure = datetime.combine(when, time(hour=depart_hour, minute=(seed % 4) * 15))
    arrival = departure + timedelta(minutes=minutes)

    from_place = origin if outbound else destination.name
    to_place = destination.name if outbound else origin

    return TransportOption(
        id=f"demo_{kind.value}_{seed % 100000}",
        kind=kind,
        from_place=from_place,
        to_place=to_place,
        segments=[
            TransportSegment(
                kind=kind,
                carrier={"train": "РЖД", "plane": "Авиакомпания", "bus": "Перевозчик"}.get(
                    kind.value, "Перевозчик"
                ),
                number=str(100 + seed % 800),
                from_place=from_place,
                to_place=to_place,
                departure=departure,
                arrival=arrival,
                duration_minutes=minutes,
                price_rub=price,
            )
        ],
        transfers=0 if hours < 8 else seed % 2,
        total_duration_minutes=minutes,
        price_rub=price,
        is_night_ride=departure.hour >= 22 or departure.hour < 6,
        purchase=None,  # demo data never carries a link
        source=DataOrigin.DEMO,
        raw_hint="образец данных, не результат живого поиска",
    )


def demo_transport_options(
    destination: Destination,
    origin: str,
    kind: TransportKind,
    hours: float,
    when: date,
    *,
    outbound: bool = True,
    count: int = 4,
) -> list[TransportOption]:
    """Several demo departures across the day, so refinement has real choices.

    Without this a "хочу дневной поезд" refinement would have nothing to switch
    to and the demo would silently do nothing.
    """
    options: list[TransportOption] = []
    for index in range(count):
        option = demo_transport(
            destination, origin, kind, hours, when, outbound=outbound, variant=index
        )
        options.append(option)
    return options


def demo_hotel(destination: Destination, nights: int, index: int = 0) -> HotelOption | None:
    """Build one demo hotel for a destination."""
    if nights <= 0:
        return None
    seed = _seed(destination.name, "hotel", str(index))
    price = int(HOTEL_BASE_PER_NIGHT * _variation(seed, 0.35) / 100) * 100
    return HotelOption(
        id=f"demo_hotel_{seed % 100000}",
        name=HOTEL_NAMES[seed % len(HOTEL_NAMES)],
        city=destination.name,
        stars=3 + seed % 2,
        rating=round(8.0 + (seed % 15) / 10, 1),
        reviews_count=80 + seed % 900,
        price_per_night_rub=price,
        nights=nights,
        district=DISTRICTS[seed % len(DISTRICTS)],
        distance_to_center_km=round(0.3 + (seed % 20) / 10, 1),
        purchase=None,
        source=DataOrigin.DEMO,
    )


def _cheapest_demo_hotel(destination: Destination, nights: int) -> HotelOption | None:
    """The budget option by default — refinement is what trades up."""
    hotels = [demo_hotel(destination, nights, index=i) for i in range(3)]
    available = [h for h in hotels if h is not None]
    if not available:
        return None
    return min(available, key=lambda h: h.price_per_night_rub or 10**9)


def demo_candidate(
    destination: Destination,
    origin_key: str,
    origin_name: str,
    kind: TransportKind,
    hours: float,
    when: date,
    nights: int,
) -> Candidate:
    """Assemble a full demo candidate for one destination."""
    variants = demo_transport_options(destination, origin_name, kind, hours, when, outbound=True)
    outbound = min(variants, key=lambda o: (o.price_rub or 10**9))
    back_date = when + timedelta(days=max(nights, 1))
    inbound = min(
        demo_transport_options(destination, origin_name, kind, hours, back_date, outbound=False),
        key=lambda o: (o.price_rub or 10**9),
    )
    candidate = Candidate(
        destination=destination,
        outbound=outbound,
        inbound=inbound,
        hotel=_cheapest_demo_hotel(destination, nights),
        nights=nights,
        origin=origin_name,
        data_origin=DataOrigin.DEMO,
    )
    candidate.note("демо-данные: цены и расписание не проверены в Туту")
    return candidate
