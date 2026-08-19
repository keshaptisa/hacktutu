"""Lightweight Russian text handling for the free-form wish fields.

Deliberately dependency-free: a hackathon server should not need pymorphy just
to notice that "исторический" and "история" mean the same thing. Stemming here
is a crude suffix trim, which is enough for tag matching and is fully testable.
"""

from __future__ import annotations

import re
import unicodedata

from app.domain.models import Mood, TransportKind

_WORD_RE = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)

_SUFFIXES = (
    "ическими", "ический", "ическая", "ическое", "ические",
    "ования", "ованию", "ами", "ями", "ого", "его", "ому", "ему",
    "ых", "их", "ая", "яя", "ое", "ее", "ые", "ие", "ой", "ей",
    "ом", "ем", "ов", "ев", "ам", "ям", "ах", "ях", "ий", "ый",
    "у", "ю", "а", "я", "ы", "и", "о", "е", "ь",
)

STOPWORDS = frozenset(
    """и в во не что он на я с со как а то все она так его но да ты к у же вы за
    бы по только ее мне было вот от меня еще нет о из ему теперь когда даже ну
    вдруг ли если или чтоб хочу хочется надо нужно можно очень мой моя мои есть
    быть будет для про чуть более менее без при""".split()
)


def normalize(text: str) -> str:
    """Lowercase, unify ё/е and collapse whitespace."""
    text = unicodedata.normalize("NFKC", text or "").lower().replace("ё", "е")
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> list[str]:
    """Meaningful lowercase tokens from free text."""
    return [t for t in _WORD_RE.findall(normalize(text)) if t not in STOPWORDS]


def stem(word: str) -> str:
    """Crude suffix trim. Good enough for tag overlap, cheap and predictable."""
    word = normalize(word)
    if len(word) <= 4:
        return word
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def stems(text: str) -> set[str]:
    """Stem set for a phrase."""
    return {stem(token) for token in tokens(text)}


def overlap_score(wish_text: str, tags: tuple[str, ...] | list[str]) -> float:
    """Share of wish stems that match a destination's tags (0..1)."""
    wish_stems = stems(wish_text)
    if not wish_stems:
        return 0.0
    tag_stems: set[str] = set()
    for tag in tags:
        tag_stems |= stems(tag)
    hits = sum(1 for s in wish_stems if any(s.startswith(t) or t.startswith(s) for t in tag_stems))
    return min(1.0, hits / len(wish_stems))


# --------------------------------------------------------------------------
# Signal extraction
# --------------------------------------------------------------------------

MOOD_KEYWORDS: dict[Mood, tuple[str, ...]] = {
    Mood.SILENCE: ("тишина", "спокойно", "медленно", "отдых", "природа", "уединение", "выдохнуть"),
    Mood.ENERGY: ("энергия", "активно", "спорт", "драйв", "движение", "горы"),
    Mood.ROMANCE: ("романтика", "вдвоем", "свидание", "красиво", "закат"),
    Mood.SPONTANEITY: ("спонтанно", "неожиданно", "куда угодно", "рандом", "необычно"),
    Mood.NIGHTLIFE: ("бары", "клубы", "ночная", "тусовка", "вечеринка"),
    Mood.IMPRESSIONS: ("музеи", "история", "исторический", "архитектура", "впечатления", "экскурсии"),
}

TRANSPORT_KEYWORDS: dict[TransportKind, tuple[str, ...]] = {
    TransportKind.TRAIN: ("поезд", "жд", "ласточка", "сапсан", "купе", "плацкарт"),
    TransportKind.PLANE: ("самолет", "перелет", "рейс", "лететь", "авиа"),
    TransportKind.BUS: ("автобус", "маршрутка"),
    TransportKind.SUBURBAN: ("электричка", "пригородный"),
}

NEGATIVE_MARKERS = ("без ", "не ", "нет ", "кроме ", "избегать")

SEA_WORDS = ("море", "океан", "пляж", "прибой")
WARM_WORDS = ("тепло", "жара", "лето", "юг")
CHEAP_WORDS = ("недорого", "дешево", "бюджетно", "мало денег", "экономно")
NO_CAR_WORDS = ("без машины", "без авто", "нет машины", "не за рулем")
DAYTIME_WORDS = ("днем", "дневной", "не ночью", "не ночной", "утренний")


def infer_moods(wishes: list[str]) -> list[Mood]:
    """Moods hinted at by the free-text fields (used only as a soft fallback
    when no LLM is configured; the model-based path in ai/normalizer.py is
    the primary reader of free text).
    """
    wish_stems = stems(" ".join(wishes))
    found: list[Mood] = []
    for mood, keys in MOOD_KEYWORDS.items():
        key_stems = {stem(k) for phrase in keys for k in phrase.split()}
        if wish_stems & key_stems and mood not in found:
            found.append(mood)
    return found


def infer_transport(wishes: list[str]) -> tuple[set[TransportKind], set[TransportKind]]:
    """Return ``(preferred, avoided)`` transport modes mentioned in the wishes."""
    blob = normalize(" ".join(wishes))
    preferred: set[TransportKind] = set()
    avoided: set[TransportKind] = set()
    for kind, keys in TRANSPORT_KEYWORDS.items():
        for key in keys:
            position = blob.find(key)
            if position == -1:
                continue
            prefix = blob[max(0, position - 12): position]
            if any(marker in prefix for marker in NEGATIVE_MARKERS):
                avoided.add(kind)
            else:
                preferred.add(kind)
    return preferred - avoided, avoided


def mentions_any(wishes: list[str], words: tuple[str, ...]) -> bool:
    """True when any of the words appears in the wishes."""
    blob = normalize(" ".join(wishes))
    return any(word in blob for word in words)


def extract_city_mentions(wishes: list[str], known: dict[str, object]) -> list[str]:
    """Cities from the catalog that the user named directly."""
    blob = normalize(" ".join(wishes))
    found: list[str] = []
    for city_key in known:
        if city_key in blob and city_key not in found:
            found.append(city_key)
    return found


def truncate(text: str, limit: int = 160) -> str:
    """Trim to a clean sentence-ish boundary."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"
