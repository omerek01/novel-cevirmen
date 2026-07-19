"""Sentetik şemalı kitaplar (paste:// — ileride pdf://, manga://).

İçe aktarılan içerik web'den ÇEKİLEMEZ; bölümler önceden `chapters` tablosuna
sahneli satır (translation NULL, raw_source dolu — E-18) olarak yazılır, iş
zinciri next_url ile gezer. Kısıtlar (plan V1): merge'e sokulmaz (E-8), zincir
yalnız sona-ekleme destekler, yalnız SON bölüm silinebilir (E-23).
"""
from __future__ import annotations

import re
import secrets
import time

from . import cache, db

SYNTHETIC_SCHEMES = ("paste://", "pdf://", "manga://")


def is_synthetic_url(url: str) -> bool:
    return bool(url) and url.startswith(SYNTHETIC_SCHEMES)


def is_synthetic_slug(slug: str) -> bool:
    return bool(slug) and slug.startswith(("paste-", "pdf-", "manga-"))


class ImportedChapterMissing(Exception):
    """Sentetik bölümün satırı yok — kaynak geri getirilemez (E-7: 404'e gider)."""


def slugify_title(title: str) -> str:
    """Başlıktan paste- önekli slug (E-13: boş sonuç → paste-<rastgele6>)."""
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    if not s:
        return f"paste-{secrets.token_hex(3)}"
    return f"paste-{s}"


def allocate_slug(title: str) -> str:
    """Çakışmayan slug tahsis et: paste-x, paste-x-2, paste-x-3 …"""
    base = slugify_title(title)
    from . import library
    library._connect().close()  # books şeması garanti (tembel oluşturma)
    conn = db.connect()
    try:
        slug = base
        n = 1
        while conn.execute(
            "SELECT 1 FROM books WHERE slug = ?", (slug,)
        ).fetchone():
            n += 1
            slug = f"{base}-{n}"
        return slug
    finally:
        conn.close()


def chapter_url(slug: str, no: int) -> str:
    return f"paste://{slug}/{no}"


def append_chapter(
    slug: str,
    book_title: str,
    chapter_title: str,
    raw_text: str,
    chapter_no: int | None = None,
) -> dict:
    """Kitabın zincirine sahneli bölüm ekle — TEK transaction (E-23).

    Numara tahsisi (max+1, elle geçersiz kılınabilir) + INSERT (çakışmada hata,
    REPLACE değil) + önceki kuyruk bölümünün next_url bağlaması atomiktir.
    Döner: {"url", "chapter_no", "prev_url"}.
    """
    cache._connect().close()  # chapters şeması + raw_source sütunu garanti
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT url, chapter_no FROM chapters WHERE book_slug = ? "
            "ORDER BY chapter_no DESC LIMIT 1",
            (slug,),
        ).fetchone()
        prev_url, prev_no = (row[0], row[1]) if row else (None, None)
        no = chapter_no if chapter_no is not None else (prev_no or 0) + 1
        url = chapter_url(slug, no)
        conn.execute(
            "INSERT INTO chapters (url, book_slug, book_title, title, chapter_no, "
            "translation, next_url, prev_url, raw_source, created_at) "
            "VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)",
            (url, slug, book_title, chapter_title, no, prev_url, raw_text, time.time()),
        )
        if prev_url:  # önceki kuyruğun next'i yeni bölüme bağlanır (n±1 zinciri)
            conn.execute(
                "UPDATE chapters SET next_url = ? WHERE url = ?", (url, prev_url)
            )
        conn.commit()
        return {"url": url, "chapter_no": no, "prev_url": prev_url}
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def stage_url_chapter(
    slug: str,
    book_title: str,
    chapter_title: str,
    raw_text: str,
    url: str,
    chapter_no: int | None = None,
) -> dict:
    """Belirli bir (genelde http) URL'ye elle yapıştırılan bölümü sahnele.

    "Takılan bölüm doldurma": bir web kitabında Cloudflare/52x ile çekilemeyen
    bölümün İngilizce metnini o gerçek URL'nin altına sahneli satır (translation
    NULL, raw_source dolu) yazar; kitap web-yerli kalır (`paste://` üretmez).
    Pipeline raw_source-öncelikli routing ile web'e inmeden bundan çevirir.

    Bağlama: URL'yi zaten `next_url`'ünde gösteren bir bölüm varsa (engellenen
    bölümün öncesi) prev ona bağlanır; yoksa kitabın kuyruğuna eklenir ve kuyruğun
    `next_url`'ü bu URL'ye bağlanır. Var olan satır varsa raw_source/başlık
    güncellenir (yeniden doldurma) ve translation NULL'lanır → yeniden çevrilir.
    Döner: {"url", "chapter_no"}.
    """
    cache._connect().close()  # chapters şeması + raw_source sütunu garanti
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT chapter_no FROM chapters WHERE url = ?", (url,)
        ).fetchone()
        if existing is not None:
            conn.execute(
                "UPDATE chapters SET book_slug = ?, book_title = ?, title = ?, "
                "raw_source = ?, translation = NULL WHERE url = ?",
                (slug, book_title, chapter_title, raw_text, url),
            )
            conn.commit()
            return {"url": url, "chapter_no": existing[0]}
        # URL'yi next'inde gösteren bölüm (engellenenin öncesi) → prev o.
        pointer = conn.execute(
            "SELECT url, chapter_no FROM chapters WHERE book_slug = ? AND next_url = ? "
            "ORDER BY chapter_no DESC LIMIT 1",
            (slug, url),
        ).fetchone()
        if pointer is not None:
            prev_url, prev_no, link_forward = pointer[0], pointer[1], False
        else:  # kimse göstermiyor → kuyruğa ekle, kuyruğun next'ini bu URL'ye bağla
            tail = conn.execute(
                "SELECT url, chapter_no FROM chapters WHERE book_slug = ? "
                "ORDER BY chapter_no DESC LIMIT 1",
                (slug,),
            ).fetchone()
            prev_url, prev_no, link_forward = (
                (tail[0], tail[1], True) if tail else (None, None, False)
            )
        no = chapter_no if chapter_no is not None else (prev_no or 0) + 1
        conn.execute(
            "INSERT INTO chapters (url, book_slug, book_title, title, chapter_no, "
            "translation, next_url, prev_url, raw_source, created_at) "
            "VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)",
            (url, slug, book_title, chapter_title, no, prev_url, raw_text, time.time()),
        )
        if link_forward and prev_url:
            conn.execute(
                "UPDATE chapters SET next_url = ? WHERE url = ?", (url, prev_url)
            )
        conn.commit()
        return {"url": url, "chapter_no": no}
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_last_chapter(slug: str, url: str) -> bool:
    """Yalnız zincirin SON bölümü silinebilir; önceki bölümün next_url'ü NULL'lanır."""
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT url, prev_url, next_url FROM chapters WHERE url = ?", (url,)
        ).fetchone()
        if row is None or row[2] is not None:  # son bölüm değil → reddet
            conn.rollback()
            return False
        conn.execute("DELETE FROM chapters WHERE url = ?", (url,))
        if row[1]:
            conn.execute(
                "UPDATE chapters SET next_url = NULL WHERE url = ?", (row[1],)
            )
        conn.commit()
        return True
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
