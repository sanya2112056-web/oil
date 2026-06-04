"""Текстові шаблони та форматування повідомлень (українською)."""
from __future__ import annotations

import html

from app.sources.base import HealthResult, HealthStatus, SourceInfo

WELCOME = (
    "🛢️ <b>OIL SCANER</b> — AI-агент моніторингу нафти (WTI)\n\n"
    "Я безперервно читаю десятки новинних джерел. Щойно виходить будь-яка "
    "новина про нафту, що може вплинути на ціну, я:\n"
    "1️⃣ збираю ринкові показники (ціна WTI/Brent, запаси EIA, індекс долара, макро)\n"
    "2️⃣ проганяю все через Claude AI (натренований на дослідженні ринку WTI 2026)\n"
    "3️⃣ надсилаю тобі сигнал: напрямок, ймовірність, % руху, час відпрацювання\n\n"
    "✅ Ти підписаний — сигнали приходитимуть автоматично.\n"
    "Користуйся кнопками нижче 👇"
)

ABOUT = (
    "ℹ️ <b>Про OIL SCANER</b>\n\n"
    "Бот-аналітик ринку WTI. Працює на безкоштовних джерелах новин і даних "
    "(можна додати багато API-ключів для глибшого покриття, але бот працює "
    "і без них — через RSS та yfinance).\n\n"
    "<b>Що означає сигнал:</b>\n"
    "🟢 LONG — очікується ріст ціни\n"
    "🔴 SHORT — очікується падіння\n"
    "⚪ NEUTRAL — чіткого руху не очікується\n\n"
    "<b>Важливо:</b> це аналітичний інструмент, а не фінансова порада. "
    "Рішення про угоди приймаєш сам.\n\n"
    "Натисни 🤖 «AI-асистент», щоб поставити будь-яке питання про бота "
    "або дізнатись, що зараз працює/не працює."
)

HELP = (
    "🆘 <b>Довідка по кнопках</b>\n\n"
    "🟢/🔴 — підписка на сигнали (вкл/викл)\n"
    "📡 Сканувати зараз — ручний запуск повного циклу аналізу\n"
    "📊 Останній сигнал — показати останній згенерований сигнал\n"
    "📈 Знімок ринку — поточні ціни й показники\n"
    "🩺 Перевірка API — статус кожного джерела (✅/⚠️/⛔/🆓)\n"
    "📋 Список API — усі ключі та де їх взяти\n"
    "🤖 AI-асистент — чат про бота й діагностика\n"
    "⚙️ Налаштування — сповіщення, поріг важливості\n"
    "📜 Історія — останні сигнали\n"
)

SIGNAL_EMOJI = {"LONG": "🟢", "SHORT": "🔴", "NEUTRAL": "⚪"}
DIR_EMOJI = {"вгору": "📈", "вниз": "📉", "вбік": "➡️"}


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""))


def format_signal(item_title: str, item_url: str, item_source: str,
                  result: dict) -> str:
    if result.get("_parse_error"):
        return ("⚠️ Не вдалося розпарсити відповідь AI.\n\n"
                f"<i>{esc(result.get('_raw', '')[:1200])}</i>")

    sig = str(result.get("signal", "NEUTRAL")).upper()
    emoji = SIGNAL_EMOJI.get(sig, "⚪")
    direction = str(result.get("direction", ""))
    dir_emoji = DIR_EMOJI.get(direction, "")
    prob = result.get("probability", "—")
    conf = result.get("confidence", "—")

    parts = [
        f"{emoji} <b>СИГНАЛ: {esc(sig)}</b> {dir_emoji}",
        "",
        f"📰 <b>Новина:</b> {esc(item_title)}",
        f"🔗 <a href=\"{esc(item_url)}\">{esc(item_source)}</a>",
        "",
        f"🧠 <b>Аналіз:</b> {esc(result.get('interpretation', '—'))}",
        "",
        f"📊 <b>Зібрані дані:</b> {esc(result.get('summary', '—'))}",
        "",
        f"🎯 Ймовірність відпрацювання: <b>{esc(prob)}%</b>",
        f"📐 Орієнтовний рух: <b>{esc(result.get('expected_move_pct', '—'))}</b>",
        f"⏱ Горизонт часу: <b>{esc(result.get('time_horizon', '—'))}</b>",
        f"🔎 Впевненість: <b>{esc(conf)}</b>",
        f"⚠️ Ризики: {esc(result.get('key_risks', '—'))}",
        "",
        "<i>Не є фінансовою порадою.</i>",
    ]
    return "\n".join(parts)


def format_health(results: list[HealthResult], core: list[HealthResult]) -> str:
    lines = ["🩺 <b>Перевірка API / джерел</b>\n"]
    lines.append("<b>Обов'язкові (core):</b>")
    for r in core:
        lines.append(f"{r.emoji} {esc(r.info.name)} — {esc(r.detail)}")

    by_cat = {"news": [], "market": []}
    for r in results:
        by_cat.setdefault(r.info.category, []).append(r)

    cat_titles = {"news": "📰 Новинні джерела", "market": "📈 Ринкові/макро джерела"}
    for cat, title in cat_titles.items():
        rows = by_cat.get(cat, [])
        if not rows:
            continue
        lines.append(f"\n<b>{title}:</b>")
        for r in rows:
            lines.append(f"{r.emoji} {esc(r.info.name)} — {esc(r.detail)}")

    lines.append("\n<i>✅ працює · 🆓 без ключа · ⛔ ключ не додано · ⚠️ помилка</i>")
    return "\n".join(lines)


def format_api_list(infos: list[SourceInfo]) -> str:
    lines = ["📋 <b>Повний список API/джерел</b>\n",
             "Додавай ключі у Railway → Variables (або у файл .env локально). "
             "Назва змінної вказана в дужках. Усе, крім core, — опційне.\n"]
    by_cat = {"core": [], "news": [], "market": []}
    for info in infos:
        by_cat.setdefault(info.category, []).append(info)
    titles = {"core": "🔑 ОБОВ'ЯЗКОВІ", "news": "📰 Новини (опційно)",
              "market": "📈 Ринок/макро (опційно)"}
    for cat, title in titles.items():
        rows = by_cat.get(cat, [])
        if not rows:
            continue
        lines.append(f"<b>{title}:</b>")
        for info in rows:
            env = f"<code>{esc(info.env_var)}</code>" if info.env_var else "🆓 без ключа"
            url = f"\n   ↳ {esc(info.signup_url)}" if info.signup_url else ""
            lines.append(f"• <b>{esc(info.name)}</b> ({env}) — {esc(info.note)}{url}")
        lines.append("")
    return "\n".join(lines)


def format_market_snapshot(snapshot: dict, unavailable: list[str]) -> str:
    if not snapshot:
        return ("📈 <b>Знімок ринку</b>\n\nНа жаль, зараз немає доступних "
                "ринкових даних. Перевір 🩺 «Перевірка API».")
    lines = ["📈 <b>Знімок ринку</b>\n"]
    for k, v in snapshot.items():
        lines.append(f"• {esc(k)}: <b>{esc(v)}</b>")
    if unavailable:
        lines.append(f"\n<i>Недоступні: {esc(', '.join(unavailable))}</i>")
    return "\n".join(lines)


def assistant_intro() -> str:
    return ("🤖 <b>AI-асистент увімкнено.</b>\n\n"
            "Питай що завгодно про бота: як він працює, що означає сигнал, "
            "які ключі додати, що зараз не працює. Я бачу поточний стан системи.\n\n"
            "Натисни «⬅️ Меню», щоб вийти з режиму асистента.")
