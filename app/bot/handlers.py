"""Обробники Telegram: команди, кнопки (callback), текстові повідомлення."""
from __future__ import annotations

import asyncio

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

from app.bot import assistant, keyboards, messages
from app.core import pipeline
from app.core.data_collector import collect_market_snapshot
from app.sources.registry import all_source_infos, check_all_health, core_health
from app.storage import db
from app.utils.log import get_logger

log = get_logger("bot.handlers")

MAX_LEN = 4000  # ліміт Telegram ~4096, лишаємо запас


async def _send(update: Update, text: str, kb=None, preview=False):
    chunks = [text[i:i + MAX_LEN] for i in range(0, len(text), MAX_LEN)] or [text]
    target = update.effective_message
    for i, ch in enumerate(chunks):
        await target.reply_text(
            ch, parse_mode=ParseMode.HTML,
            reply_markup=kb if i == len(chunks) - 1 else None,
            disable_web_page_preview=not preview)


# --- /start, /menu ---------------------------------------------------------
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await asyncio.to_thread(db.upsert_subscriber, user.id, user.username or "")
    await asyncio.to_thread(db.set_mode, user.id, "menu")
    await _send(update, messages.WELCOME, keyboards.main_menu(subscribed=True))


async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    sub = await asyncio.to_thread(db.get_subscriber, update.effective_user.id)
    subscribed = bool(sub and sub["subscribed"])
    await asyncio.to_thread(db.set_mode, update.effective_user.id, "menu")
    await _send(update, "🏠 <b>Головне меню</b>", keyboards.main_menu(subscribed))


# --- Кнопки ----------------------------------------------------------------
async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    chat_id = update.effective_user.id

    if data == "menu":
        await asyncio.to_thread(db.set_mode, chat_id, "menu")
        sub = await asyncio.to_thread(db.get_subscriber, chat_id)
        await q.edit_message_text(
            "🏠 <b>Головне меню</b>", parse_mode=ParseMode.HTML,
            reply_markup=keyboards.main_menu(bool(sub and sub["subscribed"])))

    elif data == "subscribe":
        await asyncio.to_thread(db.upsert_subscriber, chat_id,
                                update.effective_user.username or "")
        await q.edit_message_text("🟢 Підписку увімкнено! Сигнали приходитимуть автоматично.",
                                  reply_markup=keyboards.main_menu(True))

    elif data == "unsubscribe":
        await asyncio.to_thread(db.set_subscribed, chat_id, False)
        await q.edit_message_text("🔴 Підписку вимкнено. Можеш увімкнути будь-коли.",
                                  reply_markup=keyboards.main_menu(False))

    elif data == "scan_now":
        await q.edit_message_text("📡 Запускаю повний скан… (10–40 сек)",
                                  parse_mode=ParseMode.HTML)
        res = await pipeline.run_scan(ctx.application.bot, manual=True)
        await _report_scan(update, res)

    elif data == "last_signal":
        await _show_signals(update, limit=1)

    elif data == "history":
        await _show_signals(update, limit=5)

    elif data == "market":
        snapshot, unavailable = await collect_market_snapshot()
        await _send(update, messages.format_market_snapshot(snapshot, unavailable),
                    keyboards.back_menu())

    elif data == "health":
        await q.edit_message_text("🩺 Перевіряю всі джерела…")
        results = await check_all_health()
        await _send(update, messages.format_health(results, core_health()),
                    keyboards.back_menu())

    elif data == "api_list":
        await _send(update, messages.format_api_list(all_source_infos()),
                    keyboards.back_menu())

    elif data == "about":
        await _send(update, messages.ABOUT, keyboards.back_menu())

    elif data == "settings":
        sub = await asyncio.to_thread(db.get_subscriber, chat_id)
        notif = bool(sub and sub["notifications"])
        await q.edit_message_text("⚙️ <b>Налаштування</b>", parse_mode=ParseMode.HTML,
                                  reply_markup=keyboards.settings_menu(notif))

    elif data == "toggle_notif":
        new = await asyncio.to_thread(db.toggle_notifications, chat_id)
        await q.edit_message_text(
            f"⚙️ <b>Налаштування</b>\nСповіщення тепер: "
            f"{'🔔 УВІМК' if new else '🔕 ВИМК'}",
            parse_mode=ParseMode.HTML, reply_markup=keyboards.settings_menu(new))

    elif data == "assistant_on":
        await asyncio.to_thread(db.set_mode, chat_id, "assistant")
        assistant.reset(str(chat_id))
        await _send(update, messages.assistant_intro(), keyboards.assistant_menu())

    elif data == "help":
        await _send(update, messages.HELP, keyboards.back_menu())


# --- Текстові повідомлення (режим асистента) -------------------------------
async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    mode = await asyncio.to_thread(db.get_mode, chat_id)
    if mode != "assistant":
        sub = await asyncio.to_thread(db.get_subscriber, chat_id)
        await _send(update,
                    "Скористайся кнопками меню або увімкни 🤖 AI-асистента.",
                    keyboards.main_menu(bool(sub and sub["subscribed"])))
        return
    await ctx.application.bot.send_chat_action(chat_id=chat_id, action="typing")
    answer = await assistant.reply(str(chat_id), update.effective_message.text or "")
    await _send(update, answer, keyboards.assistant_menu())


# --- Допоміжні -------------------------------------------------------------
async def _report_scan(update: Update, res: dict):
    signals = res.get("signals", [])
    if not signals:
        note = res.get("note", "Нових релевантних новин немає.")
        await _send(update,
                    f"✅ Скан завершено. {note}\n"
                    f"Релевантних новин у стрічці: {res.get('relevant', 0)}.",
                    keyboards.back_menu())
        return
    for title, url, source, result in signals:
        await _send(update, messages.format_signal(title, url, source, result),
                    None)
    await _send(update, f"✅ Готово. Згенеровано сигналів: {len(signals)}.",
                keyboards.back_menu())


async def _show_signals(update: Update, limit: int):
    rows = await asyncio.to_thread(db.latest_signals, limit)
    if not rows:
        await _send(update, "📭 Сигналів ще немає. Натисни «📡 Сканувати зараз».",
                    keyboards.back_menu())
        return
    for r in rows:
        await _send(update,
                    messages.format_signal(r["news_title"], r["news_url"],
                                           "джерело", r["payload"]),
                    None)
    await _send(update, "⬆️ Останні сигнали.", keyboards.back_menu())


def register(app: Application) -> None:
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("help", cmd_menu))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
