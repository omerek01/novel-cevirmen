"""Bölüm çekme + çeviri + önbellek boru hattı.

Hem HTTP endpoint (server.get_chapter) hem arka plan toplu-çeviri işi (jobs)
aynı mantığı kullanır (DRY). FetchError/TranslateError yukarı sızar; çağıran
(endpoint HTTP koduna, iş ise hata mesajına) çevirir.
"""
from __future__ import annotations

from . import cache, glossary, library
from .fetch import fetch_chapter
from .translate import TranslateError, translate_chapter


def _finalize_cached(cached: dict, url: str) -> dict:
    """Önbellekten gelen bölümü kanonik slug'a hizala, kütüphane/sözlüğü güncelle."""
    canon = library.resolve_slug(cached["book_slug"])
    if canon != cached["book_slug"]:
        cached["book_slug"] = canon
        merged = library.get_book(canon)
        if merged and merged.get("title"):
            cached["book_title"] = merged["title"]
    glossary.merge_names(cached["book_slug"], cached.get("detected_names"))
    library.upsert_book(
        cached["book_slug"], cached["book_title"], url,
        cached["title"], cached["chapter_no"],
    )
    return cached


def get_or_translate(url: str, api_key: str | None, refresh: bool = False) -> dict:
    """Bölümü önbellekten döndür ya da çek+çevir+önbelleğe yaz.

    refresh=True önbelleği yok sayar. Önbellek isabetinde API anahtarı gerekmez.
    FetchError / TranslateError fırlatabilir.
    """
    if not refresh:
        cached = cache.get_chapter(url)
        if cached is not None:
            return _finalize_cached(cached, url)

    if not api_key:
        raise TranslateError("GEMINI_API_KEY ayarlı değil.")

    chapter = fetch_chapter(url)  # FetchError sızabilir

    # Birleştirilmiş kitap: slug'ı kanonikleştir, böylece bölüm/sözlük tek kitapta toplanır.
    book_slug = library.resolve_slug(chapter["book_slug"])
    book_title = chapter["book_title"]
    if book_slug != chapter["book_slug"]:
        merged = library.get_book(book_slug)
        if merged and merged.get("title"):
            book_title = merged["title"]

    book_glossary = glossary.get_glossary(book_slug)
    result = translate_chapter(chapter["text"], api_key=api_key, glossary=book_glossary)

    payload = {
        "title": chapter["title"],
        "translation": result["translation"],
        "detected_names": result["detected_names"],
        "chunk_count": result["chunk_count"],
        "next_url": chapter["next_url"],
        "prev_url": chapter.get("prev_url"),
        "book_slug": book_slug,
        "book_title": book_title,
        "chapter_no": chapter["chapter_no"],
        "cached": False,
    }
    cache.save_chapter(url, payload)
    glossary.merge_names(book_slug, result["detected_names"])
    library.upsert_book(
        book_slug, book_title, url, chapter["title"], chapter["chapter_no"],
    )
    return payload
