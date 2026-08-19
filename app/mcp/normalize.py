"""Turn whatever Tutu MCP returns into ESCAPE domain objects.

We cannot hard-code a response schema for tools we discover at runtime, so this
module is deliberately shape-tolerant: it locates the list of offers inside an
arbitrary payload and reads each offer through field synonyms.

Two rules are absolute:

* a booking URL is only ever *copied* from the payload, never constructed;
* a missing field stays ``None`` — we never fill a gap with a plausible number.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from typing import Any, Iterable

from app.domain.models import (
    DataOrigin,
    HotelOption,
    PurchaseLink,
    TransportKind,
    TransportOption,
    TransportSegment,
)
from app.utils.dates import is_night_time

logger = logging.getLogger(__name__)

_PRICE_KEYS = ("price", "cost", "amount", "value", "min_price", "minprice", "total", "fare", "цена")
_URL_KEYS = ("url", "link", "href", "deeplink", "booking_url", "buy_url", "order_url", "ссылка")
_DEPART_KEYS = ("departure", "depart", "departure_time", "departuredatetime", "start", "from_time", "time_from", "otpravlenie")
_ARRIVE_KEYS = ("arrival", "arrive", "arrival_time", "arrivaldatetime", "end", "to_time", "time_to", "pribytie")
_DURATION_KEYS = ("duration", "travel_time", "duration_minutes", "in_way", "time_in_way", "length")
_CARRIER_KEYS = ("carrier", "airline", "company", "operator", "brand", "perevozchik")
_NUMBER_KEYS = ("number", "train_number", "flight_number", "code", "no", "nomer")
_TRANSFER_KEYS = ("transfers", "stops", "changes", "transfer_count", "peresadki", "segments_count")
_NAME_KEYS = ("name", "title", "hotel_name", "caption")
_STARS_KEYS = ("stars", "star_rating", "category", "zvezd")
_RATING_KEYS = ("rating", "score", "review_score", "user_rating", "reyting")
_REVIEWS_KEYS = ("reviews", "reviews_count", "review_count", "votes", "otzyvy")
_DISTRICT_KEYS = ("district", "area", "neighbourhood", "region", "rayon")
_DISTANCE_KEYS = ("distance_to_center", "center_distance", "distance", "to_center")
_PHOTO_KEYS = ("photos", "images", "photo", "image", "picture", "thumbnail", "photo_url", "image_url")
_LIST_KEYS = (
    "items", "results", "offers", "variants", "options", "data", "list",
    "trains", "flights", "buses", "hotels", "segments", "tickets", "rooms",
    "schedule", "threads", "routes", "content",
)


# --------------------------------------------------------------------------
# Generic readers
# --------------------------------------------------------------------------


def find_records(payload: Any, *, depth: int = 0) -> list[dict[str, Any]]:
    """Locate the most plausible list of offer records in an unknown payload."""
    if depth > 6 or payload is None:
        return []
    if isinstance(payload, list):
        records = [item for item in payload if isinstance(item, dict)]
        if records:
            return records
        nested: list[dict[str, Any]] = []
        for item in payload:
            nested.extend(find_records(item, depth=depth + 1))
        return nested
    if not isinstance(payload, dict):
        return []

    # Preferred keys first, then any list-of-dicts we can find.
    for key in _LIST_KEYS:
        if key in payload:
            found = find_records(payload[key], depth=depth + 1)
            if found:
                return found
    best: list[dict[str, Any]] = []
    for value in payload.values():
        found = find_records(value, depth=depth + 1)
        if len(found) > len(best):
            best = found
    if best:
        return best
    # A single record returned bare.
    if any(_get(payload, _PRICE_KEYS) is not None for _ in (0,)):
        return [payload]
    return []


def _flatten(record: dict[str, Any], prefix: str = "", depth: int = 0) -> dict[str, Any]:
    """Flatten one level-ish so 'price.amount' is reachable as 'price_amount'."""
    flat: dict[str, Any] = {}
    for key, value in record.items():
        name = f"{prefix}{key}".lower()
        if isinstance(value, dict) and depth < 2:
            flat.update(_flatten(value, prefix=f"{name}_", depth=depth + 1))
            if not any(isinstance(v, (dict, list)) for v in value.values()):
                flat[name] = value
        else:
            flat[name] = value
    return flat


def _get(record: dict[str, Any], keys: Iterable[str]) -> Any:
    """Read the first matching key, tolerating nesting and naming styles."""
    flat = _flatten(record)
    for key in keys:
        needle = key.replace("_", "")
        for name, value in flat.items():
            if name.replace("_", "") == needle and value not in (None, "", []):
                return value
    for key in keys:
        needle = key.replace("_", "")
        for name, value in flat.items():
            if needle in name.replace("_", "") and value not in (None, "", []):
                return value
    return None


def read_int(value: Any) -> int | None:
    """Parse an int out of numbers, numeric strings and {'amount': 123} dicts."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(round(value))
    if isinstance(value, dict):
        for key in _PRICE_KEYS:
            if key in value:
                return read_int(value[key])
        return None
    if isinstance(value, str):
        digits = re.sub(r"[^\d.,]", "", value).replace(",", ".")
        if not digits:
            return None
        try:
            return int(round(float(digits)))
        except ValueError:
            return None
    return None


def read_datetime(value: Any) -> datetime | None:
    """Parse ISO-8601-ish datetimes; return None rather than guessing."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)) and value > 1_000_000_000:
        try:
            return datetime.fromtimestamp(float(value))
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, dict):
        for key in ("datetime", "date_time", "iso", "local", "value"):
            if key in value:
                return read_datetime(value[key])
        return None
    if not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    for candidate in (text, text.replace(" ", "T")):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    match = re.search(r"(\d{2}):(\d{2})", text)
    if match:
        return None  # a bare time without a date is not enough to trust
    return None


def read_duration_minutes(value: Any) -> int | None:
    """Accept minutes, 'PT4H30M', '4:30' or '4 ч 30 мин'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        minutes = int(value)
        return minutes if minutes < 6000 else minutes // 60
    if isinstance(value, dict):
        return read_duration_minutes(_get(value, ("minutes", "value", "total")))
    text = str(value).strip().lower()
    iso = re.match(r"p?t?(?:(\d+)h)?(?:(\d+)m)?$", text.replace(" ", ""))
    if iso and (iso.group(1) or iso.group(2)):
        return int(iso.group(1) or 0) * 60 + int(iso.group(2) or 0)
    clock = re.match(r"^(\d{1,3}):(\d{2})$", text)
    if clock:
        return int(clock.group(1)) * 60 + int(clock.group(2))
    parts = re.findall(r"(\d+)\s*(ч|час|h|мин|м|min)", text)
    if parts:
        total = 0
        for amount, unit in parts:
            total += int(amount) * (60 if unit.startswith(("ч", "h")) else 1)
        return total
    return read_int(value)


def read_url(record: dict[str, Any]) -> str | None:
    """Find a real absolute URL inside the record. Never build one."""
    value = _get(record, _URL_KEYS)
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value
    if isinstance(value, dict):
        nested = _get(value, _URL_KEYS)
        if isinstance(nested, str) and nested.startswith(("http://", "https://")):
            return nested
    return None


def read_image_url(record: dict[str, Any]) -> str | None:
    """Find the first absolute image URL in a hotel record."""

    def _first_url(value: Any) -> str | None:
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
        if isinstance(value, list):
            for item in value:
                found = _first_url(item)
                if found:
                    return found
        if isinstance(value, dict):
            for key in ("url", "src", "href", "large", "original", "preview", "default"):
                found = _first_url(value.get(key))
                if found:
                    return found
        return None

    return _first_url(_get(record, _PHOTO_KEYS))


def _stable_id(prefix: str, payload: Any) -> str:
    digest = hashlib.sha1(repr(payload).encode("utf-8", "ignore")).hexdigest()[:10]
    return f"{prefix}_{digest}"


# --------------------------------------------------------------------------
# Domain mappers
# --------------------------------------------------------------------------


def to_transport_option(
    record: dict[str, Any],
    *,
    kind: TransportKind,
    from_place: str,
    to_place: str,
    origin: DataOrigin = DataOrigin.MCP,
) -> TransportOption | None:
    """Map one raw MCP record onto a :class:`TransportOption`."""
    try:
        price = read_int(_get(record, _PRICE_KEYS))
        departure = read_datetime(_get(record, _DEPART_KEYS))
        arrival = read_datetime(_get(record, _ARRIVE_KEYS))
        duration = read_duration_minutes(_get(record, _DURATION_KEYS))
        if duration is None and departure and arrival and arrival > departure:
            duration = int((arrival - departure).total_seconds() // 60)

        transfers = read_int(_get(record, _TRANSFER_KEYS)) or 0
        carrier = _get(record, _CARRIER_KEYS)
        number = _get(record, _NUMBER_KEYS)
        url = read_url(record)

        hints: list[str] = []
        if price is None:
            hints.append("цена не пришла из MCP")
        if duration is None:
            hints.append("длительность не пришла из MCP")

        segment = TransportSegment(
            kind=kind,
            carrier=str(carrier)[:80] if carrier else None,
            number=str(number)[:24] if number else None,
            from_place=from_place,
            to_place=to_place,
            departure=departure,
            arrival=arrival,
            duration_minutes=duration,
            price_rub=price,
        )
        return TransportOption(
            id=_stable_id(kind.value, record),
            kind=kind,
            from_place=from_place,
            to_place=to_place,
            segments=[segment],
            transfers=min(max(transfers, 0), 10),
            total_duration_minutes=duration,
            price_rub=price,
            is_night_ride=is_night_time(departure),
            purchase=PurchaseLink(label="Оформить на Туту", url=url, source=origin)
            if url
            else None,
            source=origin,
            raw_hint="; ".join(hints) or None,
        )
    except Exception as exc:  # defensive: one bad record must not kill a search
        logger.debug("skipping unmappable transport record", extra={"error": str(exc)})
        return None


def to_hotel_option(
    record: dict[str, Any],
    *,
    city: str,
    nights: int,
    origin: DataOrigin = DataOrigin.MCP,
) -> HotelOption | None:
    """Map one raw MCP record onto a :class:`HotelOption`."""
    try:
        name = _get(record, _NAME_KEYS)
        if not name:
            return None
        price = read_int(_get(record, _PRICE_KEYS))
        if price is not None and nights > 1 and price > 30_000:
            # Some APIs return the stay total; keep per-night semantics stable.
            price = int(price / nights)
        stars = read_int(_get(record, _STARS_KEYS))
        rating_raw = _get(record, _RATING_KEYS)
        rating = None
        if rating_raw is not None:
            try:
                rating = round(float(str(rating_raw).replace(",", ".")), 1)
            except ValueError:
                rating = None
            if rating is not None and rating > 10:
                rating = round(rating / 10, 1)
        distance_raw = _get(record, _DISTANCE_KEYS)
        distance = None
        if distance_raw is not None:
            try:
                distance = round(float(str(distance_raw).replace(",", ".")), 1)
            except ValueError:
                distance = None

        url = read_url(record)
        image_url = read_image_url(record)
        return HotelOption(
            id=_stable_id("hotel", record),
            name=str(name)[:120],
            city=city,
            image_url=image_url,
            stars=stars if stars is not None and 0 <= stars <= 5 else None,
            rating=rating if rating is not None and 0 <= rating <= 10 else None,
            reviews_count=read_int(_get(record, _REVIEWS_KEYS)),
            price_per_night_rub=price,
            nights=max(nights, 0),
            district=str(_get(record, _DISTRICT_KEYS))[:80]
            if _get(record, _DISTRICT_KEYS)
            else None,
            distance_to_center_km=distance,
            purchase=PurchaseLink(label="Забронировать на Туту", url=url, source=origin)
            if url
            else None,
            source=origin,
        )
    except Exception as exc:  # defensive
        logger.debug("skipping unmappable hotel record", extra={"error": str(exc)})
        return None
