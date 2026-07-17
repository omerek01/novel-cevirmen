"""Bölüm çekme + çeviri + önbellek boru hattı.

Hem HTTP endpoint (server.get_chapter) hem arka plan toplu-çeviri işi (jobs)
aynı mantığı kullanır (DRY). FetchError/TranslateError yukarı sızar; çağıran
(endpoint HTTP koduna, iş ise hata mesajına) çevirir.
"""
from __future__ import annotations

from . import cache, glossary, library
from .fetch import fetch_chapter
from .translate import TranslateError, translate_chapter


def _finalize_cached(cached: dict, url: str, background: bool = False) -> dict:
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
        update_position=not background,
    )
    return cached


def get_or_translate(
    url: str,
    api_key: str | None,
    refresh: bool = False,
    want_source: bool = False,
    background: bool = False,
) -> dict:
    """Bölümü önbellekten döndür ya da çek+çevir+önbelleğe yaz.

    refresh=True önbelleği yok sayar. Önbellek isabetinde API anahtarı gerekmez.
    want_source=True ve önbellekteki bölümde hizalı İngilizce kaynak yoksa (eski
    bölüm) ve anahtar varsa, bölüm bir kez yeniden çevrilip kaynak eklenir (iki-dilli
    okuma için). FetchError / TranslateError fırlatabilir.

    background=True toplu çeviri işinden gelen çağrıları işaretler: çekim düşük
    öncelikle yapılır (okuyucu isteği kapıda öne geçer) ve kitabın "kaldığın yer"
    konumu İLERLETİLMEZ — arka planda hazırlanan bölüm okunmuş sayılmaz.
    """
    if not refresh:
        cached = cache.get_chapter(url)
        if cached is not None:
            # Eski bölümü iki-dilli için yükselt: yalnız kaynak istendiğinde, yoksa ve
            # anahtar varsa yeniden çevir; aksi halde önbelleği aynen döndür (hızlı).
            if not (want_source and not cached.get("source") and api_key):
                return _finalize_cached(cached, url, background=background)

    if not api_key:
        raise TranslateError("GEMINI_API_KEY ayarlı değil.")

    # FetchError sızabilir. Toplu iş düşük öncelikli: okuyucu kapıda öne geçer.
    chapter = fetch_chapter(url, priority="bulk" if background else "interactive")

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
        "source": result.get("source"),
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
        update_position=not background,
    )
    return payload
