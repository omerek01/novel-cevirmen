"""Bölüm çekme + çeviri + önbellek boru hattı.

Hem HTTP endpoint (server.get_chapter) hem arka plan toplu-çeviri işi (jobs)
aynı mantığı kullanır (DRY). FetchError/TranslateError yukarı sızar; çağıran
(endpoint HTTP koduna, iş ise hata mesajına) çevirir.
"""
from __future__ import annotations

import threading

from . import budget, cache, glossary, library, synthetic
from . import fetch as _fetch_mod
from .fetch import fetch_chapter
from .translate import TranslateError, ayikla_karakter_adlari, translate_chapter

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


def _finalize_cached(cached: dict, url: str, advance_position: bool = True) -> dict:
    """Önbellekten gelen bölümü kanonik slug'a hizala, kütüphane/sözlüğü güncelle."""
    canon = library.resolve_slug(cached["book_slug"])
    if canon != cached["book_slug"]:
        cached["book_slug"] = canon
        merged = library.get_book(canon)
        if merged and merged.get("title"):
            cached["book_title"] = merged["title"]
    # Önbellekteki `detected_names` HAM olabilir (süzgeçten önce yazılmış eski satır):
    # aynı süzgeçten geçmeden merge_names'e verilirse eski bölümü her açışta sözlüğe
    # yeniden İngilizce kayıt çakar. Cache'te `detected_terms` yok → boş eşleme.
    glossary.merge_names(
        cached["book_slug"],
        ayikla_karakter_adlari(
            cached.get("detected_names") or [], {}, cached.get("translation") or ""
        ),
    )
    library.upsert_book(
        cached["book_slug"], cached["book_title"], url,
        cached["title"], cached["chapter_no"],
        update_position=advance_position,
    )
    return cached


def get_or_translate(
    url: str,
    api_key: str | None,
    refresh: bool = False,
    want_source: bool = False,
    background: bool = False,
    advance_position: bool | None = None,
) -> dict:
    """Bölümü önbellekten döndür ya da çek+çevir+önbelleğe yaz.

    refresh=True önbelleği yok sayar (model zinciri her yolda AYNI: kalite öncelikli
    `translate.DEFAULT_MODELS`). Önbellek isabetinde API anahtarı gerekmez.
    want_source=True ve önbellekteki bölümde hizalı İngilizce kaynak yoksa (eski
    bölüm) ve anahtar varsa, bölüm bir kez yeniden çevrilip kaynak eklenir (iki-dilli
    okuma için). FetchError / TranslateError fırlatabilir.

    background=True toplu çeviri işinden gelen çağrıları işaretler: çekim düşük
    öncelikle yapılır (okuyucu isteği kapıda öne geçer).

    advance_position: kitabın "kaldığın yer" konumu bu bölüme ilerlesin mi. None ise
    `not background` (eski davranış). Sonsuz okumada okuyucu, akışa ÖNDEN eklenen
    (henüz okunmamış) bölümleri `advance_position=False` ile çeker — konumu yalnız
    AKTİF (okunan) bölümün position POST'u belirler; aksi halde önden-ekleme konumu
    okunmamış bölüme kaydırıp aktif-POST ile yarışır (gerçek bulgu: current_url 7'de
    takılırken cache'te bölüm 8 oluşuyordu).

    """
    adv = (not background) if advance_position is None else advance_position
    if not refresh:
        cached = cache.get_chapter(url)
        if cached is not None:
            # Eski bölümü iki-dilli için yükselt: yalnız kaynak istendiğinde, yoksa ve
            # anahtar varsa yeniden çevir; aksi halde önbelleği aynen döndür (hızlı).
            if not (want_source and not cached.get("source") and api_key):
                return _finalize_cached(cached, url, advance_position=adv)

    if not api_key:
        raise TranslateError("GEMINI_API_KEY ayarlı değil.")

    # Sözlüğe işleme ARTIK uçuşun içinde (`_do_fetch_translate_save`): eklenen
    # terimler künyenin parçası ve cache'e onunla birlikte yazılıyor. Burada tekrar
    # çağrılsaydı ikinci çağıran hep boş liste görürdü (ilk çağıran zaten eklemiş olur).
    payload = _fetch_translate_save(url, api_key, background)

    # E-2: yan etkiler çağıranın KENDİ bayrağıyla — prefetch uçuşuna katılan
    # okuyucunun "kaldığın yer"i ilerler, salt-prefetch ilerletmez.
    library.upsert_book(
        payload["book_slug"], payload["book_title"], url,
        payload["title"], payload["chapter_no"],
        update_position=adv,
    )
    return payload


def _sozluge_isle(slug: str, veri: dict) -> dict[str, str]:
    """Bölümden algılanan özel adları kitabın sözlüğüne işle.

    Sözlüğe giren şey TÜM özel adlardır, iki davranışla:
      * karakter (`detected_names`) → İngilizce KALIR (`X -> X`); İngilizce kalan
        TEK sınıf budur
      * karakter dışı her özel ad (`detected_terms`: yer, lonca, EŞYA, BECERİ,
        unvan, ırk, adlandırılmış canavar, sistem terimi…) → modelin çeviride
        kullandığı TÜRKÇE karşılıkla sabitlenir

    Amaç tutarlılık: bu adlar sözlükte olmadığı sürece model her bölümde yeniden
    karar veriyordu ve aynı şehir bölümden bölüme başka türlü çıkabiliyordu
    (gerçek bulgu: "Lightshadow City" için uydurma "Işıkölge"). Kullanıcının elle
    yazdığı kayıt her hâlükârda üstündür (`INSERT OR IGNORE`).

    Döner: FİİLEN eklenen terimler (kaynak -> karşılık) — bölüm künyesine yazılır,
    okuyucu rozetinde gösterilir. Otomatik ekleme hatalı bir karşılığı kalıcı
    kılabildiği için görünür olması şart (gerçek bulgu: kaynak sitenin yazım hatası
    "Ore Empire" sözlüğe "Maden İmparatorluğu" diye girmişti; doğrusu "Ork İmparatorluğu").
    """
    # SIRA LOAD-BEARING: önce Türkçe karşılıklar, sonra İngilizce-koru adları. İki
    # kutu aynı adı taşıyabiliyor (model sızdırıyor) ve `merge_*` INSERT OR IGNORE
    # olduğundan İLK yazan kazanır — names önce koşarken "Blackwater Guild -> Blackwater
    # Guild" kaydı, aynı yanıttaki "Blackwater Guild -> Karasu Loncası"nı bastırıyordu.
    eklenen: dict[str, str] = {}
    eklenen.update(glossary.merge_terms(slug, veri.get("detected_terms")))
    eklenen.update(glossary.merge_names(slug, veri.get("detected_names")))
    return eklenen


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
        flight.result = _do_fetch_translate_save(
            url, api_key, background, flight.ticket
        )
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


def _do_fetch_translate_save(url: str, api_key: str, background: bool, ticket) -> dict:
    staged = cache.get_staged(url)
    # GÖRSEL İÇERİK (PDF çevrilmiş sayfa / EPUB yerinde-çevrili HTML): raw_source
    # metin yolundan ÖNCE — bu bölümler paragraf-çeviri değil, sayfa render / HTML üretir.
    if staged is not None and staged.get("content_type") == "html":
        return _render_import_page(url, staged, api_key)
    if staged is not None and staged.get("raw_source"):
        # İçe aktarılmış ham kaynak var → web'e GİTME, raw_source'tan çevir.
        # Şemadan bağımsız (raw_source-öncelikli routing): hem saf `paste://`
        # zinciri hem de bir web (http) URL'sine elle yapıştırılan "takılan bölüm"
        # (site engelli/çevrimdışıyken doldurulan) buradan okunur. Kitap web-yerli
        # kalır; refresh de raw_source'tan yeniden çevirir, fetch'e inmez.
        chapter = {
            "book_slug": staged["book_slug"],
            "book_title": staged["book_title"],
            "title": staged["title"],
            "chapter_no": staged["chapter_no"],
            "text": staged["raw_source"],
            "next_url": staged["next_url"],
            "prev_url": staged["prev_url"],
        }
    elif synthetic.is_synthetic_url(url):
        # E-7/E-11: sentetik URL ama satır/kaynak yok → web'den çekilemez;
        # fetch'e/kapıya İNMEDEN 404.
        raise synthetic.ImportedChapterMissing(
            "İçe aktarılan bölümün kaynağı bulunamadı; yeniden içe aktarın."
        )
    else:
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
    book = library.get_book(book_slug)
    style_note = (book or {}).get("style_note") or ""
    # Bölüm sınırında bağlam sıfırlanmasın: önceki bölümün son Türkçe satırları
    # ilk parçaya bağlam olur (sahne ortasında biten bölümün devamı için).
    prev_context = cache.prev_translation(
        book_slug, chapter.get("prev_url"), chapter.get("chapter_no")
    )
    # Model zinciri TEK ve kalite öncelikli (`translate.DEFAULT_MODELS`): okuma,
    # prefetch, toplu çeviri ve "yeniden çevir" aynı sırayı kullanır. Yola göre ayrı
    # zincir DENENDİ ve kaldırıldı (2026-08-17, kullanıcı kararı) — okumanın gövdesi
    # prefetch'ten geldiği için ucuz zincir pratikte çevirinin ÇOĞUNU belirliyordu.
    if background:
        # Karar #13 / E-12: aynı anda en fazla 1 arka plan çevirisi — kapı yalnız
        # çekimi serileştiriyordu; çeviri aşaması da Gemini kotasını korur.
        with budget.BG_TRANSLATE_SEM:
            result = translate_chapter(
                chapter["text"], api_key=api_key, glossary=book_glossary,
                prev_context=prev_context, style_note=style_note,
            )
    else:
        result = translate_chapter(
            chapter["text"], api_key=api_key, glossary=book_glossary,
            prev_context=prev_context, style_note=style_note,
        )

    # Sözlüğe işleme uçuşun İÇİNDE: eklenen terimler künyenin parçası ve bölümle
    # birlikte cache'e yazılıyor, böylece bölüm ikinci açılışta (önbellek isabeti)
    # künyesini kaybetmiyor.
    eklenen = _sozluge_isle(book_slug, result)

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
        # KÜNYE: hangi motor çevirdi (düşüş olduysa fiilen kullanılan) + bu bölümde
        # sözlüğe eklenenler. Okuyucu bölüm sonundaki rozette gösterir.
        "engine": result.get("engine"),
        # Zincirin FİİLEN çeviren halkası (3.7 mi flash-lite mı). `engine` yalnız
        # "gemini" der; kalite sorularının cevabı bu alanda.
        "model": result.get("model"),
        "added_terms": eklenen,
        "cached": False,
    }
    cache.save_chapter(url, payload)
    return payload


def _render_import_page(url: str, staged: dict, api_key: str) -> dict:
    """Görsel içerik bölümü (content_type="html"): PDF sayfasını çevir+render / EPUB
    HTML'ini yerinde çevir. Sonuç HTML olarak cache'lenir (tekrar açılışta yeniden
    render/çeviri yok). Medya, sahnelenen (pdf-/epub-) slug altında saklanır."""
    from . import import_translate

    if not api_key:
        raise TranslateError("GEMINI_API_KEY ayarlı değil.")
    media_slug = staged["book_slug"]  # source.pdf / resimler bu slug altında
    book_slug = library.resolve_slug(media_slug)
    book = library.get_book(book_slug)
    book_title = (book and book.get("title")) or staged["book_title"]
    if url.startswith("pdf://"):
        html, model = import_translate.translate_pdf_page(
            media_slug, staged["chapter_no"], api_key
        )
    elif url.startswith("epub://"):
        html, model = import_translate.translate_epub_html(
            staged["raw_source"], media_slug, api_key
        )
    elif url.startswith("manga://"):
        from . import manga_engine

        if manga_engine.available():
            # Yerel motor: TÜM bölümü tek çağrıda arka planda çevir (model bir kez →
            # ~8s/sayfa). Sayfa hazır değilse "çevriliyor" → okuyucu poll eder.
            from . import manga_batch

            st = manga_batch.ensure_started(media_slug, api_key)
            raise synthetic.MangaTranslating(st.get("done", 0), st.get("total", 0))
        html, model = import_translate.translate_manga_page(
            media_slug, staged["chapter_no"], api_key
        )
    else:
        raise TranslateError("Bilinmeyen görsel içerik türü.")
    payload = {
        "title": staged["title"],
        "translation": html,
        "source": None,
        "detected_names": [],
        "chunk_count": 1,
        "next_url": staged["next_url"],
        "prev_url": staged["prev_url"],
        "book_slug": book_slug,
        "book_title": book_title,
        "chapter_no": staged["chapter_no"],
        "content_type": "html",
        # KÜNYE: görsel içerik de Gemini ile çevrilir (PDF/EPUB metin blokları,
        # manga balonları) → rozet metin bölümlerindekiyle aynı bilgiyi verir.
        # Sayfada çevrilecek metin yoksa model None → o sayfaya künye yazılmaz
        # ("çevrildi" demek yanlış olurdu).
        "engine": "gemini" if model else None,
        "model": model,
        "cached": False,
    }
    cache.save_chapter(url, payload)
    return payload


def fetch_into_book(
    url: str, target_slug: str, api_key: str | None, chapter_no: int | None = None
) -> dict:
    """Bir web URL'sini BELİRLİ kitaba 'sonraki bölüm' olarak çek+çevir+bağla.

    "Web'den devam" (B): paste ya da web kitabının kuyruğuna, verilen web adresinden
    çekilen bölümü ekler. Sayfanın GERÇEK next_url'ü KORUNUR → sonraki bölümler
    kendiliğinden siteden gelmeye devam eder (asıl amaç). book_slug hedefe ZORLANIR
    (host-türevli slug'a düşmez) — bölüm doğru kitapta toplanır, sentetik zincire de
    bağlanabilir. Konum İLERLETİLMEZ. FetchError / TranslateError sızabilir.
    """
    if not api_key:
        raise TranslateError("GEMINI_API_KEY ayarlı değil.")
    chapter = fetch_chapter(url, priority="interactive")
    # Bölünme fix: bu web serisinin host-türevli slug'ını (örn. renegade-immortal)
    # hedef kitaba alias'la → kullanıcı SONRAKI BÖLÜM ile normal okuyucudan devam
    # ettiğinde de bölümler AYRI kitap açmaz, resolve_slug hedefe çözer.
    host_slug = chapter.get("book_slug")
    if host_slug and host_slug != target_slug:
        library.set_alias(host_slug, target_slug)
    book_glossary = glossary.get_glossary(target_slug)
    tail = cache.tail_chapter(target_slug)
    no = chapter_no if chapter_no is not None else ((tail["chapter_no"] or 0) + 1 if tail else 1)
    prev_url = tail["url"] if tail else None
    book = library.get_book(target_slug)
    result = translate_chapter(
        chapter["text"], api_key=api_key, glossary=book_glossary,
        prev_context=cache.prev_translation(target_slug, prev_url, no),
        style_note=(book or {}).get("style_note") or "",
    )
    book_title = (book and book.get("title")) or chapter["book_title"]
    eklenen = _sozluge_isle(target_slug, result)  # künyeye girecek, kayıttan ÖNCE
    payload = {
        "title": chapter["title"],
        "translation": result["translation"],
        "source": result.get("source"),
        "detected_names": result["detected_names"],
        "chunk_count": result["chunk_count"],
        "next_url": chapter["next_url"],  # sayfanın gerçek next'i → web'den devam eder
        "prev_url": prev_url,
        "book_slug": target_slug,
        "book_title": book_title,
        "chapter_no": no,
        "engine": result.get("engine"),
        # Zincirin FİİLEN çeviren halkası — `_fetch_translate_save` ile AYNI künye.
        # Eksikti: "web'den devam" ile eklenen bölüm modelini kaybediyordu (rozet
        # "GEMINI ile çevrildi" der, hangi halka olduğunu söylemezdi).
        "model": result.get("model"),
        "added_terms": eklenen,
        "cached": False,
    }
    cache.save_chapter(url, payload)
    if prev_url:
        cache.set_next(prev_url, url)  # kuyruğun next'ini yeni bölüme bağla (zincir)
    library.upsert_book(
        target_slug, book_title, url, chapter["title"], no, update_position=False
    )
    return payload


def refresh_metadata(url: str) -> dict:
    """Yalnız gezinme bilgisini tazele (E-3) — check-updates bunu kullanır.

    Bölümü bulk öncelikle yeniden çeker ve cache satırının YALNIZ
    next_url/prev_url alanlarını günceller; translation/source'a DOKUNMAZ,
    Gemini'ye gitmez (refresh=True tam çeviri yakar + ¶-yamalarını ezerdi).
    Döner: {"next_url": ..., "prev_url": ...}.
    """
    if synthetic.is_synthetic_url(url):
        # Sentetik zincirde "kaynakta yeni bölüm var mı" diye bir şey yoktur.
        staged = cache.get_staged(url) or {}
        return {"next_url": staged.get("next_url"), "prev_url": staged.get("prev_url")}
    chapter = fetch_chapter(url, priority="bulk")
    nav = {"next_url": chapter.get("next_url"), "prev_url": chapter.get("prev_url")}
    cache.update_nav(url, nav["next_url"], nav["prev_url"])
    return nav
