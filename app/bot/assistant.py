"""AI-асистент: чат про бота + діагностика поточного стану."""
from __future__ import annotations

from app.core import analyzer
from app.core.claude_client import assistant_reply, is_ready
from app.sources.registry import check_all_health, core_health
from app.storage import db
from app.utils.log import recent_events

# Коротка історія діалогу на користувача (в пам'яті процесу)
_HISTORY: dict[str, list[dict]] = {}
_MAX_TURNS = 8


async def reply(chat_id: str, user_text: str) -> str:
    if not is_ready():
        return ("⚠️ ANTHROPIC_API_KEY не доданий, тому AI-асистент недоступний. "
                "Додай ключ у Railway → Variables і перезапусти бота.")

    # Збираємо живий стан системи для діагностики
    results = await check_all_health()
    core = core_health()
    health_lines = [f"{r.emoji} {r.info.name}: {r.detail}" for r in core + results]
    health_summary = "\n".join(health_lines)

    errors = recent_events(12)
    err_summary = "\n".join(
        f"[{e['level']}] {e['source']}: {e['message']}" for e in errors)
    sub_count = await _count()

    system = analyzer.describe_bot_for_assistant(
        health_summary, err_summary, sub_count)

    history = _HISTORY.get(chat_id, [])
    try:
        answer = await assistant_reply(system, history, user_text)
    except Exception as e:  # noqa: BLE001
        return f"⚠️ Помилка асистента: {e}"

    history = history + [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": answer},
    ]
    _HISTORY[chat_id] = history[-_MAX_TURNS * 2:]
    return answer


def reset(chat_id: str) -> None:
    _HISTORY.pop(chat_id, None)


async def _count() -> int:
    import asyncio
    return await asyncio.to_thread(db.subscriber_count)
