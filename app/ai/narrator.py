"""Turning a scored candidate into words and a timeline.

The LLM writes here when it is available; when it is not, templates do the same
job with the same data. The split matters: **no fact is ever produced in this
module**. Times come from the transport MCP returned, prices from the candidate,
and the model only chooses how to say what is already true.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta

from app.ai.llm import LLMClient
from app.ai.prompts import SCENARIO_GENERATION
from app.ai.schemas import NormalizedIntent, ScenarioCopy
from app.domain.candidate import Candidate
from app.domain.models import (
    EscapeRequest,
    ItineraryDay,
    ItineraryEvent,
    ScenarioKind,
    TransportKind,
)
from app.utils.currency import format_rub
from app.utils.dates import format_date, plural_nights, weekday_name

logger = logging.getLogger(__name__)

# Real, checkable anchors for the cities most likely to appear in a demo run.
LANDMARKS: dict[str, tuple[str, ...]] = {
    "Ярославль": ("Волжская набережная", "Спасо-Преображенский монастырь", "Церковь Ильи Пророка", "Власьевская башня"),
    "Суздаль": ("Кремль и Рождественский собор", "Музей деревянного зодчества", "Торговые ряды", "Спасо-Евфимиев монастырь"),
    "Псков": ("Псковский кром", "Мирожский монастырь", "Довмонтов город", "Набережная Великой"),
    "Великий Новгород": ("Новгородский детинец", "Софийский собор", "Ярославово дворище", "Витославлицы"),
    "Санкт-Петербург": ("Эрмитаж", "Новая Голландия", "Улица Рубинштейна", "Стрелка Васильевского острова"),
    "Казань": ("Казанский кремль", "Улица Баумана", "Храм всех религий", "Набережная Казанки"),
    "Нижний Новгород": ("Нижегородский кремль", "Чкаловская лестница", "Стрелка", "Улица Рождественская"),
    "Тула": ("Тульский кремль", "Казанская набережная", "Музей оружия", "Ликёрка Лофт"),
    "Калуга": ("Музей космонавтики", "Каменный мост", "Гостиный двор", "Берег Оки"),
    "Владимир": ("Успенский собор", "Золотые ворота", "Дмитриевский собор", "Патриарший сад"),
    "Кострома": ("Ипатьевский монастырь", "Сусанинская площадь", "Торговые ряды", "Набережная Волги"),
    "Рыбинск": ("Улица Крестовая с историческими вывесками", "Спасо-Преображенский собор", "Волжская набережная", "Музей-заповедник"),
    "Выборг": ("Выборгский замок", "Парк Монрепо", "Круглая башня", "Старый город"),
    "Калининград": ("Кафедральный собор на острове Канта", "Рыбная деревня", "Форты", "Куршская коса"),
    "Коломна": ("Коломенский кремль", "Музей пастилы", "Посадские улицы", "Соборная площадь"),
    "Сергиев Посад": ("Троице-Сергиева лавра", "Смотровая на Блинной горе", "Музей игрушки", "Келарский пруд"),
    "Плёс": ("Гора Левитана", "Соборная гора", "Набережная Волги", "Музей пейзажа"),
    "Смоленск": ("Крепостная стена", "Успенский собор", "Лопатинский сад", "Набережная Днепра"),
    "Вологда": ("Вологодский кремль", "Деревянные особняки", "Софийский собор", "Набережная реки"),
    "Петрозаводск": ("Онежская набережная", "Кварталы исторической застройки", "Национальный музей", "Причал к Кижам"),
    "Ростов Великий": ("Ростовский кремль", "Озеро Неро", "Спасо-Яковлевский монастырь", "Финифтяная мастерская"),
    "Тверь": ("Набережная Степана Разина", "Императорский дворец", "Трёхсвятская улица", "Городской сад"),
    "Мурманск": ("Атомный ледокол «Ленин»", "Сопка Алёша", "Порт", "Выезд в Териберку"),
    "Екатеринбург": ("Красная линия", "Плотинка", "Ельцин Центр", "Конструктивистский Городок чекистов"),
    "Минск": ("Проспект Независимости", "Верхний город", "Комаровский рынок", "Остров слёз"),
    "Тбилиси": ("Серные бани Абанотубани", "Старый город", "Крепость Нарикала", "Сухой мост"),
    "Кисловодск": ("Курортный парк", "Нарзанная галерея", "Красные камни", "Гора Кольцо"),
    "Пермь": ("Набережная Камы", "Музей PERMM", "Пермские боги в галерее", "Квартал заводов"),
    "Иркутск": ("130-й квартал", "Набережная Ангары", "Дом Волконских", "Выезд на Байкал"),
    "Сочи": ("Набережная", "Красная Поляна", "Дендрарий", "Олимпийский парк"),
}

TAG_ACTIVITIES: dict[str, str] = {
    "еда": "Долгий обед с местной кухней",
    "исторический": "Исторический центр пешком",
    "набережная": "Прогулка по набережной",
    "природа": "Выход к воде и в парк",
    "море": "Время у воды",
    "музеи": "Городской музей",
    "зима": "Согреться в кофейне",
    "бары": "Вечер в барах",
    "необычно": "Что-то странное и местное",
    "медленно": "Час без планов",
    "красиво": "Точка с лучшим видом",
}

ARCHETYPE_TAGLINE = {
    ScenarioKind.SILENCE: "{blurb} Ритм здесь задаёшь ты, а не расписание.",
    ScenarioKind.MADNESS: "{blurb} За {duration} сюда влезает больше, чем кажется.",
    ScenarioKind.UNEXPECTED: "{blurb} Сам бы ты это вряд ли выбрал — и в этом смысл.",
}

ICON_BY_KIND = {
    TransportKind.TRAIN: "train",
    TransportKind.PLANE: "plane",
    TransportKind.BUS: "bus",
    TransportKind.SUBURBAN: "train",
    TransportKind.UNKNOWN: "train",
}


# --------------------------------------------------------------------------
# Copy
# --------------------------------------------------------------------------


def activity_pool(candidate: Candidate) -> list[str]:
    """Concrete things to do, anchored in the destination we actually picked."""
    name = candidate.destination.name
    pool = list(LANDMARKS.get(name, ()))
    for tag in candidate.destination.tags:
        activity = TAG_ACTIVITIES.get(tag)
        if activity and activity not in pool:
            pool.append(activity)
    if not pool:
        pool = ["Центр города пешком", "Местная кухня", "Смотровая точка", "Час без планов"]
    return pool


def template_copy(
    candidate: Candidate, request: EscapeRequest, kind: ScenarioKind
) -> ScenarioCopy:
    """Deterministic copy used whenever the model is unavailable."""
    destination = candidate.destination
    duration = _duration_words(request.duration_hours)
    tagline = ARCHETYPE_TAGLINE[kind].format(blurb=destination.blurb, duration=duration)

    reasons: list[str] = []
    if candidate.total_price and candidate.total_price <= request.budget_rub:
        reasons.append("укладывается в бюджет")
    if candidate.transfers == 0:
        reasons.append("без пересадок")
    if candidate.travel_minutes and candidate.travel_minutes < request.duration_hours * 60 * 0.3:
        reasons.append("дорога не съедает поездку")
    for tag in destination.tags[:3]:
        reasons.append(tag)
    if kind is ScenarioKind.SILENCE:
        reasons.append("спокойный ритм")
    elif kind is ScenarioKind.MADNESS:
        reasons.append("плотная программа")
    else:
        reasons.append("неочевидное направление")

    days = max(1, candidate.nights + 1)
    headlines = {
        ScenarioKind.SILENCE: ["Приехать и выдохнуть", "Медленный день", "Дорога назад"],
        ScenarioKind.MADNESS: ["Сразу в город", "Максимум за день", "Последний рывок"],
        ScenarioKind.UNEXPECTED: ["Первое впечатление", "Странное и местное", "Обратно"],
    }[kind]

    return ScenarioCopy(
        tagline=tagline,
        reasons=_dedupe(reasons)[:5],
        why_ai_picked=_template_why(candidate, request, kind),
        day_headlines=headlines[:days],
        activities=activity_pool(candidate),
    )


def _template_why(candidate: Candidate, request: EscapeRequest, kind: ScenarioKind) -> str:
    """Explain the pick using only numbers we actually have."""
    parts: list[str] = []
    goal = {
        ScenarioKind.SILENCE: "минимум стресса и максимум свободного времени",
        ScenarioKind.MADNESS: "максимум впечатлений на доступное время",
        ScenarioKind.UNEXPECTED: "направление, которое обычно не попадает в выдачу",
    }[kind]
    parts.append(f"Этот вариант оптимизирован под {goal}.")

    if candidate.travel_minutes:
        share = candidate.travel_minutes / (request.duration_hours * 60)
        parts.append(f"Дорога занимает около {int(share * 100)}% всей поездки.")
    if candidate.total_price:
        left = request.budget_rub - candidate.total_price
        if left > 0:
            parts.append(f"На месте остаётся примерно {format_rub(left)} на еду и всё остальное.")
        else:
            parts.append("Бюджет использован полностью — запаса почти нет.")
    if candidate.transfers:
        parts.append(f"Пересадок: {candidate.transfers}.")
    return " ".join(parts)


async def write_copy(
    candidate: Candidate,
    request: EscapeRequest,
    intent: NormalizedIntent,
    kind: ScenarioKind,
    llm: LLMClient | None,
) -> ScenarioCopy:
    """LLM copy when possible, template copy otherwise — same shape either way."""
    fallback = template_copy(candidate, request, kind)
    if llm is None or not llm.enabled:
        return fallback

    facts = {
        "scenario": kind.value,
        "city": candidate.destination.name,
        "region": candidate.destination.region,
        "known_for": candidate.destination.blurb,
        "tags": list(candidate.destination.tags),
        "nights": candidate.nights,
        "transport": candidate.kind.value,
        "transfers": candidate.transfers,
        "travel_minutes_total": candidate.travel_minutes or None,
        "total_price_rub": candidate.total_price or None,
        "user": {
            "budget_rub": request.budget_rub,
            "duration_hours": request.duration_hours,
            "moods": [m.value for m in request.moods],
            "wishes": request.wishes,
            "summary": intent.summary,
        },
    }
    generated = await llm.ask_model(
        system=SCENARIO_GENERATION,
        user=json.dumps(facts, ensure_ascii=False),
        schema=ScenarioCopy,
    )
    if generated is None:
        return fallback

    # Never let a thin model answer degrade the card.
    return ScenarioCopy(
        tagline=generated.tagline or fallback.tagline,
        reasons=generated.reasons or fallback.reasons,
        why_ai_picked=generated.why_ai_picked or fallback.why_ai_picked,
        day_headlines=generated.day_headlines or fallback.day_headlines,
        activities=generated.activities or fallback.activities,
    )


# --------------------------------------------------------------------------
# Timeline
# --------------------------------------------------------------------------


def build_itinerary(
    candidate: Candidate,
    copy: ScenarioCopy,
    kind: ScenarioKind,
    start: date,
) -> list[ItineraryDay]:
    """Assemble the visual timeline from real departure times plus activities."""
    days: list[ItineraryDay] = []
    total_days = max(1, candidate.nights + 1)
    activities = list(copy.activities) or activity_pool(candidate)
    per_day = {ScenarioKind.SILENCE: 3, ScenarioKind.MADNESS: 5, ScenarioKind.UNEXPECTED: 4}[kind]
    cursor = 0

    for index in range(total_days):
        current = start + timedelta(days=index)
        events: list[ItineraryEvent] = []
        headline = (
            copy.day_headlines[index]
            if index < len(copy.day_headlines)
            else None
        )

        if index == 0:
            events.extend(_departure_events(candidate))

        slots = _slots(kind, first_day=index == 0, last_day=index == total_days - 1)
        for slot_time, slot_kind in slots:
            if cursor >= len(activities):
                cursor = 0
            if len(events) >= per_day + 2:
                break
            title = activities[cursor]
            cursor += 1
            events.append(
                ItineraryEvent(time=slot_time, title=title, icon=slot_kind)
            )

        if index == total_days - 1:
            events.extend(_return_events(candidate))
        events.sort(key=_event_sort_key)

        days.append(
            ItineraryDay(
                index=index + 1,
                weekday=weekday_name(current),
                date=current,
                headline=headline,
                events=events[:12],
            )
        )
    return days


def _departure_events(candidate: Candidate) -> list[ItineraryEvent]:
    """The outbound leg, using only times MCP gave us."""
    leg = candidate.outbound
    icon = ICON_BY_KIND.get(leg.kind, "train")
    events: list[ItineraryEvent] = []
    segment = leg.segments[0] if leg.segments else None

    departure = segment.departure if segment else None
    arrival = segment.arrival if segment else None

    events.append(
        ItineraryEvent(
            time=_hhmm(departure) or "—",
            title=leg.from_place,
            detail=_leg_detail(leg),
            icon=icon,
        )
    )
    events.append(
        ItineraryEvent(
            time=_hhmm(arrival) or "—",
            title=leg.to_place,
            detail="Приезд" if arrival else "Время приезда придёт из Туту при оформлении",
            icon="view",
        )
    )
    if candidate.hotel is not None:
        events.append(
            ItineraryEvent(
                time="14:00",
                title=f"Заселение — {candidate.hotel.name}",
                detail=candidate.hotel.district,
                icon="hotel",
            )
        )
    return events


def _return_events(candidate: Candidate) -> list[ItineraryEvent]:
    leg = candidate.inbound
    if leg is None:
        return []
    segment = leg.segments[0] if leg.segments else None
    return [
        ItineraryEvent(
            time=_hhmm(segment.departure if segment else None) or "—",
            title=f"{leg.from_place} → {leg.to_place}",
            detail=_leg_detail(leg),
            icon=ICON_BY_KIND.get(leg.kind, "train"),
        )
    ]


def _slots(kind: ScenarioKind, *, first_day: bool, last_day: bool) -> list[tuple[str, str]]:
    """Time slots that encode the pace of each archetype."""
    if kind is ScenarioKind.SILENCE:
        base = [("10:00", "walk"), ("14:00", "free"), ("19:00", "food")]
    elif kind is ScenarioKind.MADNESS:
        base = [("09:00", "walk"), ("12:00", "view"), ("15:00", "walk"), ("18:00", "food"), ("22:00", "night")]
    else:
        base = [("11:00", "view"), ("15:00", "walk"), ("20:00", "food")]
    if first_day:
        base = base[len(base) // 2:]
    if last_day:
        base = base[: max(1, len(base) - 1)]
    return base


def _leg_detail(leg) -> str:
    """'Поезд 104 · РЖД · 3 ч 20 мин' from whatever fields exist."""
    kind_label = {
        TransportKind.TRAIN: "Поезд",
        TransportKind.PLANE: "Рейс",
        TransportKind.BUS: "Автобус",
        TransportKind.SUBURBAN: "Электричка",
        TransportKind.UNKNOWN: "Транспорт",
    }[leg.kind]
    segment = leg.segments[0] if leg.segments else None
    parts = [kind_label]
    if segment and segment.number:
        parts.append(str(segment.number))
    if segment and segment.carrier:
        parts.append(str(segment.carrier))
    if leg.total_duration_minutes:
        hours, minutes = divmod(leg.total_duration_minutes, 60)
        parts.append(f"{hours} ч {minutes} мин" if minutes else f"{hours} ч")
    return " · ".join(parts)


def _hhmm(value: datetime | None) -> str | None:
    return value.strftime("%H:%M") if value else None


def _event_sort_key(event: ItineraryEvent) -> tuple[int, int]:
    """Sort real clock times first; keep soft labels and placeholders last."""
    parts = event.time.split(":", 1)
    if len(parts) == 2 and all(part.isdigit() for part in parts):
        hours, minutes = int(parts[0]), int(parts[1])
        if 0 <= hours <= 23 and 0 <= minutes <= 59:
            return (0, hours * 60 + minutes)
    return (1, 24 * 60)


def _duration_words(hours: int) -> str:
    if hours < 24:
        return f"{hours} часов"
    days = round(hours / 24)
    return f"{days} дня" if days in (2, 3, 4) else f"{days} дней" if days > 4 else "день"


def _dedupe(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        cleaned = item.strip().lower()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def stay_summary(candidate: Candidate) -> str:
    """'2 ночи · Отель на Соборной' for the card subtitle."""
    if candidate.nights <= 0:
        return "без ночёвки"
    if candidate.hotel is None:
        return plural_nights(candidate.nights)
    return f"{plural_nights(candidate.nights)} · {candidate.hotel.name}"


def date_line(start: date, nights: int) -> str:
    """Human date range for the detail page."""
    end = start + timedelta(days=max(nights, 0))
    return f"{format_date(start)} — {format_date(end)}" if nights else format_date(start)
