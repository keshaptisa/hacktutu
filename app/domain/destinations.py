"""Destination shortlist knowledge base.

ESCAPE's whole premise is that the user does *not* name a city. Something must
therefore decide **where to ask Tutu about**. That is this module's only job:
it turns (origin, hours, moods, wishes) into a ranked shortlist of candidate
cities, which the MCP layer then verifies with real prices and real schedules.

Nothing here is presented to the user as a fact about a trip. Reach times are
coarse planning estimates used for shortlisting only; the actual duration,
price and availability always come back from Tutu MCP.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.models import Mood, TransportKind


@dataclass(frozen=True)
class Destination:
    """A candidate city with the traits we shortlist on."""

    name: str
    region: str
    moods: tuple[Mood, ...]
    tags: tuple[str, ...]
    # Rough reach time in hours from each supported origin, by transport mode.
    reach: dict[str, dict[TransportKind, float]] = field(default_factory=dict)
    novelty: int = 50  # 0 = everyone goes there, 100 = almost nobody does
    blurb: str = ""

    def reach_from(self, origin: str) -> dict[TransportKind, float]:
        return self.reach.get(origin, {})


M = Mood
T = TransportKind


def _r(**kwargs: dict[TransportKind, float]) -> dict[str, dict[TransportKind, float]]:
    return dict(kwargs)


DESTINATIONS: tuple[Destination, ...] = (
    Destination(
        "Ярославль", "Золотое кольцо",
        (M.SILENCE, M.IMPRESSIONS, M.ROMANCE),
        ("исторический", "набережная", "медленно", "зима", "волга"),
        _r(Москва={T.TRAIN: 3.3, T.BUS: 5.0}, Санкт_Петербург={T.TRAIN: 12.0}),
        novelty=35,
        blurb="Волжская набережная, Спасский монастырь и очень тихие вечера.",
    ),
    Destination(
        "Суздаль", "Владимирская область",
        (M.SILENCE, M.ROMANCE, M.IMPRESSIONS),
        ("исторический", "деревянное зодчество", "зима", "медленно", "еда"),
        _r(Москва={T.TRAIN: 2.5, T.BUS: 4.0}),
        novelty=45,
        blurb="Город без многоэтажек: валы, купола и медовуха.",
    ),
    Destination(
        "Псков", "Псковская область",
        (M.SILENCE, M.IMPRESSIONS),
        ("исторический", "крепость", "зима", "тишина", "древний"),
        _r(Москва={T.TRAIN: 11.5, T.PLANE: 1.5}, Санкт_Петербург={T.TRAIN: 3.5, T.BUS: 4.5}),
        novelty=65,
        blurb="Кром над Великой, самые старые фрески страны и почти нет туристов.",
    ),
    Destination(
        "Великий Новгород", "Новгородская область",
        (M.SILENCE, M.IMPRESSIONS, M.ROMANCE),
        ("исторический", "древний", "кремль", "зима", "река"),
        _r(Москва={T.TRAIN: 7.5, T.BUS: 8.0}, Санкт_Петербург={T.TRAIN: 3.0, T.BUS: 3.5}),
        novelty=55,
        blurb="Софийский собор XI века и Ярославово дворище в двадцати минутах пешком.",
    ),
    Destination(
        "Санкт-Петербург", "Северо-Запад",
        (M.IMPRESSIONS, M.NIGHTLIFE, M.ROMANCE, M.ENERGY),
        ("исторический", "музеи", "бары", "море", "зима", "красиво"),
        _r(Москва={T.TRAIN: 4.0, T.PLANE: 1.5, T.BUS: 10.0}),
        novelty=15,
        blurb="Единственный город, где можно за сутки собрать музеи, залив и бары на Рубинштейна.",
    ),
    Destination(
        "Казань", "Татарстан",
        (M.IMPRESSIONS, M.ENERGY, M.NIGHTLIFE),
        ("еда", "необычно", "исторический", "кремль", "зима"),
        _r(Москва={T.TRAIN: 11.5, T.PLANE: 1.7}, Санкт_Петербург={T.PLANE: 2.3}),
        novelty=30,
        blurb="Кремль, эчпочмаки и набережная Казанки — плотно и вкусно.",
    ),
    Destination(
        "Нижний Новгород", "Поволжье",
        (M.IMPRESSIONS, M.ENERGY, M.NIGHTLIFE),
        ("набережная", "стрелка", "закат", "необычно", "зима"),
        _r(Москва={T.TRAIN: 3.6, T.PLANE: 1.4, T.BUS: 6.5}),
        novelty=35,
        blurb="Чкаловская лестница, Стрелка и лучший в стране городской закат.",
    ),
    Destination(
        "Тула", "Тульская область",
        (M.IMPRESSIONS, M.SPONTANEITY),
        ("еда", "исторический", "недорого", "близко", "зима"),
        _r(Москва={T.TRAIN: 2.3, T.BUS: 3.5}),
        novelty=50,
        blurb="Кремль, Казанская набережная и пряники, ради которых стоит ехать два часа.",
    ),
    Destination(
        "Калуга", "Калужская область",
        (M.SILENCE, M.IMPRESSIONS, M.SPONTANEITY),
        ("космос", "необычно", "недорого", "близко"),
        _r(Москва={T.TRAIN: 2.5, T.BUS: 3.0}),
        novelty=70,
        blurb="Музей космонавтики и старый город над Окой — редкая комбинация.",
    ),
    Destination(
        "Владимир", "Владимирская область",
        (M.SILENCE, M.IMPRESSIONS),
        ("исторический", "древний", "недорого", "зима", "близко"),
        _r(Москва={T.TRAIN: 1.8, T.BUS: 3.5}),
        novelty=40,
        blurb="Белокаменные соборы XII века в полутора часах от Курского.",
    ),
    Destination(
        "Кострома", "Золотое кольцо",
        (M.SILENCE, M.ROMANCE),
        ("исторический", "волга", "зима", "медленно", "недорого"),
        _r(Москва={T.TRAIN: 6.0, T.BUS: 7.0}),
        novelty=60,
        blurb="Сусанинская площадь, Ипатьевский монастырь и настоящая зимняя тишина.",
    ),
    Destination(
        "Рыбинск", "Ярославская область",
        (M.SILENCE, M.SPONTANEITY),
        ("необычно", "вывески", "волга", "недорого", "тишина"),
        _r(Москва={T.TRAIN: 6.5, T.BUS: 7.5}),
        novelty=90,
        blurb="Город, который вернул себе дореволюционные вывески. Выглядит как декорация.",
    ),
    Destination(
        "Выборг", "Ленинградская область",
        (M.IMPRESSIONS, M.ROMANCE, M.SPONTANEITY),
        ("необычно", "замок", "море", "скалы", "европа"),
        _r(Санкт_Петербург={T.TRAIN: 1.3, T.SUBURBAN: 2.5}, Москва={T.TRAIN: 10.0}),
        novelty=75,
        blurb="Единственный средневековый замок России и парк Монрепо на скалах.",
    ),
    Destination(
        "Калининград", "Калининградская область",
        (M.IMPRESSIONS, M.ROMANCE, M.SPONTANEITY),
        ("море", "европа", "необычно", "красиво"),
        _r(Москва={T.PLANE: 2.2}, Санкт_Петербург={T.PLANE: 1.8}),
        novelty=55,
        blurb="Немецкая кирпичная готика, куршские дюны и Балтика в шаговой доступности.",
    ),
    Destination(
        "Сочи", "Краснодарский край",
        (M.ENERGY, M.ROMANCE, M.NIGHTLIFE),
        ("море", "горы", "тепло", "красиво"),
        _r(Москва={T.PLANE: 2.5, T.TRAIN: 24.0}, Санкт_Петербург={T.PLANE: 3.3}),
        novelty=20,
        blurb="Море и горы в одном дне: Красная Поляна утром, набережная вечером.",
    ),
    Destination(
        "Мурманск", "Заполярье",
        (M.IMPRESSIONS, M.SPONTANEITY),
        ("север", "необычно", "северное сияние", "зима", "море"),
        _r(Москва={T.PLANE: 2.5, T.TRAIN: 34.0}, Санкт_Петербург={T.PLANE: 2.2}),
        novelty=85,
        blurb="Полярная ночь, Териберка и сияние, если повезёт с небом.",
    ),
    Destination(
        "Петрозаводск", "Карелия",
        (M.SILENCE, M.IMPRESSIONS),
        ("природа", "озеро", "север", "тишина", "зима"),
        _r(Санкт_Петербург={T.TRAIN: 5.0}, Москва={T.TRAIN: 13.5, T.PLANE: 2.0}),
        novelty=70,
        blurb="Онежская набережная со странными скульптурами и выход к Кижам.",
    ),
    Destination(
        "Вологда", "Вологодская область",
        (M.SILENCE, M.IMPRESSIONS),
        ("исторический", "деревянное зодчество", "зима", "тишина", "недорого"),
        _r(Москва={T.TRAIN: 7.5}, Санкт_Петербург={T.TRAIN: 12.0}),
        novelty=75,
        blurb="Деревянные особняки, кремль и абсолютно негромкий ритм.",
    ),
    Destination(
        "Коломна", "Московская область",
        (M.SILENCE, M.SPONTANEITY, M.ROMANCE),
        ("близко", "еда", "исторический", "недорого", "без машины"),
        _r(Москва={T.SUBURBAN: 2.2, T.TRAIN: 1.8, T.BUS: 2.5}),
        novelty=65,
        blurb="Кремль, пастила и обратный поезд, на который всегда успеваешь.",
    ),
    Destination(
        "Сергиев Посад", "Московская область",
        (M.SILENCE, M.IMPRESSIONS),
        ("близко", "исторический", "недорого", "без машины", "зима"),
        _r(Москва={T.SUBURBAN: 1.5, T.TRAIN: 1.2}),
        novelty=40,
        blurb="Лавра целиком помещается в один неспешный день.",
    ),
    Destination(
        "Плёс", "Ивановская область",
        (M.SILENCE, M.ROMANCE),
        ("волга", "природа", "красиво", "тишина", "медленно"),
        _r(Москва={T.BUS: 6.5, T.TRAIN: 5.5}),
        novelty=80,
        blurb="Левитановские холмы над Волгой. Тут буквально нечего делать, и в этом суть.",
    ),
    Destination(
        "Екатеринбург", "Урал",
        (M.ENERGY, M.NIGHTLIFE, M.IMPRESSIONS),
        ("конструктивизм", "бары", "необычно", "город"),
        _r(Москва={T.PLANE: 2.5, T.TRAIN: 26.0}, Санкт_Петербург={T.PLANE: 2.8}),
        novelty=60,
        blurb="Конструктивизм, стрит-арт и бары, которые работают до последнего гостя.",
    ),
    Destination(
        "Тбилиси", "Грузия",
        (M.ENERGY, M.NIGHTLIFE, M.IMPRESSIONS, M.ROMANCE),
        ("еда", "вино", "тепло", "необычно", "заграница"),
        _r(Москва={T.PLANE: 3.0}, Санкт_Петербург={T.PLANE: 3.7}),
        novelty=50,
        blurb="Серные бани, балконы Сололаки и ужины, которые заканчиваются под утро.",
    ),
    Destination(
        "Минск", "Беларусь",
        (M.IMPRESSIONS, M.SPONTANEITY),
        ("необычно", "недорого", "заграница", "город", "еда"),
        _r(Москва={T.TRAIN: 9.0, T.PLANE: 1.5}, Санкт_Петербург={T.TRAIN: 14.0}),
        novelty=65,
        blurb="Сталинский ампир проспекта Независимости и очень дешёвые ужины.",
    ),
    Destination(
        "Кисловодск", "Кавказские Минеральные Воды",
        (M.SILENCE, M.ROMANCE),
        ("природа", "горы", "тепло", "медленно", "парк"),
        _r(Москва={T.TRAIN: 24.0, T.PLANE: 2.5}),
        novelty=70,
        blurb="Самый большой рукотворный парк Европы и воздух, ради которого сюда едут сто лет.",
    ),
    Destination(
        "Пермь", "Урал",
        (M.SPONTANEITY, M.IMPRESSIONS, M.ENERGY),
        ("необычно", "арт", "кама", "город"),
        _r(Москва={T.PLANE: 2.2, T.TRAIN: 20.0}),
        novelty=80,
        blurb="Красные человечки, «Счастье не за горами» и очень странная городская сцена.",
    ),
    Destination(
        "Тверь", "Тверская область",
        (M.SPONTANEITY, M.SILENCE),
        ("близко", "недорого", "волга", "без машины"),
        _r(Москва={T.TRAIN: 1.0, T.SUBURBAN: 2.5, T.BUS: 3.0}),
        novelty=55,
        blurb="Час на «Ласточке» — и вы уже гуляете по набережной Степана Разина.",
    ),
    Destination(
        "Смоленск", "Смоленская область",
        (M.IMPRESSIONS, M.SILENCE),
        ("крепость", "исторический", "недорого", "зима"),
        _r(Москва={T.TRAIN: 4.5, T.BUS: 6.0}),
        novelty=75,
        blurb="Самая длинная сохранившаяся крепостная стена страны и почти пустые улицы.",
    ),
    Destination(
        "Иркутск", "Сибирь",
        (M.IMPRESSIONS, M.SPONTANEITY),
        ("байкал", "природа", "необычно", "зима", "далеко"),
        _r(Москва={T.PLANE: 5.8}),
        novelty=85,
        blurb="Ворота к Байкалу: лёд, деревянные кварталы и шесть часов лёта.",
    ),
    Destination(
        "Ростов Великий", "Ярославская область",
        (M.SILENCE, M.ROMANCE),
        ("исторический", "озеро", "недорого", "тишина", "зима"),
        _r(Москва={T.TRAIN: 3.0, T.BUS: 4.0}),
        novelty=70,
        blurb="Кремль на берегу Неро — тот самый, из «Ивана Васильевича».",
    ),
)


DESTINATIONS_BY_NAME: dict[str, Destination] = {d.name.lower(): d for d in DESTINATIONS}

ORIGIN_ALIASES: dict[str, str] = {
    "москва": "Москва",
    "мск": "Москва",
    "moscow": "Москва",
    "санкт-петербург": "Санкт_Петербург",
    "спб": "Санкт_Петербург",
    "питер": "Санкт_Петербург",
    "петербург": "Санкт_Петербург",
    "saint petersburg": "Санкт_Петербург",
}

ORIGIN_DISPLAY: dict[str, str] = {
    "Москва": "Москва",
    "Санкт_Петербург": "Санкт-Петербург",
}


def clean_origin_name(value: str | None) -> str:
    """User-facing origin: preserve manual input, normalize only known aliases."""
    if not value:
        return "Москва"
    text = " ".join(value.strip().split())
    if not text:
        return "Москва"
    known = ORIGIN_ALIASES.get(text.lower())
    if known:
        return origin_display_name(known)
    return text[:64]


def normalize_origin(value: str | None) -> str:
    """Map any spelling of the origin onto a catalog key."""
    if not value:
        return "Москва"
    return ORIGIN_ALIASES.get(value.strip().lower(), "Москва")


def origin_display_name(origin_key: str) -> str:
    """Human-readable origin for the UI."""
    return ORIGIN_DISPLAY.get(origin_key, origin_key.replace("_", "-"))


def find_destination(name: str) -> Destination | None:
    """Case-insensitive lookup, tolerant of minor spelling noise."""
    key = name.strip().lower()
    if key in DESTINATIONS_BY_NAME:
        return DESTINATIONS_BY_NAME[key]
    for stored, dest in DESTINATIONS_BY_NAME.items():
        if stored.startswith(key) or key.startswith(stored):
            return dest
    return None
