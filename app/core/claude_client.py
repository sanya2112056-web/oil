"""Обгортка над Anthropic SDK: prompt caching, ретраї, JSON-розбір."""
from __future__ import annotations

import json
import re

from anthropic import AsyncAnthropic
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_exponential)

from app.config import ANALYSIS_MODEL, ANTHROPIC_API_KEY, ASSISTANT_MODEL
from app.utils.log import get_logger, record_event

log = get_logger("core.claude")

_client: AsyncAnthropic | None = None


def client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def is_ready() -> bool:
    return bool(ANTHROPIC_API_KEY)


@retry(reraise=True, stop=stop_after_attempt(3),
       wait=wait_exponential(min=2, max=20),
       retry=retry_if_exception_type(Exception))
async def _create(model: str, system: list | str, messages: list,
                  max_tokens: int = 1400, temperature: float = 0.2):
    return await client().messages.create(
        model=model, system=system, messages=messages,
        max_tokens=max_tokens, temperature=temperature)


async def analyze(system_prompt: str, user_payload: str) -> dict:
    """Запускає аналіз через модель ANALYSIS_MODEL і повертає JSON-результат.

    Великий системний промпт кешується (cache_control) — здешевлює повторні
    виклики. Якщо модель поверне не-JSON — намагаємось витягти JSON-блок.
    """
    system = [{
        "type": "text",
        "text": system_prompt,
        "cache_control": {"type": "ephemeral"},
    }]
    resp = await _create(
        ANALYSIS_MODEL, system,
        [{"role": "user", "content": user_payload}],
        max_tokens=1500, temperature=0.2)
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return _parse_json(text)


async def assistant_reply(system_prompt: str, history: list[dict],
                          user_text: str) -> str:
    """Вільний чат AI-асистента (дешева модель)."""
    messages = history + [{"role": "user", "content": user_text}]
    resp = await _create(ASSISTANT_MODEL,
                         [{"type": "text", "text": system_prompt}],
                         messages, max_tokens=1000, temperature=0.4)
    return "".join(b.text for b in resp.content
                   if getattr(b, "type", "") == "text").strip()


def _parse_json(text: str) -> dict:
    text = text.strip()
    # прибираємо ```json ... ``` якщо є
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        record_event("error", "claude", f"JSON parse: {e}")
        return {"_raw": text, "_parse_error": str(e)}
