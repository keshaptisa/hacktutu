"""Date and duration helpers, all Russian-locale aware without extra deps."""

from __future__ import annotations

from datetime import date, datetime, timedelta

WEEKDAYS = (
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
)

MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def weekday_name(value: date) -> str:
    """'Пятница' for a given date."""
    return WEEKDAYS[value.weekday()]


def format_date(value: date) -> str:
    """'21 августа'."""
    return f"{value.day} {MONTHS_GENITIVE[value.month - 1]}"


def format_date_range(start: date, end: date) -> str:
    """'21–23 августа' or '30 августа — 2 сентября'."""
    if start == end:
        return format_date(start)
    if start.month == end.month:
        return f"{start.day}–{end.day} {MONTHS_GENITIVE[start.month - 1]}"
    return f"{format_date(start)} — {format_date(end)}"


def next_friday(today: date | None = None) -> date:
    """The upcoming Friday — our default departure when the user gives no date."""
    today = today or date.today()
    delta = (4 - today.weekday()) % 7
    return today + timedelta(days=delta or 7)


def nights_for(duration_hours: int) -> int:
    """How many hotel nights a trip of N hours realistically needs."""
    if duration_hours <= 14:
        return 0
    return max(1, round((duration_hours - 14) / 24))


def humanize_minutes(minutes: int | None) -> str:
    """90 -> '1 ч 30 мин'."""
    if minutes is None:
        return "—"
    hours, mins = divmod(int(minutes), 60)
    if hours and mins:
        return f"{hours} ч {mins} мин"
    if hours:
        return f"{hours} ч"
    return f"{mins} мин"


def humanize_duration_hours(hours: int) -> str:
    """36 -> '1 день 12 часов'; used for the big number on screen one."""
    if hours < 24:
        return f"{hours} ч"
    days, rest = divmod(hours, 24)
    label = plural_days(days)
    return f"{label} {rest} ч" if rest else label


def plural_days(days: int) -> str:
    """Russian plural for days."""
    if days % 10 == 1 and days % 100 != 11:
        return f"{days} день"
    if days % 10 in (2, 3, 4) and days % 100 not in (12, 13, 14):
        return f"{days} дня"
    return f"{days} дней"


def plural_nights(nights: int) -> str:
    """Russian plural for nights."""
    if nights % 10 == 1 and nights % 100 != 11:
        return f"{nights} ночь"
    if nights % 10 in (2, 3, 4) and nights % 100 not in (12, 13, 14):
        return f"{nights} ночи"
    return f"{nights} ночей"


def is_night_time(value: datetime | None) -> bool:
    """True for departures between 22:00 and 06:00."""
    if value is None:
        return False
    return value.hour >= 22 or value.hour < 6
