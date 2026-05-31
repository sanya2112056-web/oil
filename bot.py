"""
bot.py — головний файл Telegram-бота «Нафта Brent Сигнали».

Зміни v2:
  ✅ Бот доступний БУДЬ-ЯКОМУ користувачу (не тільки власнику)
  ✅ Заголовки новин перекладаються на українську мову

Режими роботи:
  1. Автоматичний: сканування новин кожні SCAN_INTERVAL_MIN хвилин →
     надсилає ВСІМ підписникам (хто натиснув /start).
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
import translator as tr

# ── Логування ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("oilbot")

# ── Підписники (всі хто натиснув /start) ─────────────────────────────────────
# Зберігаємо у пам'яті; при перезапуску — очищується (для persistence
# потрібна БД, але для базового використання достатньо)
SUBSCRIBERS: set[int] = set()

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
            InlineKeyboardButton("📊 Сигнал",       callback_data="signal"),
            InlineKeyboardButton("📰 Новини",        callback_data="news"),
        ],
        [
            InlineKeyboardButton("🔧 Перевірка API", callback_data="check"),
            InlineKeyboardButton("📈 Статистика",    callback_data="stats"),
        ],
    ])


def _title(item: dict) -> str:
    """Повертає перекладений заголовок якщо є, інакше — оригінал."""
    return item.get("title_uk") or item.get("title", "")


def format_signal(sig: dict) -> str:
    """Форматує сигнал для відправки в Telegram."""
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
    change_mb = eia["change_kb"] / 1000.0
    direction = "BULLISH — очікується ЗРІСТ" if change_mb < 0 \
                else "BEARISH — очікується ПАДІННЯ"
    emoji = "🟢" if change_mb < 0 else "🔴"
    sign  = "+" if change_mb >= 0 else ""

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


async def _fetch_and_translate() -> list[dict]:
    """Збирає новини та перекладає заголовки на українську."""
    items = await nf.fetch_all_news()
    items = await tr.translate_items(items)
    STATS["news_scanned"] += len(items)
    return items


# ─────────────────────────────────────────────────────────────────────────────
# Хендлери команд
# ─────────────────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Реєструє будь-якого користувача як підписника."""
    user_id = update.effective_user.id
    is_new  = user_id not in SUBSCRIBERS
    SUBSCRIBERS.add(user_id)

    if STATS["started_at"] is None:
        STATS["started_at"] = kyiv_now()

    greeting = "👋 *Вітаю! Ти підписаний на сигнали по нафті Brent.*" if is_new \
               else "✅ *Ти вже підписаний на сигнали по нафті Brent.*"

    text = (
        f"{greeting}\n\n"
        f"🔄 Автосигнали: кожні *{config.SCAN_INTERVAL_MIN} хвилин*\n"
        "📅 Event-driven: щосереди після 14:35 UTC (дані EIA)\n"
        f"👥 Підписників зараз: *{len(SUBSCRIBERS)}*\n\n"
        "Натисни кнопку або введи команду:"
    )
    await update.message.reply_text(text, parse_mode="Markdown",
                                    reply_markup=main_keyboard())
    log.info("Підписник: user_id=%s | всього=%d", user_id, len(SUBSCRIBERS))


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Довідка*\n\n"
        "/start — підписатись на сигнали\n"
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
        "🌐 Новини показуються *українською мовою*\n\n"
        "⚠️ _Сигнали не є фінансовою порадою._"
    )
    await update.effective_message.reply_text(text, parse_mode="Markdown")


async def signal_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.effective_message.reply_text("🔍 Аналізую новини...")
    items = await _fetch_and_translate()

    # Для scoring використовуємо оригінальний англійський заголовок
    sig = sa.best_signal(items)
    if sig:
        # Підставляємо перекладений заголовок у відповідь
        item_map = {it.get("title", ""): it for it in items}
        orig = sig["title"]
        if orig in item_map:
            sig = dict(sig)
            sig["title"] = item_map[orig].get("title_uk") or orig
        await msg.edit_text(format_signal(sig), parse_mode="Markdown")
    else:
        scored = sa.analyze(items)
        if scored:
            t = scored[0]
            item_map = {it.get("title", ""): it for it in items}
            title_uk = item_map.get(t["title"], {}).get("title_uk") or t["title"]
            await msg.edit_text(
                f"⚪ Сильного сигналу немає (поріг {config.SIGNAL_THRESHOLD}%).\n\n"
                f"Найкраще знайдено:\n"
                f"  • *{title_uk}*\n"
                f"  • {t['direction']} | Впевненість: {t['confidence']}%\n\n"
                f"Продовжую моніторинг...",
                parse_mode="Markdown",
            )
        else:
            await msg.edit_text("ℹ️ Нафтових новин не знайдено. Спробуйте пізніше.")


async def news_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.effective_message.reply_text("🔍 Збираю та перекладаю новини...")
    items = await _fetch_and_translate()
    scored = sa.analyze(items)[:5]

    if scored:
        # Будуємо карту orig_title → translated_title
        title_map = {it.get("title", ""): it.get("title_uk") or it.get("title", "")
                     for it in items}
        lines = ["📰 *Топ-5 впливових новин зараз:*\n"]
        for i, s in enumerate(scored, 1):
            e = "🟢" if s["direction"] == "BULLISH" else "🔴"
            uk_title = title_map.get(s["title"], s["title"])
            lines.append(
                f"{i}. {e} [{s['confidence']}%] _{uk_title}_\n"
                f"   📡 {s['source']}"
            )
        await msg.edit_text("\n".join(lines), parse_mode="Markdown")
    elif items:
        lines = ["📰 *Останні нафтові новини:*\n"]
        for i, it in enumerate(items[:5], 1):
            title = it.get("title_uk") or it.get("title", "")
            lines.append(f"{i}. _{title}_ ({it['source']})")
        await msg.edit_text("\n".join(lines), parse_mode="Markdown")
    else:
        await msg.edit_text("ℹ️ Нафтових новин не знайдено.")


async def check_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.effective_message.reply_text("🔧 Перевіряю всі джерела...")
    status = await nf.check_apis()
    lines  = [f"🔧 *Статус джерел*  |  {fmt_time()}\n"]
    for name, st in status.items():
        lines.append(f"• *{name}*: {st}")
    lines.append(f"\n👥 *Підписників:* {len(SUBSCRIBERS)}")
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
        f"👥 Підписників: {len(SUBSCRIBERS)}\n"
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
# Заплановані задачі (розсилка ВСІМ підписникам)
# ─────────────────────────────────────────────────────────────────────────────

async def auto_scan(ctx: ContextTypes.DEFAULT_TYPE):
    """
    Автоматичне сканування кожні N хвилин.
    Надсилає сигнал ВСІМ підписникам (хто натиснув /start).
    Якщо підписників немає — перевіряє TELEGRAM_CHAT_ID як fallback.
    """
    items = await _fetch_and_translate()
    sig   = sa.best_signal(items)

    if not sig:
        return

    # Перекладаємо заголовок у сигналі
    title_map = {it.get("title", ""): it.get("title_uk") or it.get("title", "")
                 for it in items}
    sig = dict(sig)
    sig["title"] = title_map.get(sig["title"], sig["title"])

    text = format_signal(sig)
    targets = set(SUBSCRIBERS)

    # Fallback: якщо підписників ще нема, шлемо власнику
    if not targets and config.TELEGRAM_CHAT_ID:
        targets = {int(config.TELEGRAM_CHAT_ID)}

    sent = 0
    for chat_id in targets:
        try:
            await ctx.bot.send_message(chat_id, text, parse_mode="Markdown")
            sent += 1
        except Exception as e:
            log.warning("Не вдалось надіслати chat_id=%s: %s", chat_id, e)

    STATS["signals_sent"] += sent
    log.info("Auto signal: %s %s%% → %d підписників | %s",
             sig["direction"], sig["confidence"], sent, sig["title"][:55])


async def eia_event(ctx: ContextTypes.DEFAULT_TYPE):
    """
    Event-driven: щосереди перевіряємо дані EIA.
    Надсилає ВСІМ підписникам.
    """
    async with aiohttp.ClientSession() as s:
        eia = await nf.fetch_eia_crude_stocks(s)

    if not eia:
        log.warning("EIA дані недоступні (немає ключа або помилка парсингу)")
        return

    text    = format_eia(eia)
    targets = set(SUBSCRIBERS)
    if not targets and config.TELEGRAM_CHAT_ID:
        targets = {int(config.TELEGRAM_CHAT_ID)}

    sent = 0
    for chat_id in targets:
        try:
            await ctx.bot.send_message(chat_id, text, parse_mode="Markdown")
            sent += 1
        except Exception as e:
            log.warning("EIA надсилання chat_id=%s: %s", chat_id, e)

    STATS["signals_sent"] += sent
    log.info("EIA event → %d підписників | %s  зміна %+.2f MB",
             sent, eia["period"], eia["change_kb"] / 1000)


# ─────────────────────────────────────────────────────────────────────────────
# Запуск
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if not config.TELEGRAM_BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN не вказано! Перевірте змінні середовища.")
        return

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

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

    jq = app.job_queue
    jq.run_repeating(
        auto_scan,
        interval=config.SCAN_INTERVAL_MIN * 60,
        first=60,
    )
    jq.run_daily(
        eia_event,
        time=dtime(14, 35, tzinfo=timezone.utc),
        days=(3,),
    )

    log.info(
        "Бот v2 запущено | інтервал %d хв | поріг %d%% | переклад=✅ | multi-user=✅",
        config.SCAN_INTERVAL_MIN,
        config.SIGNAL_THRESHOLD,
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
