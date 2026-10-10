"""Kaynağa bağlı özet önbelleği ve sınırlı çeviri deney izi; okuyucuya taşınmaz."""
import json
import time

from . import db, ceviri_baglam


def _connect():
    conn = db.connect()
    conn.execute("""CREATE TABLE IF NOT EXISTS bolum_ozetleri (
        url TEXT PRIMARY KEY, book_slug TEXT NOT NULL, chapter_no INTEGER,
        kaynak_hash TEXT NOT NULL, surum INTEGER NOT NULL, veri TEXT NOT NULL,
        zaman REAL NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS ceviri_izleri (
        id TEXT PRIMARY KEY, url TEXT NOT NULL, zaman REAL NOT NULL, veri TEXT NOT NULL)""")
    conn.execute("CREATE INDEX IF NOT EXISTS ceviri_iz_url ON ceviri_izleri(url, zaman)")
    return conn


def ozet_yaz(url: str, book_slug: str, chapter_no: int, source: str, summary: dict):
    if summary.get("kaynak_sha256") != ceviri_baglam.kaynak_hash(source):
        raise ceviri_baglam.AnalizHatasi("Özet başka bir kaynağa ait.")
    ceviri_baglam.dogrula(summary, source)
    with _connect() as conn:
        conn.execute("""INSERT INTO bolum_ozetleri VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET book_slug=excluded.book_slug,
            chapter_no=excluded.chapter_no, kaynak_hash=excluded.kaynak_hash,
            surum=excluded.surum, veri=excluded.veri, zaman=excluded.zaman""",
            (url, book_slug, chapter_no, summary["kaynak_sha256"], ceviri_baglam.SURUM,
             json.dumps(summary, ensure_ascii=False), time.time()))
    conn.close()


def ozet_oku(url: str, book_slug: str, chapter_no: int, source: str) -> dict | None:
    conn = _connect()
    try:
        r = conn.execute("SELECT veri FROM bolum_ozetleri WHERE url=? AND book_slug=? "
                         "AND chapter_no=? AND kaynak_hash=? AND surum=?",
                         (url, book_slug, chapter_no, ceviri_baglam.kaynak_hash(source),
                          ceviri_baglam.SURUM)).fetchone()
    finally:
        conn.close()
    if not r:
        return None
    try:
        summary = json.loads(r[0]); ceviri_baglam.dogrula(summary, source)
        return summary
    except (ValueError, TypeError, ceviri_baglam.AnalizHatasi):
        return None


def iz_kaydet(ident: str, url: str, veri: dict):
    conn = _connect()
    try:
        with conn:
            conn.execute("INSERT INTO ceviri_izleri VALUES (?, ?, ?, ?) "
                         "ON CONFLICT(id) DO UPDATE SET veri=excluded.veri",
                         (ident, url, time.time(), json.dumps(veri, ensure_ascii=False)))
            conn.execute("DELETE FROM ceviri_izleri WHERE url=? AND id NOT IN "
                         "(SELECT id FROM ceviri_izleri WHERE url=? ORDER BY zaman DESC LIMIT 5)",
                         (url, url))
    finally:
        conn.close()


def iz_oku(url: str) -> list[dict]:
    conn = _connect()
    try:
        return [{"id": r[0], "zaman": r[1], "veri": json.loads(r[2])} for r in conn.execute(
            "SELECT id,zaman,veri FROM ceviri_izleri WHERE url=? ORDER BY zaman DESC", (url,))]
    finally:
        conn.close()
