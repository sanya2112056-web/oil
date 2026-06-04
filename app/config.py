"""Завантаження конфігурації з оточення. Жоден опційний ключ не є обов'язковим."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _get_int(name: str, default: int) -> int:
    try:
        return int(_get(name) or default)
    except (TypeError, ValueError):
        return default


# --- Обов'язкові -----------------------------------------------------------
TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")

# --- Поведінка -------------------------------------------------------------
ADMIN_CHAT_ID = _get("ADMIN_CHAT_ID")
POLL_INTERVAL_MINUTES = _get_int("POLL_INTERVAL_MINUTES", 4)
MIN_IMPORTANCE = _get_int("MIN_IMPORTANCE", 3)
ANALYSIS_MODEL = _get("ANALYSIS_MODEL", "claude-opus-4-8")
ASSISTANT_MODEL = _get("ASSISTANT_MODEL", "claude-haiku-4-5-20251001")
BOT_LANGUAGE = _get("BOT_LANGUAGE", "uk")
DATABASE_URL = _get("DATABASE_URL", "sqlite:///data/oilscaner.db")

# Скільки нових релевантних новин обробляти за один цикл (захист від спаму/бюджету)
MAX_NEWS_PER_CYCLE = _get_int("MAX_NEWS_PER_CYCLE", 4)
# Cooldown (хв) на схожі заголовки, щоб не аналізувати дублі
SIGNAL_COOLDOWN_MINUTES = _get_int("SIGNAL_COOLDOWN_MINUTES", 20)


def missing_required() -> list[str]:
    """Повертає список відсутніх обов'язкових ключів."""
    out = []
    if not TELEGRAM_BOT_TOKEN:
        out.append("TELEGRAM_BOT_TOKEN")
    if not ANTHROPIC_API_KEY:
        out.append("ANTHROPIC_API_KEY")
    return out
