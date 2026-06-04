"""Точка входу: ініціалізація БД, бот, періодичний скан (long-polling)."""
from __future__ import annotations

import sys

from telegram import BotCommand
from telegram.ext import Application, ContextTypes

from app import config
from app.bot import handlers
from app.core.scheduler import scan_job
from app.storage import db
from app.utils.log import get_logger

log = get_logger("main")


async def _post_init(app: Application) -> None:
    await app.bot.set_my_commands([
        BotCommand("start", "Запуск і підписка"),
        BotCommand("menu", "Головне меню"),
        BotCommand("help", "Довідка"),
    ])
    # Періодичний скан новин
    interval = max(1, config.POLL_INTERVAL_MINUTES) * 60
    app.job_queue.run_repeating(scan_job, interval=interval, first=25,
                                name="news_scan")
    log.info("Бот запущено. Скан кожні %d хв.", config.POLL_INTERVAL_MINUTES)
    if config.ADMIN_CHAT_ID:
        try:
            await app.bot.send_message(
                chat_id=config.ADMIN_CHAT_ID,
                text="✅ OIL SCANER запущено й готовий до роботи.")
        except Exception as e:  # noqa: BLE001
            log.warning("Не вдалось сповістити адміна: %s", e)


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Помилка обробки апдейту", exc_info=context.error)


def main() -> None:
    missing = config.missing_required()
    if missing:
        log.error("Відсутні ОБОВ'ЯЗКОВІ ключі: %s. "
                  "Додай їх у Railway → Variables або .env.", ", ".join(missing))
        sys.exit(1)

    db.init_db()

    app = (Application.builder()
           .token(config.TELEGRAM_BOT_TOKEN)
           .post_init(_post_init)
           .build())

    handlers.register(app)
    app.add_error_handler(_on_error)

    log.info("Старт long-polling…")
    app.run_polling(allowed_updates=["message", "callback_query"],
                    drop_pending_updates=True)


if __name__ == "__main__":
    main()
