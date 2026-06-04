"""Шар зберігання: підписники, історія сигналів, кеш дедупу, налаштування.

SQLite за замовчуванням; Postgres — через DATABASE_URL. Усі операції
синхронні й швидкі (виконуються через asyncio.to_thread у викликачів).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import (Boolean, Column, DateTime, Integer, String, Text,
                        create_engine, func, select)
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import DATABASE_URL
from app.utils.log import get_logger

log = get_logger("storage.db")


def _normalize_url(url: str) -> str:
    # Railway/Heroku інколи дають postgres:// — SQLAlchemy хоче postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
        if path and os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
    return url


_URL = _normalize_url(DATABASE_URL)
engine = create_engine(_URL, future=True,
                       connect_args={"check_same_thread": False}
                       if _URL.startswith("sqlite") else {})


class Base(DeclarativeBase):
    pass


class Subscriber(Base):
    __tablename__ = "subscribers"
    chat_id = Column(String, primary_key=True)
    username = Column(String, default="")
    subscribed = Column(Boolean, default=True)
    notifications = Column(Boolean, default=True)
    min_importance = Column(Integer, default=0)   # 0 = брати глобальний
    language = Column(String, default="uk")
    mode = Column(String, default="menu")          # menu | assistant
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SignalRow(Base):
    __tablename__ = "signals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    news_title = Column(Text, default="")
    news_url = Column(Text, default="")
    signal = Column(String, default="")
    payload = Column(Text, default="{}")           # повний JSON аналізу


class SeenNews(Base):
    __tablename__ = "seen_news"
    dedup_key = Column(String, primary_key=True)
    title = Column(Text, default="")
    seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_db() -> None:
    Base.metadata.create_all(engine)
    log.info("База ініціалізована: %s", _URL.split("@")[-1])


# --- Підписники ------------------------------------------------------------
def upsert_subscriber(chat_id: int | str, username: str = "") -> None:
    cid = str(chat_id)
    with Session(engine) as s:
        sub = s.get(Subscriber, cid)
        if sub is None:
            sub = Subscriber(chat_id=cid, username=username, subscribed=True)
            s.add(sub)
        else:
            sub.subscribed = True
            if username:
                sub.username = username
        s.commit()


def set_subscribed(chat_id: int | str, value: bool) -> None:
    cid = str(chat_id)
    with Session(engine) as s:
        sub = s.get(Subscriber, cid)
        if sub:
            sub.subscribed = value
            s.commit()


def set_mode(chat_id: int | str, mode: str) -> None:
    cid = str(chat_id)
    with Session(engine) as s:
        sub = s.get(Subscriber, cid)
        if sub:
            sub.mode = mode
            s.commit()


def get_mode(chat_id: int | str) -> str:
    with Session(engine) as s:
        sub = s.get(Subscriber, str(chat_id))
        return sub.mode if sub else "menu"


def toggle_notifications(chat_id: int | str) -> bool:
    cid = str(chat_id)
    with Session(engine) as s:
        sub = s.get(Subscriber, cid)
        if not sub:
            return False
        sub.notifications = not sub.notifications
        s.commit()
        return sub.notifications


def get_subscriber(chat_id: int | str) -> dict | None:
    with Session(engine) as s:
        sub = s.get(Subscriber, str(chat_id))
        if not sub:
            return None
        return {"chat_id": sub.chat_id, "subscribed": sub.subscribed,
                "notifications": sub.notifications, "mode": sub.mode,
                "language": sub.language}


def active_subscriber_ids() -> list[str]:
    with Session(engine) as s:
        rows = s.execute(
            select(Subscriber.chat_id).where(
                Subscriber.subscribed.is_(True),
                Subscriber.notifications.is_(True))
        ).all()
        return [r[0] for r in rows]


def subscriber_count() -> int:
    with Session(engine) as s:
        return int(s.execute(
            select(func.count()).select_from(Subscriber)
            .where(Subscriber.subscribed.is_(True))).scalar() or 0)


# --- Дедуп новин -----------------------------------------------------------
def is_new(dedup_key: str) -> bool:
    with Session(engine) as s:
        return s.get(SeenNews, dedup_key) is None


def mark_seen(dedup_key: str, title: str = "") -> None:
    with Session(engine) as s:
        if s.get(SeenNews, dedup_key) is None:
            s.add(SeenNews(dedup_key=dedup_key, title=title))
            s.commit()


def cooldown_active(minutes: int) -> bool:
    """True, якщо останній сигнал був надто недавно (захист від спаму)."""
    if minutes <= 0:
        return False
    with Session(engine) as s:
        last = s.execute(
            select(SignalRow.created_at).order_by(SignalRow.id.desc()).limit(1)
        ).scalar()
    if not last:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last < timedelta(minutes=minutes)


# --- Сигнали ---------------------------------------------------------------
def save_signal(news_title: str, news_url: str, signal: str, payload: dict) -> int:
    with Session(engine) as s:
        row = SignalRow(news_title=news_title[:500], news_url=news_url[:500],
                        signal=signal, payload=json.dumps(payload, ensure_ascii=False))
        s.add(row)
        s.commit()
        return row.id


def latest_signals(limit: int = 1) -> list[dict]:
    with Session(engine) as s:
        rows = s.execute(
            select(SignalRow).order_by(SignalRow.id.desc()).limit(limit)).scalars().all()
        out = []
        for r in rows:
            try:
                payload = json.loads(r.payload)
            except json.JSONDecodeError:
                payload = {}
            out.append({"id": r.id, "created_at": r.created_at,
                        "news_title": r.news_title, "news_url": r.news_url,
                        "signal": r.signal, "payload": payload})
        return out
