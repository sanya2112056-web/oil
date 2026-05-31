import os

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ── API-ключі (усі безкоштовні) ───────────────────────────────────────────────
EIA_API_KEY       = os.getenv("EIA_API_KEY", "")        # eia.gov/opendata
NEWSAPI_KEY       = os.getenv("NEWSAPI_KEY", "")        # newsapi.org (100/день)
GNEWS_KEY         = os.getenv("GNEWS_KEY", "")          # gnews.io (100/день)
THENEWSAPI_KEY    = os.getenv("THENEWSAPI_KEY", "")     # thenewsapi.com (100/день)
FINNHUB_KEY       = os.getenv("FINNHUB_KEY", "")        # finnhub.io (60/хв)
ALPHAVANTAGE_KEY  = os.getenv("ALPHAVANTAGE_KEY", "")   # alphavantage.co (25/день)

# ── Параметри бота ────────────────────────────────────────────────────────────
SIGNAL_THRESHOLD   = int(os.getenv("SIGNAL_THRESHOLD", "65"))   # мін % для відправки
SCAN_INTERVAL_MIN  = int(os.getenv("SCAN_INTERVAL_MIN", "10"))  # авто-сканування, хвилин

# ── Часовий пояс ──────────────────────────────────────────────────────────────
KYIV_TZ_OFFSET = 2  # UTC+2 (UTC+3 влітку за EEST — змінюйте за потреби)

# ── RSS-стрічки (без ключів, без лімітів) ────────────────────────────────────
RSS_FEEDS = {
    "OilPrice.com":   "https://oilprice.com/rss/main",
    "Reuters Energy": "https://feeds.reuters.com/reuters/businessNews",
    "CNBC Energy":    "https://www.cnbc.com/id/19836768/device/rss/rss.html",
    "Investing.com":  "https://www.investing.com/rss/commodities_Crude-Oil.rss",
}

# ── Ключові слова BULLISH ─────────────────────────────────────────────────────
BULLISH = {
    "opec cut": 5, "production cut": 5, "output cut": 5,
    "supply disruption": 5, "hormuz": 5, "blockade": 5,
    "supply shock": 5, "escalation": 5,
    "sanction": 4, "hurricane": 4, "inventory draw": 4,
    "drawdown": 4, "attack": 4, "force majeure": 4,
    "shut in": 4, "outage": 4, "geopolitical": 4,
    "demand surge": 3, "tension": 3,
}

# ── Ключові слова BEARISH ─────────────────────────────────────────────────────
BEARISH = {
    "opec increase": 5, "output hike": 5, "production increase": 5,
    "ceasefire": 5, "reopen": 5, "peace deal": 5,
    "truce": 4, "de-escalation": 4, "demand slowdown": 4,
    "inventory build": 4, "china slowdown": 4, "oversupply": 4,
    "glut": 4, "open strait": 4,
    "recession": 3, "weak demand": 3,
}

# ── Ваги джерел (1.0 = максимальна довіра) ───────────────────────────────────
SOURCE_WEIGHTS = {
    "reuters": 1.0, "bloomberg": 1.0, "eia": 1.0, "opec": 1.0,
    "cnbc": 0.9, "financial times": 0.9, "ft.com": 0.9,
    "oilprice": 0.7, "investing": 0.7,
    "gnews": 0.6, "thenewsapi": 0.6, "finnhub": 0.6, "alphavantage": 0.6,
    "twitter": 0.3, "x.com": 0.3,
}
