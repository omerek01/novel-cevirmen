"""library: current_ratio migration + okuma konumu (url-çifti tutarlılığı)."""
import sqlite3

from core import db, library


def _make_old_books_db():
    """current_ratio'suz eski books tablosu + bir satır."""
    path = db.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE books (
            slug TEXT PRIMARY KEY, title TEXT, current_url TEXT,
            current_title TEXT, chapter_no INTEGER, updated_at REAL
        )
        """
    )
    conn.execute(
        "INSERT INTO books (slug,title,current_url,current_title,chapter_no,updated_at) "
        "VALUES ('s','K','u1','B1',1,0)"
    )
    conn.commit()
    conn.close()


def test_migration_adds_current_ratio():
    _make_old_books_db()
    library._connect().close()
    library._connect().close()  # idempotent
    book = library.get_book("s")
    assert book["current_ratio"] == 0.0  # eski NULL → 0


def test_position_roundtrip():
    library.upsert_book("s", "K", "u1", "B1", 1)
    library.set_position("s", "u1", 0.42)
    assert abs(library.get_book("s")["current_ratio"] - 0.42) < 1e-9


def test_position_clamped():
    library.upsert_book("s", "K", "u1", "B1", 1)
    library.set_position("s", "u1", 5.0)
    assert library.get_book("s")["current_ratio"] == 1.0
    library.set_position("s", "u1", -3.0)
    assert library.get_book("s")["current_ratio"] == 0.0


def test_upsert_resets_ratio_on_url_change():
    library.upsert_book("s", "K", "u1", "B1", 1)
    library.set_position("s", "u1", 0.6)
    library.upsert_book("s", "K", "u2", "B2", 2)  # yeni bölüm
    assert library.get_book("s")["current_ratio"] == 0.0


def test_upsert_preserves_ratio_on_same_url():
    library.upsert_book("s", "K", "u1", "B1", 1)
    library.set_position("s", "u1", 0.6)
    library.upsert_book("s", "K", "u1", "B1", 1)  # aynı bölüm (resume)
    assert abs(library.get_book("s")["current_ratio"] - 0.6) < 1e-9


def test_list_books_includes_ratio():
    library.upsert_book("s", "K", "u1", "B1", 1)
    library.set_position("s", "u1", 0.3)
    books = library.list_books()
    assert books[0]["current_ratio"] == 0.3


def test_set_position_unknown_book_noop():
    library.set_position("yok", "u1", 0.5)  # patlamamalı
    assert library.get_book("yok") is None


def test_upsert_without_position_keeps_existing_row():
    """update_position=False (toplu iş): mevcut kitabın konumuna dokunmaz."""
    library.upsert_book("s", "K", "u1", "B1", 1)
    library.set_position("s", "u1", 0.4)
    library.upsert_book("s", "K", "u9", "B9", 9, update_position=False)
    book = library.get_book("s")
    assert book["current_url"] == "u1"
    assert book["chapter_no"] == 1
    assert abs(book["current_ratio"] - 0.4) < 1e-9


def test_upsert_without_position_still_inserts_missing_book():
    """update_position=False yeni kitabı yine de kütüphaneye ekler (görünürlük)."""
    library.upsert_book("yeni", "K", "u1", "B1", 1, update_position=False)
    assert library.get_book("yeni")["current_url"] == "u1"
