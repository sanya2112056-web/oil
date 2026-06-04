"""Inline-клавіатури бота."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu(subscribed: bool = True) -> InlineKeyboardMarkup:
    sub_btn = (InlineKeyboardButton("🔴 Відписатися", callback_data="unsubscribe")
               if subscribed else
               InlineKeyboardButton("🟢 Підписатися", callback_data="subscribe"))
    rows = [
        [InlineKeyboardButton("📡 Сканувати зараз", callback_data="scan_now")],
        [InlineKeyboardButton("📊 Останній сигнал", callback_data="last_signal"),
         InlineKeyboardButton("📜 Історія", callback_data="history")],
        [InlineKeyboardButton("📈 Знімок ринку", callback_data="market"),
         InlineKeyboardButton("🩺 Перевірка API", callback_data="health")],
        [InlineKeyboardButton("📋 Список API", callback_data="api_list"),
         InlineKeyboardButton("⚙️ Налаштування", callback_data="settings")],
        [InlineKeyboardButton("🤖 AI-асистент", callback_data="assistant_on")],
        [sub_btn,
         InlineKeyboardButton("ℹ️ Про бота", callback_data="about")],
    ]
    return InlineKeyboardMarkup(rows)


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Меню", callback_data="menu")]])


def assistant_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Меню (вийти з асистента)", callback_data="menu")]])


def settings_menu(notifications: bool) -> InlineKeyboardMarkup:
    notif = "🔔 Сповіщення: УВІМК" if notifications else "🔕 Сповіщення: ВИМК"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(notif, callback_data="toggle_notif")],
        [InlineKeyboardButton("⬅️ Меню", callback_data="menu")],
    ])
