"""Kitap listesi + okuma konumu — cihazlar arası paylaşılır (sunucu tarafı).

Daha önce kütüphane tarayıcıda (localStorage) tutuluyordu; bu yüzden PC'de
eklenen kitap telefonda görünmüyordu. Artık sunucuda (chapters.db ile aynı
dosyada) tutulur, böylece tüm cihazlar aynı kütüphaneyi ve son okuma konumunu
paylaşır.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "cache" / "chapters.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS books (
            slug TEXT PRIMARY KEY,
            title TEXT,
            current_url TEXT,
            current_title TEXT,
            chapter_no INTEGER,
            updated_at REAL
        )
        """
    )
    # Aynı kitabın farklı sitelerdeki slug'larını tek kanonik slug'a bağlar
    # (örn. only-i-level-up-wn -> solo-leveling).
    conn.execute(
        "CREATE TABLE IF NOT EXISTS aliases (alias TEXT PRIMARY KEY, canonical TEXT)"
    )
    return conn


def resolve_slug(slug: str) -> str:
    """Bir slug alias ise kanonik karşılığını, değilse kendisini döndürür."""
    if not slug:
        return slug
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT canonical FROM aliases WHERE alias = ?", (slug,)
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else slug


def merge_books(source: str, target: str) -> str:
    """`source` kitabını `target` kitabıyla birleştirir.

    Bölümler ve sözlük target'a taşınır, source kitabı listeden kalkar ve bundan
    sonra source slug'ından gelen her şey target'a yönlenir. Kanonik slug döner.
    """
    source = (source or "").strip()
    target = (target or "").strip()
    if not source or not target or source == target:
        return target or source
    conn = _connect()
    try:
        # Hedef kendisi bir alias'sa kanonik köke in (alias zinciri olmasın).
        row = conn.execute(
            "SELECT canonical FROM aliases WHERE alias = ?", (target,)
        ).fetchone()
        if row:
            target = row[0]
        if target == source:
            return target
        # Bölümleri taşı (url PK olduğu için çakışma olmaz).
        try:
            conn.execute(
                "UPDATE chapters SET book_slug = ? WHERE book_slug = ?", (target, source)
            )
        except sqlite3.OperationalError:
            pass
        # Sözlüğü taşı; hedefteki kullanıcı düzenlemesini bozma (OR IGNORE).
        try:
            conn.execute(
                "INSERT OR IGNORE INTO glossary (book_slug, source, target) "
                "SELECT ?, source, target FROM glossary WHERE book_slug = ?",
                (target, source),
            )
            conn.execute("DELETE FROM glossary WHERE book_slug = ?", (source,))
        except sqlite3.OperationalError:
            pass
        # source'a bağlı eski alias'ları target'a yönlendir, sonra source->target ekle.
        conn.execute(
            "UPDATE aliases SET canonical = ? WHERE canonical = ?", (target, source)
        )
        conn.execute(
            "INSERT OR REPLACE INTO aliases (alias, canonical) VALUES (?, ?)",
            (source, target),
        )
        conn.execute("DELETE FROM books WHERE slug = ?", (source,))
        conn.commit()
    finally:
        conn.close()
    return target


def upsert_book(
    slug: str,
    title: str,
    current_url: str,
    current_title: str | None,
    chapter_no: int | None,
) -> None:
    """Bir bölüm okununca kitabı + son okuma konumunu güncelle (paylaşılır)."""
    if not slug:
        return
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO books
                (slug, title, current_url, current_title, chapter_no, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (slug, title, current_url, current_title, chapter_no, time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def list_books() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT slug, title, current_url, current_title, chapter_no "
            "FROM books ORDER BY updated_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "slug": r[0],
            "title": r[1],
            "current_url": r[2],
            "current_title": r[3],
            "chapter_no": r[4],
        }
        for r in rows
    ]


def get_book(slug: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT slug, title, current_url, current_title, chapter_no "
            "FROM books WHERE slug = ?",
            (slug,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "slug": row[0],
        "title": row[1],
        "current_url": row[2],
        "current_title": row[3],
        "chapter_no": row[4],
    }


def backfill_from_cache() -> None:
    """Önbellekte olup books tablosunda olmayan kitapları ekle (bir kez, var olanı bozmaz)."""
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO books
                (slug, title, current_url, current_title, chapter_no, updated_at)
            SELECT c.book_slug, c.book_title, c.url, c.title, c.chapter_no, c.created_at
            FROM chapters c
            JOIN (
                SELECT book_slug, MAX(created_at) AS mc
                FROM chapters GROUP BY book_slug
            ) m ON c.book_slug = m.book_slug AND c.created_at = m.mc
            """
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass  # chapters tablosu henüz yoksa (taze kurulum) sorun değil
    finally:
        conn.close()
