"""Збір новин з усіх джерел + фільтр релевантності + дедуп."""
from __future__ import annotations

import asyncio

import httpx

from app.core.relevance import importance, is_oil_related
from app.sources.base import NewsItem
from app.sources.news import ALL_NEWS_SOURCES
from app.utils.log import get_logger, record_event

log = get_logger("core.news")


async def collect_all_news() -> list[NewsItem]:
    """Тягне новини з усіх доступних джерел паралельно (помилки ігноруються)."""
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True,
                                 headers={"User-Agent": "OilScaner/1.0"}) as client:
        results = await asyncio.gather(
            *[s.fetch(client) for s in ALL_NEWS_SOURCES],
            return_exceptions=True,
        )
    items: list[NewsItem] = []
    for src, res in zip(ALL_NEWS_SOURCES, results):
        if isinstance(res, Exception):
            record_event("warn", src.info.key, f"fetch: {res}")
            continue
        items.extend(res)
    return items


def filter_relevant(items: list[NewsItem]) -> list[NewsItem]:
    """Лишає лише нафто-дотичні, прибирає дублі в межах партії за заголовком."""
    seen_titles: set[str] = set()
    out: list[NewsItem] = []
    for it in items:
        if not it.title or not is_oil_related(it):
            continue
        norm = it.title.strip().lower()[:120]
        if norm in seen_titles:
            continue
        seen_titles.add(norm)
        out.append(it)
    # найважливіші — першими
    out.sort(key=importance, reverse=True)
    return out
