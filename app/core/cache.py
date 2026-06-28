"""Çevrilen bölümlerin kalıcı önbelleği (SQLite).

Bir bölüm bir kez çevrildikten sonra burada saklanır; tekrar açıldığında
API'ye gidilmeden anında döner. Tarayıcıdan bağımsızdır (PC + telefon paylaşır).
"""
from __future__ import annotations

import json
import sqlite3
import time

from . import db


def _connect() -> sqlite3.Connection:
    path = db.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chapters (
            url TEXT PRIMARY KEY,
            book_slug TEXT,
            book_title TEXT,
            title TEXT,
            chapter_no INTEGER,
            translation TEXT,
            next_url TEXT,
            detected_names TEXT,
            chunk_count INTEGER,
            created_at REAL,
            prev_url TEXT,
            source_text TEXT
        )
        """
    )
    # Eski DB'ler için idempotent migration'lar.
    db.ensure_column(conn, "chapters", "prev_url", "prev_url TEXT")
    # source_text: çeviriyle paragraf-hizalı İngilizce kaynak (iki-dilli okuma).
    db.ensure_column(conn, "chapters", "source_text", "source_text TEXT")
    return conn


def get_chapter(url: str) -> dict | None:
    """Önbellekte varsa bölümü döndürür (cached=True), yoksa None."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT book_slug, book_title, title, chapter_no, translation, "
            "next_url, detected_names, chunk_count, prev_url, source_text "
            "FROM chapters WHERE url = ?",
            (url,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "book_slug": row[0],
        "book_title": row[1],
        "title": row[2],
        "chapter_no": row[3],
        "translation": row[4],
        "next_url": row[5],
        "detected_names": json.loads(row[6] or "[]"),
        "chunk_count": row[7],
        "prev_url": row[8],
        "source": row[9],
        "cached": True,
    }


def list_chapters(book_slug: str) -> list[dict]:
    """Bir kitabın çevrilmiş bölümlerini bölüm numarasına göre sıralı döndürür."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT url, title, chapter_no FROM chapters WHERE book_slug = ? "
            "ORDER BY chapter_no IS NULL, chapter_no",
            (book_slug,),
        ).fetchall()
    finally:
        conn.close()
    return [{"url": r[0], "title": r[1], "chapter_no": r[2]} for r in rows]


def save_chapter(url: str, data: dict) -> None:
    """Çevrilen bölümü önbelleğe yaz (varsa üzerine)."""
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO chapters
                (url, book_slug, book_title, title, chapter_no,
                 translation, next_url, detected_names, chunk_count, created_at,
                 prev_url, source_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                url,
                data.get("book_slug"),
                data.get("book_title"),
                data.get("title"),
                data.get("chapter_no"),
                data.get("translation"),
                data.get("next_url"),
                json.dumps(data.get("detected_names") or [], ensure_ascii=False),
                data.get("chunk_count"),
                time.time(),
                data.get("prev_url"),
                data.get("source"),
            ),
        )
        conn.commit()
    finally:
        conn.close()
