"""Періодичне завдання: повний скан новин і розсилка сигналів."""
from __future__ import annotations

from telegram.ext import ContextTypes

from app.core import pipeline
from app.utils.log import get_logger

log = get_logger("core.scheduler")


async def scan_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        res = await pipeline.run_scan(context.bot, manual=False)
        if res.get("analyzed"):
            log.info("Авто-скан: %d сигнал(ів) розіслано", res["analyzed"])
    except Exception:  # noqa: BLE001
        log.exception("Помилка авто-скану")
