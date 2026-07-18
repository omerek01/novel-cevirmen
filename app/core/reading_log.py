"""Okuma günlüğü — "bugün / toplam bölüm" istatistiğinin veri kaynağı.

Satırı İSTEMCİ yazar (okuyucuda bölüm başarıyla render edilince `POST
/api/reading-log`): SW cache-first GET'i sunucuya ulaştırmadığı için sunucu-yanı
loglama imkânsızdır; prefetch/arka plan istekleri de böylece hiç loglanmaz.
`day` istemcinin YEREL günüdür — "bugün" sayacı gece yarısı UTC'ye kaymaz.
Tekilleştirme UNIQUE indeksledir (aynı gün aynı bölüm ikinci kez sayılmaz).
Yazım best-effort: DB meşgulse kayıt düşer, okuma asla bozulmaz.
"""
from __future__ import annotations

import re
import sqlite3

from . import db

_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _connect() -> sqlite3.Connection:
    conn = db.connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reading_log (
            day TEXT NOT NULL,
            slug TEXT NOT NULL,
            url TEXT NOT NULL,
            ts REAL,
            UNIQUE(day, slug, url)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reading_log_ts ON reading_log(ts)")
    return conn


def log_read(day: str, slug: str, url: str) -> bool:
    """Bir bölüm okumasını günlüğe yaz (günde bölüm başına bir kez).

    True = yeni satır yazıldı; False = tekrar/geçersiz girdi/DB meşgul (yutulur —
    istatistik 1 eksik kalır, kabul edilmiş maliyet).
    """
    day = (day or "").strip()
    if not _DAY_RE.match(day) or not slug or not url:
        return False
    import time

    try:
        conn = _connect()
        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO reading_log (day, slug, url, ts) "
                "VALUES (?, ?, ?, ?)",
                (day, slug, url, time.time()),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return False  # best-effort: kilitli DB okuma akışını asla bozmasın


def stats(day: str) -> dict:
    """`{"today": N, "total": M}` — tek sorgu (N+1 yok).

    today: verilen (yerel) günde okunan benzersiz bölüm sayısı.
    total: tüm zamanlarda okunan benzersiz bölüm sayısı (D-B11v2: 'toplam'
    tanımı = benzersiz okunmuş bölüm).
    """
    day = (day or "").strip()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COUNT(DISTINCT url), "
            "COUNT(DISTINCT CASE WHEN day = ? THEN url END) FROM reading_log",
            (day,),
        ).fetchone()
    finally:
        conn.close()
    return {"today": row[1] or 0, "total": row[0] or 0}
