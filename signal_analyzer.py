"""
signal_analyzer.py — оцінює новини та генерує торгові сигнали.

Алгоритм:
  1. Підраховуємо суму ваг BULLISH / BEARISH ключових слів у заголовку.
  2. Враховуємо вагу джерела (Reuters = 1.0, блог = 0.3, …).
  3. Враховуємо свіжість статті (recency factor).
  4. Розраховуємо confidence 0–100%.
  5. Повертаємо сигнал лише якщо confidence ≥ SIGNAL_THRESHOLD.
"""

import logging
from datetime import datetime, timezone

import config

log = logging.getLogger("signal_analyzer")


# ─────────────────────────────────────────────────────────────────────────────
# Допоміжні функції
# ─────────────────────────────────────────────────────────────────────────────

def _source_weight(source: str) -> float:
    """Повертає вагу довіри до джерела."""
    s = (source or "").lower()
    for key, w in config.SOURCE_WEIGHTS.items():
        if key in s:
            return w
    return 0.6   # за замовчуванням — невідоме джерело


def _recency_factor(published: str) -> float:
    """
    Чим свіжіша новина, тим вищий коефіцієнт.
    Повертає 1.0 (<30 хв), 0.85 (<2 год), 0.65 (<6 год), 0.4 (>6 год).
    """
    if not published:
        return 0.75   # невідомий час → середня свіжість

    now = datetime.now(timezone.utc)
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",   # RSS типовий формат
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y%m%dT%H%M%S",              # Alpha Vantage
    ):
        try:
            dt = datetime.strptime(published, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_min = (now - dt).total_seconds() / 60
            if age_min < 30:
                return 1.0
            if age_min < 120:
                return 0.85
            if age_min < 360:
                return 0.65
            return 0.4
        except ValueError:
            continue
    return 0.75


def _price_reaction(confidence: int, direction: str) -> tuple[str, str]:
    """
    Повертає орієнтовний % руху ціни та рекомендований таймфрейм
    залежно від впевненості сигналу.
    """
    if confidence >= 85:
        move = "2–5%"
        tf   = "M15 / H1"
    elif confidence >= 70:
        move = "1–2.5%"
        tf   = "M15 / H1"
    else:
        move = "0.5–1.5%"
        tf   = "H1 / H4"

    arrow = "↑" if direction == "BULLISH" else "↓"
    return f"{arrow} ~{move}", tf


def _reaction_time(confidence: int, source: str) -> str:
    """Типовий час реакції ринку."""
    src = (source or "").lower()
    if "eia" in src or "opec" in src:
        return "5–15 хв (офіційні дані)"
    if confidence >= 80:
        return "15–30 хв"
    return "30–90 хв"


# ─────────────────────────────────────────────────────────────────────────────
# Основні функції
# ─────────────────────────────────────────────────────────────────────────────

def score_item(item: dict) -> dict | None:
    """
    Оцінює одну новину.
    Повертає словник із сигналом або None, якщо новина нерелевантна.
    """
    title = (item.get("title") or "").lower()
    raw   = 0.0
    hits  = []

    for kw, w in config.BULLISH.items():
        if kw in title:
            raw  += w
            hits.append(f"+{kw}")

    for kw, w in config.BEARISH.items():
        if kw in title:
            raw  -= w
            hits.append(f"-{kw}")

    # Враховуємо готовий сентимент від Alpha Vantage (-1..+1 → ±5)
    if "av_sentiment" in item:
        try:
            av = float(item["av_sentiment"])
            raw += av * 5
            if av > 0.15:
                hits.append(f"+AV_sentiment({av:.2f})")
            elif av < -0.15:
                hits.append(f"-AV_sentiment({av:.2f})")
        except (TypeError, ValueError):
            pass

    if raw == 0:
        return None   # нейтральна новина

    direction = "BULLISH" if raw > 0 else "BEARISH"

    magnitude        = min(abs(raw), 15) / 15          # 0..1
    source_w         = _source_weight(item.get("source"))
    recency_w        = _recency_factor(item.get("published", ""))
    confidence       = round(magnitude * source_w * recency_w * 100)
    confidence       = max(1, min(confidence, 99))

    price_move, tf   = _price_reaction(confidence, direction)
    reaction_time    = _reaction_time(confidence, item.get("source", ""))

    return {
        "direction":     direction,
        "confidence":    confidence,
        "hits":          hits,
        "title":         item.get("title", ""),
        "source":        item.get("source", ""),
        "url":           item.get("url", ""),
        "price_move":    price_move,
        "timeframe":     tf,
        "reaction_time": reaction_time,
    }


def analyze(items: list[dict]) -> list[dict]:
    """Оцінює список новин, повертає відсортований список сигналів."""
    scored = [s for s in (score_item(i) for i in items) if s]
    scored.sort(key=lambda x: x["confidence"], reverse=True)
    return scored


def best_signal(items: list[dict], threshold: int = None) -> dict | None:
    """
    Повертає найкращий сигнал, якщо його впевненість ≥ threshold.
    Для EIA/OPEC поріг знижується до 55%.
    """
    thr     = threshold or config.SIGNAL_THRESHOLD
    scored  = analyze(items)

    if not scored:
        return None

    top = scored[0]
    src = (top.get("source") or "").lower()

    # Офіційні джерела — нижчий поріг
    eff_thr = 55 if ("eia" in src or "opec" in src) else thr

    if top["confidence"] >= eff_thr:
        return top
    return None
