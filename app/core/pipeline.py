"""Bölüm çekme + çeviri + önbellek boru hattı.

Hem HTTP endpoint (server.get_chapter) hem arka plan toplu-çeviri işi (jobs)
aynı mantığı kullanır (DRY). FetchError/TranslateError yukarı sızar; çağıran
(endpoint HTTP koduna, iş ise hata mesajına) çevirir.
"""
from __future__ import annotations

import threading

from . import budget, cache, glossary, library
from . import fetch as _fetch_mod
from .fetch import fetch_chapter
from .translate import TranslateError, translate_chapter

# ---- URL-başına tek-uçuş (single-flight) — prefetch'in ön koşulu ----
# Aynı URL için ikinci çağrı ilkinin sonucunu bekler; aynı bölüm asla iki kez
# Gemini'ye gitmez. Paylaşılan kısım YALNIZ fetch+translate+cache.save (E-2);
# glossary/upsert yan etkileri her çağıranın kendi bayrağıyla ayrıca koşar.


class _Flight:
    def __init__(self, background: bool) -> None:
        self.event = threading.Event()
        self.result: dict | None = None
        self.exc: BaseException | None = None
        # E-1: uçuş kapıda beklerken interaktif katılımcı gelirse boost edilir.
        self.ticket = _fetch_mod._FETCH_GATE.ticket("bulk" if background else "interactive")


_FLIGHTS: dict[str, _Flight] = {}
_FLIGHTS_LOCK = threading.Lock()


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

    payload = _fetch_translate_save(url, api_key, background)

    # E-2: yan etkiler çağıranın KENDİ bayrağıyla — prefetch uçuşuna katılan
    # okuyucunun "kaldığın yer"i ilerler, salt-prefetch ilerletmez.
    glossary.merge_names(payload["book_slug"], payload["detected_names"])
    library.upsert_book(
        payload["book_slug"], payload["book_title"], url,
        payload["title"], payload["chapter_no"],
        update_position=not background,
    )
    return payload


def _fetch_translate_save(url: str, api_key: str, background: bool) -> dict:
    """Tek-uçuş korumalı paylaşılan iş: çek + çevir + önbelleğe yaz."""
    with _FLIGHTS_LOCK:
        flight = _FLIGHTS.get(url)
        joined = flight is not None
        if not joined:
            flight = _Flight(background)
            _FLIGHTS[url] = flight
    if joined:
        if not background:
            flight.ticket.boost()  # E-1: okuyucu katıldı → kapı önceliği yükselir
        flight.event.wait()
        if flight.exc is not None:
            raise flight.exc
        return dict(flight.result)
    try:
        flight.result = _do_fetch_translate_save(url, api_key, background, flight.ticket)
        return dict(flight.result)
    except BaseException as exc:
        # E-14: uçuş ölürse girdi silinir + hata bekleyenlere yayılır; sonraki
        # çağrı yeniden dener (aksi halde URL restart'a kadar kilitli kalırdı).
        flight.exc = exc
        raise
    finally:
        with _FLIGHTS_LOCK:
            _FLIGHTS.pop(url, None)
        flight.event.set()


def _do_fetch_translate_save(
    url: str, api_key: str, background: bool, ticket
) -> dict:
    # FetchError sızabilir. Toplu iş düşük öncelikli: okuyucu kapıda öne geçer.
    chapter = fetch_chapter(
        url, priority="bulk" if background else "interactive", ticket=ticket
    )

    # Birleştirilmiş kitap: slug'ı kanonikleştir, böylece bölüm/sözlük tek kitapta toplanır.
    book_slug = library.resolve_slug(chapter["book_slug"])
    book_title = chapter["book_title"]
    if book_slug != chapter["book_slug"]:
        merged = library.get_book(book_slug)
        if merged and merged.get("title"):
            book_title = merged["title"]

    book_glossary = glossary.get_glossary(book_slug)
    if background:
        # Karar #13 / E-12: aynı anda en fazla 1 arka plan çevirisi — kapı yalnız
        # çekimi serileştiriyordu; çeviri aşaması da Gemini kotasını korur.
        with budget.BG_TRANSLATE_SEM:
            result = translate_chapter(chapter["text"], api_key=api_key, glossary=book_glossary)
    else:
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
    return payload


def refresh_metadata(url: str) -> dict:
    """Yalnız gezinme bilgisini tazele (E-3) — check-updates bunu kullanır.

    Bölümü bulk öncelikle yeniden çeker ve cache satırının YALNIZ
    next_url/prev_url alanlarını günceller; translation/source'a DOKUNMAZ,
    Gemini'ye gitmez (refresh=True tam çeviri yakar + ¶-yamalarını ezerdi).
    Döner: {"next_url": ..., "prev_url": ...}.
    """
    chapter = fetch_chapter(url, priority="bulk")
    nav = {"next_url": chapter.get("next_url"), "prev_url": chapter.get("prev_url")}
    cache.update_nav(url, nav["next_url"], nav["prev_url"])
    return nav
