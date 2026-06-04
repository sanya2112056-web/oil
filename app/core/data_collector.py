"""Збір ринкового знімка: ціни WTI/Brent, запаси, індекс долара, макро.

Тягне з усіх доступних ринкових джерел; недоступні (без ключа) тихо
пропускаються. Повертає (snapshot, unavailable) — словник показників та
список джерел, яких не вистачає (для прозорості в аналізі та health).
"""
from __future__ import annotations

import asyncio

import httpx

from app.sources.market import ALL_MARKET_SOURCES
from app.utils.log import get_logger, record_event

log = get_logger("core.data")


async def collect_market_snapshot() -> tuple[dict, list[str]]:
    snapshot: dict = {}
    unavailable: list[str] = []
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True,
                                 headers={"User-Agent": "OilScaner/1.0"}) as client:
        coros = []
        active = []
        for src in ALL_MARKET_SOURCES:
            if src.info.env_var is not None and not src.info.is_configured():
                unavailable.append(src.info.name)
                continue
            active.append(src)
            coros.append(src.fetch(client))
        results = await asyncio.gather(*coros, return_exceptions=True)

    for src, res in zip(active, results):
        if isinstance(res, Exception):
            record_event("warn", src.info.key, f"data: {res}")
            unavailable.append(f"{src.info.name} (помилка)")
            continue
        if isinstance(res, dict):
            snapshot.update(res)
    return snapshot, unavailable


def best_wti_price(snapshot: dict) -> float | None:
    """Обирає найнадійнішу доступну ціну WTI зі знімка."""
    for key in ("WTI_price", "FRED_WTI", "TwelveData_WTI", "AV_WTI", "CommAPI_WTI"):
        v = snapshot.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    return None
