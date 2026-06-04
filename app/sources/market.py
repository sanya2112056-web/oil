"""Ринкові / фундаментальні / макро джерела.

Кожне джерело повертає dict {показник: значення}. yfinance — без ключа
(надійний фолбек ціни WTI/Brent). Решта — опційні (потрібен ключ).
"""
from __future__ import annotations

import asyncio
import os

import httpx

from app.sources.base import HealthResult, HealthStatus, SourceInfo
from app.utils.log import get_logger, record_event

log = get_logger("sources.market")


class MarketSource:
    info: SourceInfo

    @property
    def key(self) -> str:
        return self.info.env_var and (os.getenv(self.info.env_var) or "").strip() or ""

    async def fetch(self, client: httpx.AsyncClient) -> dict:
        raise NotImplementedError

    async def health_check(self, client: httpx.AsyncClient) -> HealthResult:
        if self.info.env_var is None:
            try:
                data = await self.fetch(client)
                return HealthResult(self.info, HealthStatus.NO_KEY_NEEDED,
                                    f"{len(data)} показників")
            except Exception as e:  # noqa: BLE001
                return HealthResult(self.info, HealthStatus.ERROR, str(e)[:160])
        if not self.info.is_configured():
            return HealthResult(self.info, HealthStatus.NOT_CONFIGURED, "ключ не доданий")
        try:
            data = await self.fetch(client)
            return HealthResult(self.info, HealthStatus.OK, f"{len(data)} показників")
        except Exception as e:  # noqa: BLE001
            record_event("error", self.info.key, str(e))
            return HealthResult(self.info, HealthStatus.ERROR, str(e)[:160])


# --------------------------------------------------------------------------
#  yfinance — БЕЗ ключа (база: завжди дає ціну WTI/Brent)
# --------------------------------------------------------------------------
class YFinanceSource(MarketSource):
    info = SourceInfo("yfinance", "Yahoo Finance (yfinance)", "market", None,
                      "https://pypi.org/project/yfinance/",
                      "Ф'ючерси CL=F (WTI), BZ=F (Brent), DX-Y (індекс долара) — без ключа")

    async def fetch(self, client):
        def _load():
            import yfinance as yf

            out = {}
            tickers = {"CL=F": "WTI", "BZ=F": "Brent", "DX-Y.NYB": "USD_Index"}
            for tk, label in tickers.items():
                try:
                    hist = yf.Ticker(tk).history(period="5d", interval="1d")
                    if hist is None or hist.empty:
                        continue
                    last = float(hist["Close"].iloc[-1])
                    out[f"{label}_price"] = round(last, 2)
                    if len(hist) >= 2:
                        prev = float(hist["Close"].iloc[-2])
                        if prev:
                            out[f"{label}_change_pct"] = round((last - prev) / prev * 100, 2)
                except Exception:  # noqa: BLE001
                    continue
            return out

        return await asyncio.to_thread(_load)


# --------------------------------------------------------------------------
#  EIA — запаси нафти, видобуток, WTI spot
# --------------------------------------------------------------------------
class EIASource(MarketSource):
    info = SourceInfo("eia", "EIA Open Data", "market", "EIA_KEY",
                      "https://www.eia.gov/opendata/register.php",
                      "Тижневі запаси сирої нафти, видобуток, WTI spot")

    async def fetch(self, client):
        if not self.key:
            return {}
        out = {}
        # Тижневі комерційні запаси сирої нафти (тис. барелів)
        r = await client.get(
            "https://api.eia.gov/v2/petroleum/stoc/wstk/data/",
            params={"api_key": self.key, "frequency": "weekly",
                    "data[0]": "value", "facets[series][]": "WCESTUS1",
                    "sort[0][column]": "period", "sort[0][direction]": "desc",
                    "length": 2})
        if r.status_code == 200:
            rows = r.json().get("response", {}).get("data", [])
            if rows:
                out["EIA_crude_stocks_kbbl"] = rows[0].get("value")
                if len(rows) >= 2 and rows[0].get("value") and rows[1].get("value"):
                    out["EIA_crude_stocks_change_kbbl"] = (
                        rows[0]["value"] - rows[1]["value"])
                out["EIA_stocks_period"] = rows[0].get("period")
        return out


# --------------------------------------------------------------------------
#  FRED — WTI, індекс долара, макро
# --------------------------------------------------------------------------
class FREDSource(MarketSource):
    info = SourceInfo("fred", "FRED (St. Louis Fed)", "market", "FRED_KEY",
                      "https://fred.stlouisfed.org/docs/api/api_key.html",
                      "WTI (DCOILWTICO), індекс долара (DTWEXBGS), макро")

    SERIES = {"DCOILWTICO": "FRED_WTI", "DTWEXBGS": "FRED_USD_BroadIndex"}

    async def fetch(self, client):
        if not self.key:
            return {}
        out = {}
        for series_id, label in self.SERIES.items():
            r = await client.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={"series_id": series_id, "api_key": self.key,
                        "file_type": "json", "sort_order": "desc", "limit": 1})
            if r.status_code == 200:
                obs = r.json().get("observations", [])
                if obs and obs[0].get("value") not in (None, "."):
                    try:
                        out[label] = float(obs[0]["value"])
                    except ValueError:
                        pass
        return out


# --------------------------------------------------------------------------
#  Finnhub — котирування/економкалендар
# --------------------------------------------------------------------------
class FinnhubQuoteSource(MarketSource):
    info = SourceInfo("finnhub_quote", "Finnhub Quote", "market", "FINNHUB_KEY",
                      "https://finnhub.io/",
                      "Котирування (той самий ключ, що й Finnhub News)")

    async def fetch(self, client):
        if not self.key:
            return {}
        out = {}
        # USO — ETF на нафту, як проксі настрою
        r = await client.get("https://finnhub.io/api/v1/quote",
                             params={"symbol": "USO", "token": self.key})
        if r.status_code == 200:
            d = r.json()
            if d.get("c"):
                out["Finnhub_USO_price"] = d.get("c")
                out["Finnhub_USO_change_pct"] = d.get("dp")
        return out


# --------------------------------------------------------------------------
#  Alpha Vantage — WTI, BRENT, макро
# --------------------------------------------------------------------------
class AlphaVantageSource(MarketSource):
    info = SourceInfo("alphavantage", "Alpha Vantage", "market", "ALPHAVANTAGE_KEY",
                      "https://www.alphavantage.co/support/#api-key",
                      "WTI, BRENT, макро-індикатори")

    async def fetch(self, client):
        if not self.key:
            return {}
        out = {}
        for func, label in (("WTI", "AV_WTI"), ("BRENT", "AV_Brent")):
            r = await client.get(
                "https://www.alphavantage.co/query",
                params={"function": func, "interval": "daily", "apikey": self.key})
            if r.status_code == 200:
                data = r.json().get("data", [])
                if data:
                    try:
                        out[label] = float(data[0].get("value"))
                    except (ValueError, TypeError):
                        pass
        return out


# --------------------------------------------------------------------------
#  Twelve Data — real-time WTI
# --------------------------------------------------------------------------
class TwelveDataSource(MarketSource):
    info = SourceInfo("twelvedata", "Twelve Data", "market", "TWELVEDATA_KEY",
                      "https://twelvedata.com/", "Real-time ціна WTI/USD")

    async def fetch(self, client):
        if not self.key:
            return {}
        r = await client.get("https://api.twelvedata.com/price",
                             params={"symbol": "WTI/USD", "apikey": self.key})
        if r.status_code == 200:
            p = r.json().get("price")
            if p:
                try:
                    return {"TwelveData_WTI": float(p)}
                except ValueError:
                    pass
        return {}


# --------------------------------------------------------------------------
#  Commodities-API — ціни товарів
# --------------------------------------------------------------------------
class CommoditiesAPISource(MarketSource):
    info = SourceInfo("commodities_api", "Commodities-API", "market",
                      "COMMODITIES_API_KEY", "https://commodities-api.com/",
                      "Спот-ціни товарів (WTIOIL, BRENTOIL)")

    async def fetch(self, client):
        if not self.key:
            return {}
        r = await client.get(
            "https://commodities-api.com/api/latest",
            params={"access_key": self.key, "base": "USD",
                    "symbols": "WTIOIL,BRENTOIL"})
        if r.status_code == 200:
            rates = r.json().get("data", {}).get("rates", {})
            out = {}
            # rates подаються як 1/ціна — інвертуємо для зручності
            for sym, label in (("WTIOIL", "CommAPI_WTI"), ("BRENTOIL", "CommAPI_Brent")):
                v = rates.get(sym)
                if v:
                    try:
                        out[label] = round(1 / float(v), 2)
                    except (ValueError, ZeroDivisionError):
                        pass
            return out
        return {}


ALL_MARKET_SOURCES: list[MarketSource] = [
    YFinanceSource(), EIASource(), FREDSource(), FinnhubQuoteSource(),
    AlphaVantageSource(), TwelveDataSource(), CommoditiesAPISource(),
]
