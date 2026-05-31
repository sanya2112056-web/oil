"""
translator.py — переклад заголовків новин на українську мову.

Використовує безкоштовний Google Translate (без API-ключа) через
бібліотеку deep-translator. Якщо переклад не вдався — повертає оригінал.
"""
import asyncio
import logging

log = logging.getLogger("translator")

# Кеш щоб не перекладати одне й те саме двічі
_cache: dict[str, str] = {}


async def translate_to_uk(text: str) -> str:
    """Перекладає рядок на українську. Повертає оригінал при помилці."""
    if not text:
        return text

    # Якщо вже є в кеші
    if text in _cache:
        return _cache[text]

    # Якщо текст вже містить кирилицю — не перекладаємо
    if any('\u0400' <= c <= '\u04FF' for c in text):
        return text

    try:
        from deep_translator import GoogleTranslator
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: GoogleTranslator(source='auto', target='uk').translate(text)
        )
        translated = result or text
        _cache[text] = translated
        return translated
    except Exception as e:
        log.warning("Переклад не вдався: %s | %s", text[:60], e)
        return text  # повертаємо оригінал


async def translate_items(items: list[dict]) -> list[dict]:
    """Перекладає поле 'title' у кожному елементі списку."""
    if not items:
        return items

    tasks = [translate_to_uk(it.get("title", "")) for it in items]
    translated_titles = await asyncio.gather(*tasks, return_exceptions=True)

    result = []
    for it, title in zip(items, translated_titles):
        new_it = dict(it)
        if isinstance(title, str):
            new_it["title_uk"] = title   # перекладена версія
        else:
            new_it["title_uk"] = it.get("title", "")
        result.append(new_it)
    return result
