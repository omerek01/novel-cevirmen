"""Kitap başına sözlük (glossary) — terim tutarlılığı için kalıcı eşleme.

Eşleme: kaynak (İngilizce terim) -> karşılık (nasıl yazılsın). Karakter isimleri
çeviri sırasında otomatik eklenir; kullanıcı kendi terimlerini ekleyip düzenler.
chapters.db ile aynı dosyada ayrı bir tabloda tutulur.
"""
from __future__ import annotations

import sqlite3

from . import db


def _connect() -> sqlite3.Connection:
    path = db.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS glossary (
            book_slug TEXT,
            source TEXT,
            target TEXT,
            PRIMARY KEY (book_slug, source)
        )
        """
    )
    return conn


def get_glossary(book_slug: str) -> dict[str, str]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT source, target FROM glossary WHERE book_slug = ? "
            "ORDER BY source COLLATE NOCASE",
            (book_slug,),
        ).fetchall()
    finally:
        conn.close()
    return {row[0]: row[1] for row in rows}


def set_term(book_slug: str, source: str, target: str | None) -> None:
    source = (source or "").strip()
    if not source:
        return
    target = (target or "").strip() or source  # boş karşılık = aynen koru
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO glossary (book_slug, source, target) VALUES (?, ?, ?)",
            (book_slug, source, target),
        )
        conn.commit()
    finally:
        conn.close()


def delete_term(book_slug: str, source: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "DELETE FROM glossary WHERE book_slug = ? AND source = ?",
            (book_slug, source),
        )
        conn.commit()
    finally:
        conn.close()


def merge_names(book_slug: str, names: list[str] | None) -> None:
    """Otomatik algılanan karakter isimlerini ekle; mevcut kullanıcı düzenlemesini bozma."""
    if not names:
        return
    rows = [(book_slug, n.strip(), n.strip()) for n in names if n and n.strip()]
    if not rows:
        return
    conn = _connect()
    try:
        conn.executemany(
            "INSERT OR IGNORE INTO glossary (book_slug, source, target) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
