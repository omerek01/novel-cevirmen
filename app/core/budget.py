"""Gemini bütçe primitifleri (karar #13 / E-12).

İki primitif:
- `BG_TRANSLATE_SEM`: süreç-içi semafor — aynı anda EN FAZLA 1 arka plan
  çevirisi (kapı yalnız çekimi serileştirir; çeviri aşaması bunu kullanır).
- `counters(day, name, value)` tablosu: kalıcı günlük sayaçlar. Slice 5'in
  gece otomatik-çeviri bütçesi (günde `DAILY_AUTO_TRANSLATE_BUDGET` bölüm)
  bu sayaçtan okur; restart sayacı sıfırlamaz.
"""
from __future__ import annotations

import sqlite3
import threading

from . import db

BG_TRANSLATE_SEM = threading.Semaphore(1)

# Gece otomatik çevirisinin günlük bölüm bütçesi (karar #13 varsayılanı).
DAILY_AUTO_TRANSLATE_BUDGET = 20


def _connect() -> sqlite3.Connection:
    conn = db.connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS counters (
            day TEXT NOT NULL,
            name TEXT NOT NULL,
            value INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (day, name)
        )
        """
    )
    return conn


def increment(day: str, name: str, amount: int = 1) -> int:
    """Sayaç artır, yeni değeri döndür (E-16 gereği ON CONFLICT, REPLACE değil)."""
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO counters (day, name, value) VALUES (?, ?, ?) "
            "ON CONFLICT(day, name) DO UPDATE SET value = value + excluded.value",
            (day, name, amount),
        )
        row = conn.execute(
            "SELECT value FROM counters WHERE day = ? AND name = ?", (day, name)
        ).fetchone()
        conn.commit()
        return row[0] if row else 0
    finally:
        conn.close()


def get(day: str, name: str) -> int:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT value FROM counters WHERE day = ? AND name = ?", (day, name)
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else 0
