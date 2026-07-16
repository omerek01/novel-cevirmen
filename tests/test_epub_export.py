"""epub_export: önbellek bölümlerini aralıkla seçip geçerli ePub üretme."""
from io import BytesIO
from zipfile import ZipFile

from core import cache, epub_export, library


def _seed(slug="roman", numbers=(1, 2, 3)):
    for no in numbers:
        url = f"https://örnek/roman/chapter-{no}"
        cache.save_chapter(url, {
            "book_slug": slug,
            "book_title": "Example Novel",
            "title": f"Chapter {no}",
            "chapter_no": no,
            "translation": f"Çeviri metni {no}",
            "next_url": None,
            "prev_url": None,
            "detected_names": [],
            "chunk_count": 1,
        })
        library.upsert_book(slug, "Example Novel", url, f"Chapter {no}", no)


def test_build_epub_returns_zip_and_range_filename():
    _seed()

    filename, data = epub_export.build_epub("roman", start=2, count=2)

    assert filename == "roman-2-3.epub"
    assert data and data.startswith(b"PK")


def test_build_epub_empty_and_no_matching_range():
    assert epub_export.build_epub("yok", start=1, count=5) == ("", b"")
    _seed(numbers=(1, 2))
    assert epub_export.build_epub("roman", start=99, count=5) == ("", b"")


def test_build_epub_filters_selected_chapters():
    _seed(numbers=(1, 2, 3, 4))

    _, data = epub_export.build_epub("roman", start=2, count=2)
    with ZipFile(BytesIO(data)) as archive:
        pages = b"\n".join(
            archive.read(name)
            for name in archive.namelist()
            if name.endswith(".xhtml")
        ).decode("utf-8")

    assert "Çeviri metni 2" in pages
    assert "Çeviri metni 3" in pages
    assert "Çeviri metni 1" not in pages
    assert "Çeviri metni 4" not in pages


def test_build_epub_includes_unnumbered_chapters():
    # chapter_no=None olan bölümler (bazı siteler) — aralık filtresi HEPSİNİ elememeli,
    # yoksa o kitaplar ePub'a hiç paketlenemez (regresyon koruması).
    for i, url in enumerate(("https://örnek/wn/a", "https://örnek/wn/b"), 1):
        cache.save_chapter(url, {
            "book_slug": "wn",
            "book_title": "WN",
            "title": f"Bölüm {i}",
            "chapter_no": None,
            "translation": f"Metin {i}",
            "next_url": None,
            "prev_url": None,
            "detected_names": [],
            "chunk_count": 1,
        })
        library.upsert_book("wn", "WN", url, f"Bölüm {i}", None)

    filename, data = epub_export.build_epub("wn", start=1, count=10)

    assert data and data.startswith(b"PK")
