"""library.merge_books: bölüm + sözlük taşıma, alias çözümü, zincir düzleme."""
from core import cache, glossary, library


def _seed_book(slug, url):
    cache.save_chapter(url, {
        "book_slug": slug, "book_title": slug.title(), "title": "B1",
        "chapter_no": 1, "translation": "x", "next_url": None, "prev_url": None,
        "detected_names": [], "chunk_count": 1,
    })
    library.upsert_book(slug, slug.title(), url, "B1", 1)


def test_merge_moves_chapters_and_glossary():
    _seed_book("src", "uSrc")
    _seed_book("dst", "uDst")
    glossary.set_term("src", "Sky", "Gökyüzü")

    canonical = library.merge_books("src", "dst")

    assert canonical == "dst"
    # bölüm dst'ye taşındı
    assert any(c["url"] == "uSrc" for c in cache.list_chapters("dst"))
    # sözlük dst'ye taşındı
    assert glossary.get_glossary("dst").get("Sky") == "Gökyüzü"
    assert glossary.get_glossary("src") == {}
    # src kitabı listeden kalktı
    assert library.get_book("src") is None
    # src slug'ı artık dst'ye çözülüyor
    assert library.resolve_slug("src") == "dst"


def test_merge_preserves_existing_dst_glossary():
    _seed_book("src", "uSrc")
    _seed_book("dst", "uDst")
    glossary.set_term("src", "Name", "KaynakKarşılık")
    glossary.set_term("dst", "Name", "HedefKarşılık")  # dst düzenlemesi korunmalı

    library.merge_books("src", "dst")

    assert glossary.get_glossary("dst")["Name"] == "HedefKarşılık"


def test_merge_into_alias_follows_to_canonical():
    _seed_book("a", "uA")
    _seed_book("b", "uB")
    _seed_book("c", "uC")
    library.merge_books("a", "b")  # a -> b
    # b'yi c'ye birleştir; a artık c'ye çözülmeli (zincir düzlenir)
    library.merge_books("b", "c")
    assert library.resolve_slug("a") == "c"
    assert library.resolve_slug("b") == "c"


def test_merge_noop_on_same_or_empty():
    assert library.merge_books("x", "x") == "x"
    assert library.merge_books("", "y") == "y"
