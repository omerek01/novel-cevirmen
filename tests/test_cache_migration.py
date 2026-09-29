"""cache: prev_url migration idempotensi + roundtrip + eski NULL satır."""
import sqlite3

from core import cache, db


def _make_old_schema_db():
    """prev_url'süz eski chapters tablosu + bir satır oluştur."""
    path = db.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE chapters (
            url TEXT PRIMARY KEY, book_slug TEXT, book_title TEXT, title TEXT,
            chapter_no INTEGER, translation TEXT, next_url TEXT,
            detected_names TEXT, chunk_count INTEGER, created_at REAL
        )
        """
    )
    conn.execute(
        "INSERT INTO chapters (url, book_slug, book_title, title, chapter_no, "
        "translation, next_url, detected_names, chunk_count, created_at) "
        "VALUES ('uOld','s','K','B1',1,'metin','uNext','[]',1,0)"
    )
    conn.commit()
    conn.close()


def test_migration_adds_prev_url_idempotent():
    _make_old_schema_db()
    cache._connect().close()  # 1. çağrı: ALTER ile prev_url ekler
    cache._connect().close()  # 2. çağrı: patlamamalı (idempotent)
    conn = sqlite3.connect(db.db_path())
    cols = {r[1] for r in conn.execute("PRAGMA table_info(chapters)")}
    conn.close()
    assert "prev_url" in cols


def test_old_row_prev_url_is_none():
    _make_old_schema_db()
    cache._connect().close()  # migration
    row = cache.get_chapter("uOld")
    assert row is not None
    assert row["prev_url"] is None
    assert row["next_url"] == "uNext"


def test_save_get_roundtrips_prev_url():
    cache.save_chapter(
        "u1",
        {
            "book_slug": "s", "book_title": "K", "title": "B1", "chapter_no": 1,
            "translation": "çeviri", "next_url": "u2", "prev_url": "u0",
            "detected_names": ["Kim"], "chunk_count": 2,
        },
    )
    row = cache.get_chapter("u1")
    assert row["prev_url"] == "u0"
    assert row["next_url"] == "u2"
    assert row["detected_names"] == ["Kim"]


def test_fresh_db_has_prev_url():
    # translation şart: çevirisiz satır artık SAHNELİ sayılır ve okuma yolunda
    # görünmez (E-17) — bu test yalnız prev_url roundtrip'ini doğrular.
    cache.save_chapter(
        "u9", {"book_slug": "s", "title": "B", "prev_url": "u8", "translation": "x"}
    )
    assert cache.get_chapter("u9")["prev_url"] == "u8"


def test_migration_adds_source_text_and_old_row_none():
    _make_old_schema_db()  # source_text'siz eski şema
    cache._connect().close()  # migration source_text ekler
    conn = sqlite3.connect(db.db_path())
    cols = {r[1] for r in conn.execute("PRAGMA table_info(chapters)")}
    conn.close()
    assert "source_text" in cols
    assert cache.get_chapter("uOld")["source"] is None  # eski satırda kaynak yok


def test_save_get_roundtrips_source():
    cache.save_chapter(
        "u1",
        {
            "book_slug": "s", "title": "B1", "translation": "çeviri\n\niki",
            "source": "english\n\ntwo", "prev_url": "u0",
        },
    )
    row = cache.get_chapter("u1")
    assert row["source"] == "english\n\ntwo"
    assert row["translation"] == "çeviri\n\niki"


# ---------------------------------------------------------------- arşiv göçü

def _eski_semali_arsiv():
    """`uzunluk_orani` sütunu OLMAYAN `ceviri_arsivi` — sunucudaki hâli taklit eder."""
    path = db.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE ceviri_arsivi (
            id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL,
            translation TEXT NOT NULL, source_text TEXT, engine TEXT, model TEXT,
            glossary_leaks TEXT, ingilizce_kalinti TEXT, sozluk_surumu INTEGER,
            ceviri_zamani REAL, arsiv_zamani REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _bolum(**ek):
    temel = {
        "book_slug": "k", "book_title": "K", "title": "B1", "chapter_no": 1,
        "source": "kaynak", "uzunluk_orani": 0.9,
    }
    temel.update(ek)
    return temel


def test_arsiv_tablosu_da_goc_alir():
    """`CREATE TABLE IF NOT EXISTS` VAR OLAN tabloya sütun EKLEMEZ.

    Ölçülen vaka (2026-09-29): `uzunluk_orani` arşiv tablosuna yalnız BİLDİRİMLE
    eklenmişti. Sıfırdan kurulan test DB'sinde çalışıyordu, canlı sunucuda ise
    tablo zaten durduğu için sütun HİÇ oluşmuyordu.

    Arşive künye alanı eklerken İKİSİ de gerekir: bildirim (yeni kurulum) +
    `ensure_column` (mevcut kurulum).
    """
    _eski_semali_arsiv()
    conn = cache._connect()
    try:
        sutunlar = {r[1] for r in conn.execute("PRAGMA table_info(ceviri_arsivi)")}
    finally:
        conn.close()
    assert "uzunluk_orani" in sutunlar


def test_eski_semali_arsivde_YENIDEN_CEVIR_calisir():
    """Asıl tehlike buydu: `_arsivle`, var olan bir bölüm YENİDEN ÇEVRİLİRKEN
    koşar. Göç olmadan "yeniden çevir" düğmesi sunucuda çökerdi — ve kullanıcının
    o gün yapacağı tam olarak buydu (özetlenmiş bölümü yeniden çevirmek)."""
    _eski_semali_arsiv()
    cache.save_chapter("uA", _bolum(translation="ilk çeviri"))
    cache.save_chapter("uA", _bolum(translation="YENİDEN çevrildi"))

    assert cache.get_chapter("uA")["translation"] == "YENİDEN çevrildi"
    arsiv = cache.arsiv_listesi("uA")
    assert len(arsiv) == 1 and arsiv[0]["uzunluk_orani"] == 0.9
