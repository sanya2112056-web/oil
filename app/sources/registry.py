"""Єдиний реєстр усіх джерел: для health-check та списку API."""
from __future__ import annotations

import asyncio

import httpx

from app.sources.base import HealthResult, HealthStatus, SourceInfo
from app.sources.market import ALL_MARKET_SOURCES
from app.sources.news import ALL_NEWS_SOURCES

# Усі джерела разом
ALL_SOURCES = ALL_NEWS_SOURCES + ALL_MARKET_SOURCES

# «Core»-сервіси (не джерела даних, але потрібні в health/списку)
CORE_SERVICES = [
    SourceInfo("telegram", "Telegram Bot", "core", "TELEGRAM_BOT_TOKEN",
               "https://t.me/BotFather", "ОБОВ'ЯЗКОВО — токен бота"),
    SourceInfo("anthropic", "Anthropic (Claude)", "core", "ANTHROPIC_API_KEY",
               "https://console.anthropic.com/", "ОБОВ'ЯЗКОВО — мозок аналізу"),
]


async def check_all_health(timeout: float = 15.0) -> list[HealthResult]:
    """Паралельно перевіряє всі джерела даних і повертає статуси."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True,
                                 headers={"User-Agent": "OilScaner/1.0"}) as client:
        results = await asyncio.gather(
            *[s.health_check(client) for s in ALL_SOURCES],
            return_exceptions=True,
        )
    out: list[HealthResult] = []
    for s, res in zip(ALL_SOURCES, results):
        if isinstance(res, HealthResult):
            out.append(res)
        else:
            out.append(HealthResult(s.info, HealthStatus.ERROR, str(res)[:160]))
    return out


def core_health() -> list[HealthResult]:
    """Статус обов'язкових core-сервісів (без мережевого запиту)."""
    out = []
    for info in CORE_SERVICES:
        status = HealthStatus.OK if info.is_configured() else HealthStatus.NOT_CONFIGURED
        detail = "налаштовано" if info.is_configured() else "КЛЮЧ ВІДСУТНІЙ"
        out.append(HealthResult(info, status, detail))
    return out


def all_source_infos() -> list[SourceInfo]:
    """Усі джерела + core — для повного списку API."""
    return CORE_SERVICES + [s.info for s in ALL_SOURCES]
