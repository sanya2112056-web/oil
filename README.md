# 🛢️ OIL SCANER — Telegram AI-агент аналізу нафти (WTI)

Публічний Telegram-бот-аналітик. Безперервно читає десятки безкоштовних
новинних джерел; щойно виходить **будь-яка** новина про нафту, що може
вплинути на ціну, бот:

1. збирає ринкові показники (ціна WTI/Brent, запаси EIA, індекс долара, макро);
2. проганяє новину + дані через **Claude AI** (системний промпт побудований на
   глибокому дослідженні ринку WTI 2026 — геополітична премія Іран/Ормуз,
   історичні патерни реакцій, еталонний кейс стрибка +5% 1 червня 2026);
3. надсилає підписникам сигнал: **напрямок · ймовірність · орієнтовний % руху ·
   горизонт часу · ризики**.

> ⚠️ Це аналітичний інструмент, а не фінансова порада.

---

## ✨ Можливості

- **Публічний**: будь-хто тисне `/start` → підписується → отримує сигнали.
- **Працює навіть без жодного опційного ключа**: новини беруться з безкоштовних
  RSS, ціна — з `yfinance`. Додаси ключі — покриття глибшає.
- **Кнопки**: 📡 Сканувати зараз · 📊 Останній сигнал · 📜 Історія · 📈 Знімок
  ринку · 🩺 **Перевірка API** (статус кожного джерела) · 📋 **Список API** ·
  ⚙️ Налаштування · 🤖 **AI-асистент** · підписка/відписка.
- **AI-асистент**: окремий чат-режим — пояснює роботу бота, допомагає з ключами,
  діагностує що працює/не працює (бачить живий health + останні помилки).

---

## 🚀 Деплой: GitHub → Railway

### 1. Залити на GitHub
```bash
git init
git add .
git commit -m "OIL SCANER bot"
git branch -M main
git remote add origin https://github.com/<ти>/<repo>.git
git push -u origin main
```

### 2. Railway
1. [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo** → обери репозиторій.
2. Railway сам визначить Python (Nixpacks) і запустить `python -m app.main`
   (див. `Procfile` / `railway.json`).
3. Вкладка **Variables** → додай ключі (мінімум два обов'язкові, решта — опційно).
4. (Опційно, щоб БД переживала редеплої) **New → Volume**, примонтуй у `/data`,
   і встанови `DATABASE_URL=sqlite:////data/oilscaner.db`
   *(або підключи Railway Postgres — тоді просто скопіюй наданий `DATABASE_URL`).*
5. Deploy. У логах має з'явитись «Бот запущено». Відкрий бота в Telegram → `/start`.

> Вебхуки не потрібні — бот працює через long-polling (тип сервісу — worker).

### 3. Створити Telegram-бота
[@BotFather](https://t.me/BotFather) → `/newbot` → скопіюй токен у `TELEGRAM_BOT_TOKEN`.

---

## 🔑 Змінні середовища

### Обов'язкові
| Змінна | Де взяти |
|---|---|
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/ |

### Налаштування (є дефолти)
| Змінна | Дефолт | Опис |
|---|---|---|
| `ADMIN_CHAT_ID` | — | твій Telegram id (сповіщення про старт/помилки), дізнатись: [@userinfobot](https://t.me/userinfobot) |
| `POLL_INTERVAL_MINUTES` | `4` | як часто опитувати новини |
| `MIN_IMPORTANCE` | `3` | поріг важливості новини (1–10), нижче = більше сигналів |
| `MAX_NEWS_PER_CYCLE` | `4` | макс. новин на цикл (захист бюджету) |
| `SIGNAL_COOLDOWN_MINUTES` | `20` | пауза між авто-сигналами |
| `ANALYSIS_MODEL` | `claude-opus-4-8` | модель аналізу |
| `ASSISTANT_MODEL` | `claude-haiku-4-5-20251001` | модель асистента |
| `DATABASE_URL` | `sqlite:///data/oilscaner.db` | БД (або Postgres) |

### Новинні API (опційно — додавай скільки треба)
NewsAPI.org (`NEWSAPI_KEY`) · GNews (`GNEWS_KEY`) · NewsData.io (`NEWSDATA_KEY`) ·
Marketaux (`MARKETAUX_KEY`) · Mediastack (`MEDIASTACK_KEY`) · Finnhub
(`FINNHUB_KEY`) · The Guardian (`GUARDIAN_KEY`) · NYTimes (`NYTIMES_KEY`) ·
Currents (`CURRENTS_KEY`).
**Без ключа (RSS):** OilPrice, Rigzone, EIA, Investing.com, Oil & Gas Journal,
Google News — працюють завжди.

### Ринкові / макро API (опційно)
EIA (`EIA_KEY`) · FRED (`FRED_KEY`) · Alpha Vantage (`ALPHAVANTAGE_KEY`) ·
Twelve Data (`TWELVEDATA_KEY`) · Commodities-API (`COMMODITIES_API_KEY`).
**Без ключа:** Yahoo Finance через `yfinance` (WTI/Brent/USD-index).

> Повний список з посиланнями на реєстрацію також доступний у боті:
> кнопка **📋 Список API**. Статус кожного — кнопка **🩺 Перевірка API**.

---

## 💻 Локальний запуск
```bash
pip install -r requirements.txt
copy .env.example .env   # (Windows)  /  cp .env.example .env (Linux/Mac)
# впиши щонайменше TELEGRAM_BOT_TOKEN і ANTHROPIC_API_KEY
python -m app.main
```
У Telegram: `/start` → меню. Навіть без опційних ключів бот живий: RSS дають
новини, yfinance — ціну, «Перевірка API» покаже ⛔ для невказаних.

---

## 🗂️ Структура
```
app/
  main.py            # запуск: БД + бот + періодичний скан
  config.py          # змінні середовища
  bot/               # handlers, keyboards, messages, assistant
  core/              # news_aggregator, relevance, data_collector,
                     # claude_client, analyzer, pipeline, scheduler
  sources/           # base, registry, news (API+RSS), market (yfinance+API)
  storage/db.py      # підписники, сигнали, дедуп
  utils/             # логування + буфер помилок
```

Мозок аналізу — `app/core/analyzer.py` (системний промпт на базі дослідження).
Реєстр джерел і health — `app/sources/registry.py`.
