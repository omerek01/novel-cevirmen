"""reading_log: günlük tekilleştirme + tek sorgu istatistik + kitap durumu (E-16)."""
from core import library, reading_log


def test_log_read_dedup_same_day():
    """Aynı gün aynı bölüm ikinci kez sayılmaz (UNIQUE + INSERT OR IGNORE)."""
    assert reading_log.log_read("2026-07-18", "s", "u1") is True
    assert reading_log.log_read("2026-07-18", "s", "u1") is False  # no-op
    assert reading_log.stats("2026-07-18") == {"today": 1, "total": 1}


def test_stats_today_vs_total_unique_chapters():
    """total = benzersiz okunmuş bölüm (D-B11v2): iki gün okunan bölüm 1 sayılır."""
    reading_log.log_read("2026-07-17", "s", "u1")
    reading_log.log_read("2026-07-18", "s", "u1")  # aynı bölüm, yeni gün
    reading_log.log_read("2026-07-18", "s", "u2")
    assert reading_log.stats("2026-07-18") == {"today": 2, "total": 2}
    assert reading_log.stats("2026-07-17") == {"today": 1, "total": 2}
    # Hiç okunmamış gün: bugün 0, toplam değişmez.
    assert reading_log.stats("2026-07-16") == {"today": 0, "total": 2}


def test_log_read_rejects_invalid_input():
    assert reading_log.log_read("bugün", "s", "u1") is False  # gün formatı değil
    assert reading_log.log_read("2026-07-18", "", "u1") is False
    assert reading_log.log_read("2026-07-18", "s", "") is False
    assert reading_log.stats("2026-07-18") == {"today": 0, "total": 0}


def test_book_status_roundtrip_and_validation():
    library.upsert_book("s", "K", "u1", "B1", 1)
    assert library.get_book("s")["status"] == "okunuyor"  # NULL varsayılanı
    assert library.set_status("s", "bitti") is True
    assert library.get_book("s")["status"] == "bitti"
    assert library.list_books()[0]["status"] == "bitti"
    assert library.set_status("s", "rafta") is False  # geçersiz durum yazılmaz
    assert library.get_book("s")["status"] == "bitti"
    assert library.set_status("yok", "bitti") is False  # bilinmeyen kitap


def test_upsert_preserves_status_e16():
    """E-16 (kritik): konum upsert'i status'u sıfırlamamalı.

    Eski INSERT OR REPLACE satırı silip yeniden yazdığı için adı geçmeyen
    sütunlar (status, ileride has_new/auto_translate) NULL'a dönerdi."""
    library.upsert_book("s", "K", "u1", "B1", 1)
    library.set_status("s", "beklemede")
    library.upsert_book("s", "K", "u2", "B2", 2)  # okuyucu ilerledi
    book = library.get_book("s")
    assert book["status"] == "beklemede"  # KORUNDU
    assert book["current_url"] == "u2"  # konum yine de güncellendi
    # update_position=False yolu da (INSERT OR IGNORE) dokunmaz.
    library.upsert_book("s", "K", "u9", "B9", 9, update_position=False)
    assert library.get_book("s")["status"] == "beklemede"
