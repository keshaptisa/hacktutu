"""Money formatting. One place, so the UI and the email never disagree."""

from __future__ import annotations

NBSP = "\u00a0"


def format_rub(amount: int | float | None, *, approx: bool = False) -> str:
    """11400 -> '11 400 ₽'. ``approx=True`` prefixes '≈'."""
    if amount is None:
        return "—"
    value = int(round(float(amount)))
    grouped = f"{value:,}".replace(",", NBSP)
    prefix = "≈ " if approx else ""
    return f"{prefix}{grouped}{NBSP}₽"


def parse_rub(text: str) -> int | None:
    """Pull a rouble amount out of free text: 'до 17 000 ₽' -> 17000."""
    digits: list[str] = []
    found: list[int] = []
    for char in text:
        if char.isdigit():
            digits.append(char)
        elif char in " \u00a0" and digits:
            continue  # thousands separator inside a number
        else:
            if digits:
                found.append(int("".join(digits)))
                digits = []
    if digits:
        found.append(int("".join(digits)))
    plausible = [n for n in found if 500 <= n <= 500_000]
    return max(plausible) if plausible else None


def split_budget(total_rub: int, nights: int) -> tuple[int, int]:
    """Rough transport/stay split used to bound MCP queries.

    Returns ``(transport_cap, stay_cap)``. With no nights the whole budget goes
    to transport; otherwise we reserve ~45% for the hotel and keep 12% for food
    and local transport so the total does not blow past the user's number.
    """
    spendable = int(total_rub * 0.88)
    if nights <= 0:
        return spendable, 0
    stay = int(spendable * 0.45)
    return spendable - stay, stay
