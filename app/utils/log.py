"""Просте логування + кільцевий буфер останніх помилок для AI-асистента."""
from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)

# python-telegram-bot та httpx дуже балакучі на DEBUG/INFO — приглушуємо
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

# Останні помилки/події (для діагностики через AI-асистента та health)
_RECENT: deque[dict] = deque(maxlen=60)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def record_event(level: str, source: str, message: str) -> None:
    """Зберегти подію у кільцевий буфер (показується асистенту/в health)."""
    _RECENT.append(
        {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "level": level,
            "source": source,
            "message": message[:500],
        }
    )


def recent_events(limit: int = 20) -> list[dict]:
    return list(_RECENT)[-limit:]
