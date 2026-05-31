"""
bot.py — головний файл Telegram-бота «Нафта Brent Сигнали».

Режими роботи:
  1. Автоматичний: сканування новин кожні SCAN_INTERVAL_MIN хвилин.
  2. Event-driven: щосереди о 14:35 UTC — перевірка запасів EIA.

Команди: /start /signal /check /news /stats /help
"""

import logging
from datetime import datetime, timezone, timedelta, time as dtime

import aiohttp
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

import config
import news_fetcher as nf
import signal_analyzer as sa

# ── Логування ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("oilbot")

# ── Статистика сесії ──────────────────────────────────────────────────────────
STATS = {"signals_sent": 0, "news_scanned": 0, "started_at": None}


# ─────────────────────────────────────────────────────────────────────────────
# Допоміжні функції
# ─────────────────────────────────────────────────────────────────────────────

def kyiv_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=config.KYIV_TZ_OFFSET)


def fmt_time() -> str:
    return kyiv_now().strftime("%d.%m.%Y %H:%M (UTC+2)")


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Сигнал",        callback_data="signal"),
            InlineKeyboardButton("📰 Новини",         callback_data="news"),
        ],
        [
            InlineKeyboardButton("🔧 Перевірка API",  callback_data="check"),
            InlineKeyboardButton("📈 Статистика",     callback_data="stats"),
        ],
    ])


def format_signal(sig: dict) -> str:
    """Форматує сигнал для надсилання в Telegram."""
    emoji = "🟢" if sig["direction"] == "BULLISH" else "🔴"
    word  = "BULLISH — очікується ЗРІСТ" if sig["direction"] == "BULLISH" \
            else "BEARISH — очікується ПАДІННЯ"
    hits  = ", ".join(sig["hits"][:6]) or "—"
    url   = f"\n🔗 {sig['url']}" if sig.get("url") else ""

    return (
        f"🛢️ *СИГНАЛ — НАФТА BRENT*\n"
        f"📅 {fmt_time()}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📰 *Новина:* {sig['title']}\n"
        f"📡 *Джерело:* {sig['source']}"
        f"{url}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{emoji} *Напрямок:* {word}\n"
        f"💹 *Очікуваний рух:* {sig['price_move']}\n"
        f"⏱️ *Реакція ринку:* {sig['reaction_time']}\n"
        f"📈 *Таймфрейм:* {sig['timeframe']}\n"
        f"🔥 *Впевненість:* {sig['confidence']}%\n"
        f"🔑 *Тригери:* {hits}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ _Це не є фінансовою порадою._"
    )


def format_eia(eia: dict) -> str:
    """Форматує звіт EIA для Telegram."""
    change_mb  = eia["change_kb"] / 1000.0
    direction  = "BULLISH — очікується ЗРІСТ" if change_mb < 0 \
                 else "BEARISH — очікується ПАДІННЯ"
    emoji      = "🟢" if change_mb < 0 else "🔴"
    sign       = "+" if change_mb >= 0 else ""

    return (
        f"🛢️ *EIA — ЗАПАСИ СИРОЇ НАФТИ США*\n"
        f"📅 {fmt_time()}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *Звітний тиждень:* {eia['period']}\n"
        f"📦 *Запаси:* {eia['value_kb']:,.0f} тис. бар.\n"
        f"🔄 *Зміна:* {sign}{change_mb:.2f} млн барелів\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{emoji} *Сигнал:* {direction}\n"
        f"⏱️ *Реакція ринку:* 5–15 хв\n"
        f"📈 *Таймфрейм:* M5 / M15\n"
        f"🔥 *Впевненість:* 80%\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ _Це не є фінансовою порадою._"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Хендлери команд
# ─────────────────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    STATS["started_at"] = kyiv_now()
    text = (
        "👋 *Вітаю! Бот сигналів по нафті Brent запущено.*\n\n"
        f"🔄 Автосканування: кожні *{config.SCAN_INTERVAL_MIN} хвилин*\n"
        "📅 Event-driven: щосереди після 14:35 UTC (дані EIA)\n\n"
        "Натисни кнопку або введи команду:"
    )
    await update.message.reply_text(text, parse_mode="Markdown",
                                    reply_markup=main_keyboard())


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Довідка*\n\n"
        "/start — запустити бота\n"
        "/signal — отримати поточний сигнал\n"
        "/check — перевірити кожне API окремо\n"
        "/news — топ-5 впливових новин зараз\n"
        "/stats — статистика роботи бота\n"
        "/help — ця довідка\n\n"
        "🛢️ Бот аналізує новини про:\n"
        "  • Рішення ОПЕК+ (квоти, наради)\n"
        "  • Запаси нафти США (EIA, кожну середу)\n"
        "  • Геополітику (Близький Схід, санкції)\n"
        "  • Макроекономіку (ФРС, DXY, PMI)\n\n"
        "⚠️ _Сигнали не є фінансовою порадою._"
    )
    await update.effective_message.reply_text(text, parse_mode="Markdown")


async def signal_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.effective_message.reply_text("🔍 Аналізую новини...")
    items = await nf.fetch_all_news()
    STATS["news_scanned"] += len(items)

    sig = sa.best_signal(items)
    if sig:
        await msg.edit_text(format_signal(sig), parse_mode="Markdown")
    else:
        scored = sa.analyze(items)
        if scored:
            t = scored[0]
            await msg.edit_text(
                f"⚪ Сильного сигналу немає (поріг {config.SIGNAL_THRESHOLD}%).\n\n"
                f"Найкраще знайдено:\n"
                f"  • *{t['title']}*\n"
                f"  • {t['direction']} | Впевненість: {t['confidence']}%\n\n"
                f"Продовжую моніторинг...",
                parse_mode="Markdown",
            )
        else:
            await msg.edit_text("ℹ️ Нафтових новин не знайдено. Спробуйте пізніше.")


async def news_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.effective_message.reply_text("🔍 Збираю новини...")
    items = await nf.fetch_all_news()
    scored = sa.analyze(items)[:5]

    if scored:
        lines = ["📰 *Топ-5 впливових новин зараз:*\n"]
        for i, s in enumerate(scored, 1):
            e = "🟢" if s["direction"] == "BULLISH" else "🔴"
            lines.append(
                f"{i}. {e} [{s['confidence']}%] _{s['title']}_\n"
                f"   📡 {s['source']}"
            )
        await msg.edit_text("\n".join(lines), parse_mode="Markdown")
    elif items:
        lines = ["📰 *Останні нафтові новини:*\n"]
        for i, it in enumerate(items[:5], 1):
            lines.append(f"{i}. _{it['title']}_ ({it['source']})")
        await msg.edit_text("\n".join(lines), parse_mode="Markdown")
    else:
        await msg.edit_text("ℹ️ Нафтових новин не знайдено.")


async def check_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.effective_message.reply_text("🔧 Перевіряю всі джерела...")
    status = await nf.check_apis()
    lines  = [f"🔧 *Статус джерел*  |  {fmt_time()}\n"]
    for name, st in status.items():
        lines.append(f"• *{name}*: {st}")
    lines.append("\n_Ключ не вказано = ⚠️, помилка = ❌, ОК = ✅_")
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")


async def stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uptime = ""
    if STATS["started_at"]:
        delta   = kyiv_now() - STATS["started_at"]
        hours   = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        uptime  = f"{hours}г {minutes}хв"

    text = (
        f"📊 *Статистика бота*\n"
        f"📅 {fmt_time()}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱️ Uptime: {uptime or '—'}\n"
        f"🔍 Новин проскановано: {STATS['news_scanned']}\n"
        f"📤 Сигналів надіслано: {STATS['signals_sent']}\n"
        f"⚙️ Інтервал сканування: {config.SCAN_INTERVAL_MIN} хв\n"
        f"🎯 Поріг сигналу: {config.SIGNAL_THRESHOLD}%"
    )
    await update.effective_message.reply_text(text, parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────────────────────
# Callback-кнопки (inline keyboard)
# ─────────────────────────────────────────────────────────────────────────────

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "signal":
        await signal_cmd(update, ctx)
    elif q.data == "news":
        await news_cmd(update, ctx)
    elif q.data == "check":
        await check_cmd(update, ctx)
    elif q.data == "stats":
        await stats_cmd(update, ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Заплановані задачі
# ─────────────────────────────────────────────────────────────────────────────

async def auto_scan(ctx: ContextTypes.DEFAULT_TYPE):
    """Автоматичне сканування кожні N хвилин."""
    if not config.TELEGRAM_CHAT_ID:
        return
    items = await nf.fetch_all_news()
    STATS["news_scanned"] += len(items)
    sig = sa.best_signal(items)
    if sig:
        await ctx.bot.send_message(
            config.TELEGRAM_CHAT_ID,
            format_signal(sig),
            parse_mode="Markdown",
        )
        STATS["signals_sent"] += 1
        log.info("Auto signal: %s %s%%  [%s]",
                 sig["direction"], sig["confidence"], sig["title"][:60])


async def eia_event(ctx: ContextTypes.DEFAULT_TYPE):
    """
    Event-driven: щосереди перевіряємо дані EIA.
    EIA виходить о ~10:30 ET → ми стартуємо о 14:35 UTC (влітку).
    """
    if not config.TELEGRAM_CHAT_ID:
        return
    async with aiohttp.ClientSession() as s:
        eia = await nf.fetch_eia_crude_stocks(s)
    if eia:
        await ctx.bot.send_message(
            config.TELEGRAM_CHAT_ID,
            format_eia(eia),
            parse_mode="Markdown",
        )
        STATS["signals_sent"] += 1
        log.info("EIA event sent: %s  change %+.2f MB",
                 eia["period"], eia["change_kb"] / 1000)
    else:
        log.warning("EIA data not available (no key or parse error)")


# ─────────────────────────────────────────────────────────────────────────────
# Запуск
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if not config.TELEGRAM_BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN не вказано! Перевірте змінні середовища.")
        return

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Реєстрація команд
    for cmd, handler in [
        ("start",  start),
        ("help",   help_cmd),
        ("signal", signal_cmd),
        ("news",   news_cmd),
        ("check",  check_cmd),
        ("stats",  stats_cmd),
    ]:
        app.add_handler(CommandHandler(cmd, handler))

    app.add_handler(CallbackQueryHandler(on_button))

    # Заплановані задачі
    jq = app.job_queue
    # Автоматичне сканування
    jq.run_repeating(
        auto_scan,
        interval=config.SCAN_INTERVAL_MIN * 60,
        first=60,    # перший запуск через 1 хв після старту
    )
    # EIA щосереди о 14:35 UTC (day=3 при 0=Sunday у PTB)
    jq.run_daily(
        eia_event,
        time=dtime(14, 35, tzinfo=timezone.utc),
        days=(3,),
    )

    log.info(
        "Бот запущено | інтервал %d хв | поріг %d%% | chat_id=%s",
        config.SCAN_INTERVAL_MIN,
        config.SIGNAL_THRESHOLD,
        config.TELEGRAM_CHAT_ID or "НЕ ВКАЗАНО",
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
