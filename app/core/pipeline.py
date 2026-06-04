"""Повний цикл: новини → фільтр → дані → Claude → розсилка підписникам."""
from __future__ import annotations

import asyncio

from telegram import Bot
from telegram.constants import ParseMode

from app.config import (MAX_NEWS_PER_CYCLE, MIN_IMPORTANCE,
                        SIGNAL_COOLDOWN_MINUTES)
from app.bot import messages
from app.core import analyzer
from app.core.claude_client import is_ready
from app.core.data_collector import collect_market_snapshot
from app.core.news_aggregator import collect_all_news, filter_relevant
from app.core.relevance import importance
from app.storage import db
from app.utils.log import get_logger, record_event

log = get_logger("core.pipeline")

# Запобігає одночасним циклам (scheduler + ручний запуск)
_lock = asyncio.Lock()


async def run_scan(bot: Bot, manual: bool = False) -> dict:
    """Повертає {'analyzed': n, 'signals': [(title, url, source, result), ...]}."""
    if _lock.locked():
        return {"analyzed": 0, "signals": [], "note": "Скан уже виконується."}

    async with _lock:
        if not is_ready():
            return {"analyzed": 0, "signals": [],
                    "note": "ANTHROPIC_API_KEY не доданий — аналіз недоступний."}

        raw = await collect_all_news()
        relevant = filter_relevant(raw)
        log.info("Новин: %d, релевантних: %d", len(raw), len(relevant))

        # Cooldown лише для автоматичного циклу
        if not manual and db.cooldown_active(SIGNAL_COOLDOWN_MINUTES):
            return {"analyzed": 0, "signals": [],
                    "note": "cooldown", "relevant": len(relevant)}

        # Відбираємо нові за дедупом і порогом важливості
        candidates = []
        for it in relevant:
            score = importance(it)
            is_fresh = await asyncio.to_thread(db.is_new, it.dedup_key())
            if not is_fresh:
                continue
            if score < MIN_IMPORTANCE and not manual:
                # позначаємо як бачене, щоб не перевіряти щоразу
                await asyncio.to_thread(db.mark_seen, it.dedup_key(), it.title)
                continue
            candidates.append((it, score))
            if len(candidates) >= MAX_NEWS_PER_CYCLE:
                break

        if not candidates and manual:
            # ручний запуск: візьмемо найважливішу новину, навіть якщо вже бачена
            if relevant:
                candidates = [(relevant[0], importance(relevant[0]))]

        if not candidates:
            return {"analyzed": 0, "signals": [], "relevant": len(relevant),
                    "note": "Нових релевантних новин немає."}

        snapshot, unavailable = await collect_market_snapshot()

        signals = []
        for it, score in candidates:
            await asyncio.to_thread(db.mark_seen, it.dedup_key(), it.title)
            try:
                result = await analyzer.analyze_news(it, snapshot, unavailable, score)
            except Exception as e:  # noqa: BLE001
                record_event("error", "analyzer", str(e))
                log.exception("Помилка аналізу")
                continue
            sig = str(result.get("signal", "NEUTRAL")).upper()
            await asyncio.to_thread(db.save_signal, it.title, it.url, sig, result)
            signals.append((it.title, it.url, it.source, result))

        # Розсилка підписникам
        for title, url, source, result in signals:
            text = messages.format_signal(title, url, source, result)
            await _broadcast(bot, text)

        return {"analyzed": len(signals), "signals": signals,
                "relevant": len(relevant)}


async def _broadcast(bot: Bot, text: str) -> None:
    ids = await asyncio.to_thread(db.active_subscriber_ids)
    for cid in ids:
        try:
            await bot.send_message(chat_id=cid, text=text,
                                   parse_mode=ParseMode.HTML,
                                   disable_web_page_preview=True)
            await asyncio.sleep(0.05)  # м'який rate-limit
        except Exception as e:  # noqa: BLE001
            record_event("warn", "broadcast", f"{cid}: {e}")
