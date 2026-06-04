"""Фільтр релевантності: чи дотична новина до нафти + оцінка важливості (1..10)."""
from __future__ import annotations

from app.sources.base import NewsItem

# Базові нафтові терміни (без них новина не релевантна)
OIL_TERMS = [
    "oil", "crude", "wti", "brent", "opec", "petroleum", "barrel", "barrels",
    "refinery", "refineries", "shale", "нафт", "brent", "нефт",
]

# Сигнали високої важливості (різкий рух): геополітика, пропозиція, ціна
HIGH_SIGNAL = {
    "hormuz": 4, "strait of hormuz": 5, "iran": 3, "israel": 2, "tehran": 3,
    "opec+": 4, "opec cut": 4, "production cut": 4, "supply cut": 4,
    "sanction": 3, "embargo": 3, "attack": 3, "strike": 2, "tanker": 3,
    "pipeline": 2, "outage": 3, "disruption": 3, "war": 3, "missile": 3,
    "drone": 2, "blockade": 4, "ceasefire": 3, "de-escalat": 3, "deescalat": 3,
    "inventory": 2, "inventories": 2, "stockpile": 2, "draw": 2, "build": 2,
    "eia": 2, "api report": 2, "rig count": 1, "saudi": 2, "russia": 2,
    "venezuela": 2, "libya": 2, "nigeria": 1, "surge": 2, "plunge": 2,
    "soar": 2, "spike": 2, "rally": 1, "crash": 2, "demand": 1, "recession": 2,
    "fed": 1, "rate cut": 1, "dollar": 1, "нафт": 1, "ормуз": 4, "іран": 3,
}


def is_oil_related(item: NewsItem) -> bool:
    text = f"{item.title} {item.summary}".lower()
    return any(term in text for term in OIL_TERMS)


def importance(item: NewsItem) -> int:
    """Оцінка 1..10. Базово 2; додаються бали за тригерні слова."""
    text = f"{item.title} {item.summary}".lower()
    score = 2
    for kw, w in HIGH_SIGNAL.items():
        if kw in text:
            score += w
    return max(1, min(10, score))
