"""
news_fetcher.py — збирає новини з RSS + безкоштовних API
і повертає єдиний дедублікований список.
"""
import asyncio
import logging

import aiohttp
import feedparser

import config

log = logging.getLogger("news_fetcher")

# Слова, за якими ми відбираємо нафтові новини з загальних стрічок
OIL_KEYWORDS = ("oil", "brent", "crude", "opec", "petroleum", "wti",
                "hormuz", "energy", "barrel", "refinery", "lng")


# ─────────────────────────────────────────────────────────────────────────────
# Утиліти
# ─────────────────────────────────────────────────────────────────────────────

def _is_oil(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in OIL_KEYWORDS)


async def _get_json(session: aiohttp.ClientSession, url: str,
                    params: dict = None, timeout: int = 15) -> dict | None:
    """GET → JSON з 3-ма спробами та exponential backoff."""
    for attempt in range(3):
        try:
            async with session.get(
                url, params=params,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as r:
                if r.status == 200:
                    return await r.json(content_type=None)
                log.warning("HTTP %s for %s", r.status, url)
                if r.status in (401, 403, 429):
                    return None           # ключ невірний або ліміт — не повторюємо
        except Exception as e:
            log.warning("fetch err %s (try %s): %s", url, attempt + 1, e)
        await asyncio.sleep(1.5 ** (attempt + 1))
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Джерела новин
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_rss() -> list[dict]:
    """RSS-стрічки — безкоштовно, без лімітів, найшвидші."""
    items = []
    loop = asyncio.get_event_loop()
    for name, url in config.RSS_FEEDS.items():
        try:
            feed = await loop.run_in_executor(None, feedparser.parse, url)
            for e in feed.entries[:20]:
                title   = e.get("title", "")
                summary = e.get("summary", "")
                if _is_oil(title) or _is_oil(summary):
                    items.append({
                        "title":     title,
                        "source":    name,
                        "url":       e.get("link", ""),
                        "published": e.get("published", ""),
                    })
        except Exception as ex:
            log.warning("RSS '%s' failed: %s", name, ex)
    return items


async def fetch_newsapi(session: aiohttp.ClientSession) -> list[dict]:
    """newsapi.org — 100 запитів/день (free, 24-год затримка)."""
    if not config.NEWSAPI_KEY:
        return []
    data = await _get_json(session, "https://newsapi.org/v2/everything", params={
        "q":        "brent OR crude oil OR opec",
        "language": "en",
        "sortBy":   "publishedAt",
        "pageSize": 10,
        "apiKey":   config.NEWSAPI_KEY,
    })
    if not data or data.get("status") != "ok":
        return []
    return [{
        "title":     a["title"],
        "source":    a["source"]["name"],
        "url":       a["url"],
        "published": a.get("publishedAt", ""),
    } for a in data.get("articles", []) if _is_oil(a.get("title", ""))]


async def fetch_gnews(session: aiohttp.ClientSession) -> list[dict]:
    """gnews.io — 100 запитів/день (free)."""
    if not config.GNEWS_KEY:
        return []
    data = await _get_json(session, "https://gnews.io/api/v4/search", params={
        "q":       "brent OR crude oil OR opec",
        "lang":    "en",
        "max":     10,
        "apikey":  config.GNEWS_KEY,
    })
    if not data:
        return []
    return [{
        "title":     a["title"],
        "source":    a.get("source", {}).get("name", "GNews"),
        "url":       a["url"],
        "published": a.get("publishedAt", ""),
    } for a in data.get("articles", [])]


async def fetch_thenewsapi(session: aiohttp.ClientSession) -> list[dict]:
    """thenewsapi.com — 100 запитів/день (free)."""
    if not config.THENEWSAPI_KEY:
        return []
    data = await _get_json(session, "https://api.thenewsapi.com/v1/news/all", params={
        "api_token": config.THENEWSAPI_KEY,
        "search":    "brent | crude oil | opec",
        "language":  "en",
        "limit":     5,
    })
    if not data:
        return []
    return [{
        "title":     a["title"],
        "source":    a.get("source", "TheNewsAPI"),
        "url":       a["url"],
        "published": a.get("published_at", ""),
    } for a in data.get("data", [])]


async def fetch_finnhub(session: aiohttp.ClientSession) -> list[dict]:
    """finnhub.io — 60 запитів/хв (free)."""
    if not config.FINNHUB_KEY:
        return []
    data = await _get_json(session, "https://finnhub.io/api/v1/news", params={
        "category": "general",
        "token":    config.FINNHUB_KEY,
    })
    if not isinstance(data, list):
        return []
    out = []
    for a in data[:40]:
        if _is_oil(a.get("headline", "")):
            out.append({
                "title":     a["headline"],
                "source":    a.get("source", "Finnhub"),
                "url":       a.get("url", ""),
                "published": "",
            })
    return out[:10]


async def fetch_alphavantage(session: aiohttp.ClientSession) -> list[dict]:
    """alphavantage.co NEWS_SENTIMENT — 25 запитів/день (free)."""
    if not config.ALPHAVANTAGE_KEY:
        return []
    data = await _get_json(session, "https://www.alphavantage.co/query", params={
        "function": "NEWS_SENTIMENT",
        "topics":   "energy_transportation",
        "apikey":   config.ALPHAVANTAGE_KEY,
        "limit":    15,
    })
    if not data or "feed" not in data:
        return []
    out = []
    for a in data["feed"]:
        if _is_oil(a.get("title", "")):
            out.append({
                "title":        a["title"],
                "source":       a.get("source", "AlphaVantage"),
                "url":          a.get("url", ""),
                "published":    a.get("time_published", ""),
                "av_sentiment": a.get("overall_sentiment_score", 0),
            })
    return out[:10]


# ─────────────────────────────────────────────────────────────────────────────
# EIA запаси (офіційний урядовий API, безкоштовний)
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_eia_crude_stocks(session: aiohttp.ClientSession) -> dict | None:
    """
    Повертає останнє + попереднє тижневе значення комерційних
    запасів сирої нафти США (тис. барелів).
    Вихід EIA: кожну середу ~10:30 ET (14:30 UTC влітку / 15:30 UTC взимку).
    """
    if not config.EIA_API_KEY:
        return None
    data = await _get_json(
        session,
        "https://api.eia.gov/v2/petroleum/stoc/wstk/data/",
        params={
            "api_key":              config.EIA_API_KEY,
            "frequency":            "weekly",
            "data[0]":              "value",
            "facets[product][]":    "EPC0",
            "sort[0][column]":      "period",
            "sort[0][direction]":   "desc",
            "length":               2,
        },
    )
    try:
        rows   = data["response"]["data"]
        latest = rows[0]
        prev   = rows[1]
        change = float(latest["value"]) - float(prev["value"])
        return {
            "period":    latest["period"],
            "value_kb":  float(latest["value"]),   # тисяч барелів
            "change_kb": change,
        }
    except Exception as e:
        log.warning("EIA parse error: %s", e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Агрегатор
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_all_news() -> list[dict]:
    """Збирає новини з усіх джерел, дедублікує за заголовком."""
    rss_items = await fetch_rss()

    async with aiohttp.ClientSession() as s:
        results = await asyncio.gather(
            fetch_newsapi(s),
            fetch_gnews(s),
            fetch_thenewsapi(s),
            fetch_finnhub(s),
            fetch_alphavantage(s),
            return_exceptions=True,
        )

    all_items = list(rss_items)
    for r in results:
        if isinstance(r, list):
            all_items.extend(r)

    # Дедублікація
    seen, dedup = set(), []
    for it in all_items:
        key = it.get("title", "").strip().lower()[:90]
        if key and key not in seen:
            seen.add(key)
            dedup.append(it)

    log.info("fetch_all_news: %d uniq items", len(dedup))
    return dedup


# ─────────────────────────────────────────────────────────────────────────────
# Перевірка стану кожного API (для команди /check)
# ─────────────────────────────────────────────────────────────────────────────

async def check_apis() -> dict[str, str]:
    status = {}

    # RSS
    rss = await fetch_rss()
    status["RSS-стрічки"] = f"✅ {len(rss)} нафтових статей" if rss else "❌ нічого не отримано"

    async with aiohttp.ClientSession() as s:

        # EIA
        if config.EIA_API_KEY:
            eia = await fetch_eia_crude_stocks(s)
            status["EIA (запаси)"] = (
                f"✅ {eia['period']}: {eia['value_kb']:,.0f} тис. бар. "
                f"({eia['change_kb']:+,.0f})"
                if eia else "❌ помилка запиту"
            )
        else:
            status["EIA (запаси)"] = "⚠️ ключ не вказано"

        # NewsAPI
        if config.NEWSAPI_KEY:
            d = await _get_json(s, "https://newsapi.org/v2/everything",
                                params={"q": "oil", "pageSize": 1,
                                        "apiKey": config.NEWSAPI_KEY})
            status["NewsAPI"] = "✅ OK" if (d and d.get("status") == "ok") else "❌ помилка"
        else:
            status["NewsAPI"] = "⚠️ ключ не вказано"

        # GNews
        if config.GNEWS_KEY:
            d = await _get_json(s, "https://gnews.io/api/v4/search",
                                params={"q": "oil", "max": 1, "apikey": config.GNEWS_KEY})
            status["GNews"] = "✅ OK" if d else "❌ помилка"
        else:
            status["GNews"] = "⚠️ ключ не вказано"

        # TheNewsAPI
        if config.THENEWSAPI_KEY:
            d = await _get_json(s, "https://api.thenewsapi.com/v1/news/all",
                                params={"api_token": config.THENEWSAPI_KEY,
                                        "limit": 1, "search": "oil"})
            status["TheNewsAPI"] = "✅ OK" if d else "❌ помилка"
        else:
            status["TheNewsAPI"] = "⚠️ ключ не вказано"

        # Finnhub
        if config.FINNHUB_KEY:
            d = await _get_json(s, "https://finnhub.io/api/v1/news",
                                params={"category": "general",
                                        "token": config.FINNHUB_KEY})
            status["Finnhub"] = "✅ OK" if isinstance(d, list) else "❌ помилка"
        else:
            status["Finnhub"] = "⚠️ ключ не вказано"

        # Alpha Vantage
        if config.ALPHAVANTAGE_KEY:
            d = await _get_json(s, "https://www.alphavantage.co/query",
                                params={"function": "NEWS_SENTIMENT",
                                        "topics": "energy_transportation",
                                        "apikey": config.ALPHAVANTAGE_KEY,
                                        "limit": 1})
            status["AlphaVantage"] = "✅ OK" if (d and "feed" in d) else "❌ помилка"
        else:
            status["AlphaVantage"] = "⚠️ ключ не вказано"

    return status
