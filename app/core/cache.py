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
    conn = db.connect()
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
    # raw_source (E-18): içe aktarımın DEĞİŞMEZ ham kaynağı. source_text hizalı
    # iki-dilli metindir ve hizalama tutmayınca bilerek NULL olur — ikisi
    # birbirinin yerine geçemez. Sentetik refresh/¶-yeniden-çevir buradan okur.
    db.ensure_column(conn, "chapters", "raw_source", "raw_source TEXT")
    # content_type (E-10): NULL/"text" = düz metin bölüm (web/paste). "html" = görsel
    # içerik (PDF çevrilmiş sayfa <img> / EPUB yerinde-çevrili HTML) — okuyucu
    # translation'ı paragraf yerine innerHTML olarak render eder; iki-dilli/¶-yeniden-
    # çevir/arama devre dışı.
    db.ensure_column(conn, "chapters", "content_type", "content_type TEXT")
    # KÜNYE (okuyucudaki rozet): bu bölümü hangi motor çevirdi ve o çeviride sözlüğe
    # hangi terimler EKLENDİ. Sözlüğe otomatik ekleme sessiz çalışıyor ve hatalı bir
    # karşılığı kalıcılaştırabiliyor (gerçek bulgu: kaynak sitenin yazım hatası
    # "Ore Empire" sözlüğe "Maden İmparatorluğu" diye girmişti — doğrusu ork ırkı,
    # "Ork İmparatorluğu"); görünür olması gerekiyor. Cache'te saklanır, yoksa ikinci açılışta
    # (önbellek isabeti) künyesini kaybederdi.
    db.ensure_column(conn, "chapters", "engine", "engine TEXT")
    db.ensure_column(conn, "chapters", "added_terms", "added_terms TEXT")  # JSON eşleme
    # Motorun İÇİNDEKİ model: `engine` yalnız "gemini" der, oysa zincirin hangi halkası
    # çevirdi (3.7 mi flash-lite mı) kalite sorularının cevabı orada. Bu bilgi daha önce
    # yalnız çalışma zamanında vardı ve kayboluyordu → "bunu hangi model çevirdi"
    # tahminle cevaplanıyordu. Eski satırlarda NULL; rozet yalnız motoru gösterir.
    db.ensure_column(conn, "chapters", "model", "model TEXT")
    return conn


def get_chapter(url: str) -> dict | None:
    """Önbellekte varsa ÇEVRİLMİŞ bölümü döndürür (cached=True), yoksa None.

    E-17: sahneli satırlar (translation IS NULL — içe aktarım işi henüz
    çevirmedi) okuma yolunda cache MISS sayılır; yalnız iş yolu onları gezer
    (get_staged). Aksi halde okuyucu boş bölüm alırdı."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT book_slug, book_title, title, chapter_no, translation, "
            "next_url, detected_names, chunk_count, prev_url, source_text, content_type, "
            "engine, added_terms, model "
            "FROM chapters WHERE url = ? AND translation IS NOT NULL",
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
        "content_type": row[10] or "text",
        # Künye: eski satırlarda NULL (sütun sonradan eklendi) → okuyucu rozeti çizmez.
        "engine": row[11],
        "added_terms": json.loads(row[12] or "{}"),
        "model": row[13],
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


def prev_translation(
    book_slug: str, prev_url: str | None, chapter_no: int | None
) -> str:
    """Bir önceki bölümün Türkçe metni — yeni bölümün çeviri bağlamı için.

    Önce `prev_url` denenir (zincir doğrudan bağlıysa kesin sonuç); yoksa aynı
    kitapta bu bölümden KÜÇÜK en büyük numaralı bölüme düşülür (elle eklenen ya da
    zinciri kopuk bölümlerde de bağlam bulunsun). Görsel bölümler (`content_type`
    "html") atlanır: içlerinde çeviri bağlamı olarak kullanılabilecek düz metin yok.
    Bulunamazsa boş string.
    """
    if prev_url:
        row = get_chapter(prev_url)
        if row and row.get("content_type") != "html" and (row.get("translation") or "").strip():
            return row["translation"]
    if not book_slug or chapter_no is None:
        return ""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT translation FROM chapters WHERE book_slug = ? AND chapter_no < ? "
            "AND translation IS NOT NULL AND IFNULL(content_type, 'text') != 'html' "
            "ORDER BY chapter_no DESC LIMIT 1",
            (book_slug, chapter_no),
        ).fetchone()
    finally:
        conn.close()
    return (row[0] or "") if row else ""


def delete_chapter(url: str) -> bool:
    """Bölümü önbellekten sil (listeden kalkar). Kayıt silindiyse True döner."""
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM chapters WHERE url = ?", (url,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def update_nav(url: str, next_url: str | None, prev_url: str | None) -> bool:
    """Cache satırının YALNIZ gezinme alanlarını güncelle (E-3, refresh_metadata).

    translation/source'a dokunmaz — gece kontrolü çeviri yakmadan ve ¶-yamalarını
    ezmeden yeni bölüm bağlantısını işleyebilsin. Satır yoksa False."""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE chapters SET next_url = ?, prev_url = ? WHERE url = ?",
            (next_url, prev_url, url),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def tail_chapter(book_slug: str) -> dict | None:
    """Kitabın en yüksek numaralı (kuyruk) bölümü — zincire sona ekleme için."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT url, chapter_no FROM chapters WHERE book_slug = ? "
            "ORDER BY chapter_no IS NULL, chapter_no DESC LIMIT 1",
            (book_slug,),
        ).fetchone()
    finally:
        conn.close()
    return {"url": row[0], "chapter_no": row[1]} if row else None


def set_next(url: str, next_url: str | None) -> bool:
    """Yalnız bir satırın next_url'ünü güncelle (prev_url'e DOKUNMAZ). Satır yoksa False."""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE chapters SET next_url = ? WHERE url = ?", (next_url, url)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_staged(url: str) -> dict | None:
    """Satırı çeviri durumundan bağımsız döndür (İŞ YOLU — okuma yolu değil).

    İçe aktarım işi sahneli (translation NULL) satırları bununla gezer;
    raw_source (E-18) ham kaynağı taşır."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT book_slug, book_title, title, chapter_no, translation, "
            "next_url, prev_url, raw_source, content_type FROM chapters WHERE url = ?",
            (url,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "book_slug": row[0], "book_title": row[1], "title": row[2],
        "chapter_no": row[3], "translation": row[4], "next_url": row[5],
        "prev_url": row[6], "raw_source": row[7], "content_type": row[8] or "text",
    }


def save_chapter(url: str, data: dict) -> None:
    """Çevrilen bölümü önbelleğe yaz (varsa üzerine).

    E-16: ON CONFLICT (REPLACE değil) — adı geçmeyen raw_source her çeviri
    yazımında sessizce silinmesin (içe aktarımın ham kaynağı değişmezdir).

    Künye alanları (engine/added_terms/model) COALESCE ile yazılır: bu alanları TAŞIMAYAN
    bir payload (örn. `_render_import_page`) aynı satırı güncellediğinde mevcut künye
    NULL'a düşmesin. Aynı E-16 sınıfı hata, farklı sütunlar."""
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO chapters
                (url, book_slug, book_title, title, chapter_no,
                 translation, next_url, detected_names, chunk_count, created_at,
                 prev_url, source_text, content_type, engine, added_terms, model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                book_slug = excluded.book_slug, book_title = excluded.book_title,
                title = excluded.title, chapter_no = excluded.chapter_no,
                translation = excluded.translation, next_url = excluded.next_url,
                detected_names = excluded.detected_names,
                chunk_count = excluded.chunk_count, created_at = excluded.created_at,
                prev_url = excluded.prev_url, source_text = excluded.source_text,
                content_type = excluded.content_type,
                engine = COALESCE(excluded.engine, engine),
                added_terms = COALESCE(excluded.added_terms, added_terms),
                model = COALESCE(excluded.model, model)
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
                data.get("content_type"),
                data.get("engine"),
                # None bırakılır (boş dict DEĞİL): COALESCE'in eski künyeyi koruyabilmesi
                # için "bilgi yok" ile "bu bölümde hiçbir şey eklenmedi" ayrışmalı.
                json.dumps(data["added_terms"], ensure_ascii=False)
                if data.get("added_terms") is not None
                else None,
                data.get("model"),
            ),
        )
        conn.commit()
    finally:
        conn.close()
