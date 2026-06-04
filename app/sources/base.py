"""Базові типи для джерел даних: новини, ринок, health-статус."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class HealthStatus(str, Enum):
    OK = "ok"                      # ✅ ключ є і джерело відповіло
    ERROR = "error"               # ⚠️ ключ є, але сталася помилка
    NOT_CONFIGURED = "not_set"    # ⛔ ключ не доданий
    NO_KEY_NEEDED = "no_key"      # 🆓 ключ не потрібен (RSS / yfinance)


@dataclass
class NewsItem:
    """Уніфікована новина з будь-якого джерела."""
    title: str
    url: str
    source: str               # назва джерела (NewsAPI, RSS:OilPrice, ...)
    summary: str = ""
    published: str = ""       # ISO-час, якщо відомо

    def dedup_key(self) -> str:
        import hashlib

        base = (self.url or self.title).strip().lower()
        return hashlib.sha256(base.encode("utf-8", "ignore")).hexdigest()[:32]


@dataclass
class SourceInfo:
    """Метадані джерела для реєстру / health-check / списку API."""
    key: str                  # унікальний ідентифікатор (newsapi, eia, ...)
    name: str                 # людська назва
    category: str             # news | market | core
    env_var: Optional[str]    # назва env-змінної з ключем (None = ключ не потрібен)
    signup_url: str = ""      # де взяти ключ
    note: str = ""            # короткий опис

    def is_configured(self) -> bool:
        if self.env_var is None:
            return True
        return bool((os.getenv(self.env_var) or "").strip())


@dataclass
class HealthResult:
    info: SourceInfo
    status: HealthStatus
    detail: str = ""
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    @property
    def emoji(self) -> str:
        return {
            HealthStatus.OK: "✅",
            HealthStatus.ERROR: "⚠️",
            HealthStatus.NOT_CONFIGURED: "⛔",
            HealthStatus.NO_KEY_NEEDED: "🆓",
        }[self.status]
