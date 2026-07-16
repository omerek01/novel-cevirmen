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
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(pipeline, "translate_chapter", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))

    result = pipeline.get_or_translate("u1", None)

    assert result["cached"] is True
    assert result["translation"] == "Eski çeviri"


def test_refresh_bypasses_cache(monkeypatch):
    _cached()
    calls = []
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url: calls.append(url) or _chapter())
    monkeypatch.setattr(pipeline, "translate_chapter", lambda *a, **k: _translation())

    result = pipeline.get_or_translate("u1", "anahtar", refresh=True)

    assert calls == ["u1"]
    assert result["cached"] is False
    assert result["translation"] == "Yeni çeviri"


def test_want_source_retranslates_old_cached_chapter(monkeypatch):
    _cached(source=None)
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url: _chapter())
    monkeypatch.setattr(pipeline, "translate_chapter", lambda *a, **k: _translation())

    result = pipeline.get_or_translate("u1", "anahtar", want_source=True)

    assert result["cached"] is False
    assert result["source"] == "Source text"
    assert cache.get_chapter("u1")["source"] == "Source text"


def test_fresh_translate_updates_cache_library_and_glossary(monkeypatch):
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url: _chapter())
    monkeypatch.setattr(pipeline, "translate_chapter", lambda *a, **k: _translation())

    result = pipeline.get_or_translate("u1", "anahtar")

    assert result["cached"] is False
    assert cache.get_chapter("u1")["translation"] == "Yeni çeviri"
    assert library.get_book("roman")["current_url"] == "u1"
    assert glossary.get_glossary("roman") == {"Alice": "Alice", "Bob": "Bob"}
