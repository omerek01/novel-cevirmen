"""pipeline: önbellek seçimi ve çek-çevir-kaydet yan etkileri."""
from core import cache, glossary, library, pipeline


def _cached(url="u1", source=None):
    cache.save_chapter(url, {
        "book_slug": "roman",
        "book_title": "Example Novel",
        "title": "Chapter 1",
        "chapter_no": 1,
        "translation": "Eski çeviri",
        "source": source,
        "next_url": "u2",
        "prev_url": None,
        "detected_names": ["Alice"],
        "chunk_count": 1,
    })


def _chapter():
    return {
        "book_slug": "roman",
        "book_title": "Example Novel",
        "title": "Chapter 1",
        "chapter_no": 1,
        "text": "Source text",
        "next_url": "u2",
        "prev_url": None,
    }


def _translation():
    return {
        "translation": "Yeni çeviri",
        "source": "Source text",
        "detected_names": ["Alice", "Bob"],
        "chunk_count": 1,
    }


def test_cache_hit_needs_no_key_or_network(monkeypatch):
    _cached()
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url, **kw: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(pipeline, "translate_chapter", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))

    result = pipeline.get_or_translate("u1", None)

    assert result["cached"] is True
    assert result["translation"] == "Eski çeviri"


def test_refresh_bypasses_cache(monkeypatch):
    _cached()
    calls = []
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url, **kw: calls.append(url) or _chapter())
    monkeypatch.setattr(pipeline, "translate_chapter", lambda *a, **k: _translation())

    result = pipeline.get_or_translate("u1", "anahtar", refresh=True)

    assert calls == ["u1"]
    assert result["cached"] is False
    assert result["translation"] == "Yeni çeviri"


def test_want_source_retranslates_old_cached_chapter(monkeypatch):
    _cached(source=None)
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url, **kw: _chapter())
    monkeypatch.setattr(pipeline, "translate_chapter", lambda *a, **k: _translation())

    result = pipeline.get_or_translate("u1", "anahtar", want_source=True)

    assert result["cached"] is False
    assert result["source"] == "Source text"
    assert cache.get_chapter("u1")["source"] == "Source text"


def test_fresh_translate_updates_cache_library_and_glossary(monkeypatch):
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url, **kw: _chapter())
    monkeypatch.setattr(pipeline, "translate_chapter", lambda *a, **k: _translation())

    result = pipeline.get_or_translate("u1", "anahtar")

    assert result["cached"] is False
    assert cache.get_chapter("u1")["translation"] == "Yeni çeviri"
    assert library.get_book("roman")["current_url"] == "u1"
    assert glossary.get_glossary("roman") == {"Alice": "Alice", "Bob": "Bob"}


def test_background_translate_keeps_reading_position(monkeypatch):
    """Toplu iş bölüm hazırlarken 'kaldığın yer' İLERLEMEZ (okuma bozulmaz)."""
    library.upsert_book("roman", "Example Novel", "u1", "Chapter 1", 1)
    ch2 = _chapter() | {"title": "Chapter 2", "chapter_no": 2, "next_url": "u3"}
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url, **kw: ch2)
    monkeypatch.setattr(pipeline, "translate_chapter", lambda *a, **k: _translation())

    result = pipeline.get_or_translate("u2", "anahtar", background=True)

    assert result["cached"] is False
    assert cache.get_chapter("u2")["translation"] == "Yeni çeviri"  # bölüm hazır
    book = library.get_book("roman")
    assert book["current_url"] == "u1"  # okuma konumu yerinde
    assert book["chapter_no"] == 1


def test_background_cache_hit_keeps_reading_position(monkeypatch):
    """Önbellekten dönen toplu bölüm de konumu ilerletmez."""
    library.upsert_book("roman", "Example Novel", "u1", "Chapter 1", 1)
    _cached(url="u5")

    pipeline.get_or_translate("u5", None, background=True)

    assert library.get_book("roman")["current_url"] == "u1"


def test_background_translate_adds_missing_book(monkeypatch):
    """Kitap kütüphanede hiç yoksa toplu iş yine de görünür kılar."""
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url, **kw: _chapter())
    monkeypatch.setattr(pipeline, "translate_chapter", lambda *a, **k: _translation())

    pipeline.get_or_translate("u1", "anahtar", background=True)

    assert library.get_book("roman") is not None


def test_background_fetch_uses_bulk_priority(monkeypatch):
    """background=True çekimi düşük öncelikle (priority='bulk') yapar."""
    seen = {}

    def fake_fetch(url, **kw):
        seen.update(kw)
        return _chapter()

    monkeypatch.setattr(pipeline, "fetch_chapter", fake_fetch)
    monkeypatch.setattr(pipeline, "translate_chapter", lambda *a, **k: _translation())

    pipeline.get_or_translate("u1", "anahtar", background=True)
    assert seen.get("priority") == "bulk"

    seen.clear()
    pipeline.get_or_translate("u1", "anahtar", refresh=True)
    assert seen.get("priority") == "interactive"
