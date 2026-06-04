"""Новинні джерела: API (потрібен ключ) + RSS (без ключа).

Кожне джерело — підклас NewsSource з .info (метадані) та async fetch().
Якщо ключа немає — fetch() повертає [] (бот працює далі), а в health-check
джерело позначається ⛔. RSS-джерела не потребують ключа і працюють завжди.
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

import feedparser
import httpx

from app.sources.base import HealthResult, HealthStatus, NewsItem, SourceInfo
from app.utils.log import get_logger, record_event

log = get_logger("sources.news")

# Запит для пошукових API та Google-News RSS
OIL_QUERY = "crude oil OR WTI OR Brent OR OPEC OR petroleum OR Hormuz"


class NewsSource:
    info: SourceInfo

    @property
    def key(self) -> str:
        return self.info.env_var and (os.getenv(self.info.env_var) or "").strip() or ""

    async def fetch(self, client: httpx.AsyncClient) -> list[NewsItem]:
        raise NotImplementedError

    async def health_check(self, client: httpx.AsyncClient) -> HealthResult:
        if self.info.env_var is None:
            # RSS / без ключа
            try:
                items = await self.fetch(client)
                return HealthResult(self.info, HealthStatus.NO_KEY_NEEDED,
                                    f"{len(items)} новин")
            except Exception as e:  # noqa: BLE001
                return HealthResult(self.info, HealthStatus.ERROR, str(e)[:160])
        if not self.info.is_configured():
            return HealthResult(self.info, HealthStatus.NOT_CONFIGURED, "ключ не доданий")
        try:
            items = await self.fetch(client)
            return HealthResult(self.info, HealthStatus.OK, f"{len(items)} новин")
        except Exception as e:  # noqa: BLE001
            record_event("error", self.info.key, str(e))
            return HealthResult(self.info, HealthStatus.ERROR, str(e)[:160])


# --------------------------------------------------------------------------
#  API-джерела (потрібен ключ)
# --------------------------------------------------------------------------
class NewsAPISource(NewsSource):
    info = SourceInfo("newsapi", "NewsAPI.org", "news", "NEWSAPI_KEY",
                      "https://newsapi.org/register", "Глобальні новини, пошук за запитом")

    async def fetch(self, client):
        if not self.key:
            return []
        r = await client.get(
            "https://newsapi.org/v2/everything",
            params={"q": OIL_QUERY, "language": "en", "sortBy": "publishedAt",
                    "pageSize": 30, "apiKey": self.key},
        )
        r.raise_for_status()
        out = []
        for a in r.json().get("articles", []):
            out.append(NewsItem(
                title=a.get("title") or "", url=a.get("url") or "",
                source="NewsAPI", summary=a.get("description") or "",
                published=a.get("publishedAt") or ""))
        return out


class GNewsSource(NewsSource):
    info = SourceInfo("gnews", "GNews.io", "news", "GNEWS_KEY",
                      "https://gnews.io/", "Новини з пошуком")

    async def fetch(self, client):
        if not self.key:
            return []
        r = await client.get(
            "https://gnews.io/api/v4/search",
            params={"q": OIL_QUERY, "lang": "en", "max": 25, "apikey": self.key})
        r.raise_for_status()
        return [NewsItem(title=a.get("title", ""), url=a.get("url", ""),
                         source="GNews", summary=a.get("description", ""),
                         published=a.get("publishedAt", ""))
                for a in r.json().get("articles", [])]


class NewsDataSource(NewsSource):
    info = SourceInfo("newsdata", "NewsData.io", "news", "NEWSDATA_KEY",
                      "https://newsdata.io/", "Новини, багато мов")

    async def fetch(self, client):
        if not self.key:
            return []
        r = await client.get(
            "https://newsdata.io/api/1/news",
            params={"apikey": self.key, "q": OIL_QUERY, "language": "en"})
        r.raise_for_status()
        return [NewsItem(title=a.get("title", ""), url=a.get("link", ""),
                         source="NewsData", summary=a.get("description", "") or "",
                         published=a.get("pubDate", ""))
                for a in r.json().get("results", []) or []]


class MarketauxSource(NewsSource):
    info = SourceInfo("marketaux", "Marketaux", "news", "MARKETAUX_KEY",
                      "https://www.marketaux.com/", "Фінансові/ринкові новини")

    async def fetch(self, client):
        if not self.key:
            return []
        r = await client.get(
            "https://api.marketaux.com/v1/news/all",
            params={"api_token": self.key, "search": OIL_QUERY,
                    "language": "en", "limit": 25})
        r.raise_for_status()
        return [NewsItem(title=a.get("title", ""), url=a.get("url", ""),
                         source="Marketaux", summary=a.get("description", "") or "",
                         published=a.get("published_at", ""))
                for a in r.json().get("data", [])]


class MediastackSource(NewsSource):
    info = SourceInfo("mediastack", "Mediastack", "news", "MEDIASTACK_KEY",
                      "https://mediastack.com/", "Новинна стрічка")

    async def fetch(self, client):
        if not self.key:
            return []
        r = await client.get(
            "http://api.mediastack.com/v1/news",
            params={"access_key": self.key, "keywords": "oil,crude,OPEC",
                    "languages": "en", "limit": 25})
        r.raise_for_status()
        return [NewsItem(title=a.get("title", "") or "", url=a.get("url", "") or "",
                         source="Mediastack", summary=a.get("description", "") or "",
                         published=a.get("published_at", ""))
                for a in r.json().get("data", [])]


class FinnhubNewsSource(NewsSource):
    info = SourceInfo("finnhub_news", "Finnhub News", "news", "FINNHUB_KEY",
                      "https://finnhub.io/", "Загальні ринкові новини")

    async def fetch(self, client):
        if not self.key:
            return []
        r = await client.get(
            "https://finnhub.io/api/v1/news",
            params={"category": "general", "token": self.key})
        r.raise_for_status()
        return [NewsItem(title=a.get("headline", ""), url=a.get("url", ""),
                         source="Finnhub", summary=a.get("summary", "") or "")
                for a in r.json() if isinstance(a, dict)]


class GuardianSource(NewsSource):
    info = SourceInfo("guardian", "The Guardian", "news", "GUARDIAN_KEY",
                      "https://open-platform.theguardian.com/access/", "Якісна журналістика")

    async def fetch(self, client):
        if not self.key:
            return []
        r = await client.get(
            "https://content.guardianapis.com/search",
            params={"q": "oil OR OPEC OR crude", "api-key": self.key,
                    "show-fields": "trailText", "page-size": 25})
        r.raise_for_status()
        out = []
        for a in r.json().get("response", {}).get("results", []):
            out.append(NewsItem(
                title=a.get("webTitle", ""), url=a.get("webUrl", ""),
                source="Guardian",
                summary=(a.get("fields") or {}).get("trailText", ""),
                published=a.get("webPublicationDate", "")))
        return out


class NYTimesSource(NewsSource):
    info = SourceInfo("nytimes", "NYTimes", "news", "NYTIMES_KEY",
                      "https://developer.nytimes.com/", "Article Search API")

    async def fetch(self, client):
        if not self.key:
            return []
        r = await client.get(
            "https://api.nytimes.com/svc/search/v2/articlesearch.json",
            params={"q": "crude oil OPEC", "api-key": self.key, "sort": "newest"})
        r.raise_for_status()
        out = []
        for a in r.json().get("response", {}).get("docs", []):
            out.append(NewsItem(
                title=(a.get("headline") or {}).get("main", ""),
                url=a.get("web_url", ""), source="NYTimes",
                summary=a.get("abstract", "") or "",
                published=a.get("pub_date", "")))
        return out


class CurrentsSource(NewsSource):
    info = SourceInfo("currents", "Currents API", "news", "CURRENTS_KEY",
                      "https://currentsapi.services/", "Новинна стрічка")

    async def fetch(self, client):
        if not self.key:
            return []
        r = await client.get(
            "https://api.currentsapi.services/v1/search",
            params={"keywords": "oil crude OPEC", "language": "en",
                    "apiKey": self.key})
        r.raise_for_status()
        return [NewsItem(title=a.get("title", ""), url=a.get("url", ""),
                         source="Currents", summary=a.get("description", "") or "",
                         published=a.get("published", ""))
                for a in r.json().get("news", [])]


# --------------------------------------------------------------------------
#  RSS-джерела (БЕЗ ключа — гарантують роботу навіть з 0 API)
# --------------------------------------------------------------------------
class RSSSource(NewsSource):
    def __init__(self, key: str, name: str, url: str, note: str = ""):
        self.info = SourceInfo(key, name, "news", None, url, note or "RSS, без ключа")
        self._url = url

    async def fetch(self, client):
        def _parse():
            feed = feedparser.parse(self._url)
            items = []
            for e in feed.entries[:30]:
                items.append(NewsItem(
                    title=getattr(e, "title", ""),
                    url=getattr(e, "link", ""),
                    source=f"RSS:{self.info.name}",
                    summary=getattr(e, "summary", "") or "",
                    published=getattr(e, "published", "") or ""))
            return items

        return await asyncio.to_thread(_parse)


RSS_SOURCES = [
    RSSSource("rss_oilprice", "OilPrice.com", "https://oilprice.com/rss/main"),
    RSSSource("rss_rigzone", "Rigzone", "https://www.rigzone.com/news/rss/rigzone_latest.aspx"),
    RSSSource("rss_eia", "EIA Today in Energy", "https://www.eia.gov/rss/todayinenergy.xml"),
    RSSSource("rss_investing", "Investing.com Commodities",
              "https://www.investing.com/rss/commodities.rss"),
    RSSSource("rss_ogj", "Oil & Gas Journal", "https://www.ogj.com/__rss/website-scheduled-content.xml"),
    RSSSource("rss_gnews_oil", "Google News: Oil",
              "https://news.google.com/rss/search?q=" + OIL_QUERY.replace(" ", "+")
              + "&hl=en-US&gl=US&ceid=US:en"),
    RSSSource("rss_gnews_hormuz", "Google News: Hormuz/Iran oil",
              "https://news.google.com/rss/search?q=Strait+of+Hormuz+OR+Iran+oil"
              "&hl=en-US&gl=US&ceid=US:en"),
]

API_NEWS_SOURCES = [
    NewsAPISource(), GNewsSource(), NewsDataSource(), MarketauxSource(),
    MediastackSource(), FinnhubNewsSource(), GuardianSource(), NYTimesSource(),
    CurrentsSource(),
]

ALL_NEWS_SOURCES: list[NewsSource] = API_NEWS_SOURCES + RSS_SOURCES
