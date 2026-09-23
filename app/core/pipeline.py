"""Bölüm çekme + çeviri + önbellek boru hattı.

Hem HTTP endpoint (server.get_chapter) hem arka plan toplu-çeviri işi (jobs)
aynı mantığı kullanır (DRY). FetchError/TranslateError yukarı sızar; çağıran
(endpoint HTTP koduna, iş ise hata mesajına) çevirir.
"""
from __future__ import annotations

import threading

from . import api_durum, budget, cache, glossary, library, synthetic
from . import fetch as _fetch_mod
from . import translate as _translate_mod
# `_chapter_no`: URL'den bölüm numarası. TEK tanım fetch.py'de — ikinci bir
# regex yazmak, iki yerin zamanla ayrışması demek olurdu.
from .fetch import _chapter_no as _url_bolum_no
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
    # `source` (İngilizce kaynak metin) süzgecin 4. elemesini besler; eski satırlarda
    # NULL olabilir ve o durumda eleme KOŞMAZ — doğrulanamayan kayıt atılmaz.
    glossary.merge_names(
        cached["book_slug"],
        ayikla_karakter_adlari(
            cached.get("detected_names") or [],
            {},
            cached.get("translation") or "",
            cached.get("source") or "",
        ),
        "auto",
        cached.get("chapter_no"),
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
    refetch: bool = False,
) -> dict:
    """Bölümü önbellekten döndür ya da çek+çevir+önbelleğe yaz.

    refresh=True önbelleği yok sayar (model zinciri her yolda AYNI: kalite öncelikli
    `translate.DEFAULT_MODELS`). Önbellek isabetinde API anahtarı gerekmez.
    want_source=True ve önbellekteki bölümde hizalı İngilizce kaynak yoksa (eski
    bölüm) ve anahtar varsa, bölüm bir kez yeniden çevrilip kaynak eklenir (iki-dilli
    okuma için). FetchError / TranslateError fırlatabilir.

    background=True toplu çeviri işinden gelen çağrıları işaretler: çekim düşük
    öncelikle yapılır (okuyucu isteği kapıda öne geçer).

    refetch=True bölümü SİTEDEN yeniden indirmeye zorlar. Varsayılan False:
    önbellekte hizalı İngilizce kaynak varsa "yeniden çevir" web'e HİÇ gitmez
    (bkz. `_onbellek_kaynagi`). refetch, kaynağın KENDİSİ bozuk geldiğinde
    ("Bölüm Boş" kartı) gerekir.

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
                sonuc = _finalize_cached(cached, url, advance_position=adv)
                sonuc["kosullu_denetlenmeyen"] = kosullu_denetlenmeyen(
                    sonuc["book_slug"], sonuc.get("source")
                )
                return sonuc

    if not _translate_mod.ceviri_anahtari_var_mi(api_key):
        raise TranslateError(_translate_mod.ANAHTAR_YOK_MESAJI)

    # Sözlüğe işleme ARTIK uçuşun içinde (`_do_fetch_translate_save`): eklenen
    # terimler künyenin parçası ve cache'e onunla birlikte yazılıyor. Burada tekrar
    # çağrılsaydı ikinci çağıran hep boş liste görürdü (ilk çağıran zaten eklemiş olur).
    payload = _fetch_translate_save(url, api_key, background, refetch)

    # E-2: yan etkiler çağıranın KENDİ bayrağıyla — prefetch uçuşuna katılan
    # okuyucunun "kaldığın yer"i ilerler, salt-prefetch ilerletmez.
    library.upsert_book(
        payload["book_slug"], payload["book_title"], url,
        payload["title"], payload["chapter_no"],
        update_position=adv,
    )
    payload["kosullu_denetlenmeyen"] = kosullu_denetlenmeyen(
        payload["book_slug"], payload.get("source")
    )
    return payload


def kosullu_denetlenmeyen(book_slug: str | None, kaynak: str | None) -> list[str]:
    """Bu bölümde geçen KOŞULLU sözlük kayıtları (otomatik denetim dışı kalanlar).

    Koşullu kayıt uyum denetiminden ve otomatik onarımdan BİLİNÇLİ olarak çıkarılır
    (`translate._denetlenebilir_terimler`): koşulun sağlanıp sağlanmadığı
    deterministik olarak ölçülemez. Okuyucu künyesi bu yüzden "sözlüğe uyuldu"
    DİYEMEZ; "bağlam nedeniyle otomatik denetlenmedi" der. Bilgi okuma anında
    hesaplanır, saklanmaz: künyeye yeni bir sütun eklemek dört üretim noktasına
    yayılırdı, oysa bu bir ölçüm değil bugünkü sözlüğün bir özelliği.
    """
    if not book_slug or not (kaynak or "").strip():
        return []
    kosullar = glossary.ceviri_kosullari(book_slug)
    if not kosullar:
        return []
    sozluk = glossary.ceviri_sozlugu(book_slug)
    tekili = _translate_mod._tekili_kayitli_cogullar(sozluk)
    return sorted(
        s for s in kosullar
        if _translate_mod._terim_metinde(s, sozluk.get(s, s), kaynak, tekili)
    )



def _sozluge_isle(
    slug: str, veri: dict, chapter_no: int | None = None
) -> dict[str, str]:
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

    `chapter_no` köken sütununa (`glossary.first_chapter`) yazılır: yanlış bir
    otomatik karşılık görüldüğünde hangi bölümden geldiği izlenebilsin.

    Döner: FİİLEN eklenen terimler (kaynak -> karşılık) — bölüm künyesine yazılır,
    okuyucu rozetinde gösterilir. Otomatik ekleme hatalı bir karşılığı kalıcı
    kılabildiği için görünür olması şart (gerçek bulgu: kaynak sitenin yazım hatası
    "Ore Empire" sözlüğe "Maden İmparatorluğu" diye girmişti; doğrusu "Ork İmparatorluğu").
    """
    # SIRA LOAD-BEARING: önce Türkçe karşılıklar, sonra İngilizce-koru adları. İki
    # kutu aynı adı taşıyabiliyor (model sızdırıyor) ve `merge_*` INSERT OR IGNORE
    # olduğundan İLK yazan kazanır — names önce koşarken "Blackwater Guild -> Blackwater
    # Guild" kaydı, aynı yanıttaki "Blackwater Guild -> Karasu Loncası"nı bastırıyordu.
    # KÖKEN CÜMLESİ: kaydın çıktığı cümle, TÜRKÇE çeviriden aranır — kullanıcı
    # sözlüğü Türkçe okurken denetliyor ve karşılığın cümle içinde nasıl durduğunu
    # görmek istiyor. Karakter adları İngilizce kaldığı için onlar da bu metinde
    # aynen geçer. Arama `_term_regex` ölçütüyle yapılır (yazım varyantına
    # toleranslı), yani sözlüğün her yerinde kullanılan AYNI kural.
    metin = veri.get("translation") or ""
    terimler = veri.get("detected_terms") or {}
    adlar = veri.get("detected_names") or []
    cumleler: dict[str, str] = {}
    for kaynak, karsilik in terimler.items():
        c = _translate_mod.cumle_bul(metin, karsilik or kaynak)
        if c:
            cumleler[kaynak] = c
    for ad in adlar:
        c = _translate_mod.cumle_bul(metin, ad)
        if c:
            cumleler.setdefault(ad, c)

    eklenen: dict[str, str] = {}
    eklenen.update(
        glossary.merge_terms(
            slug, veri.get("detected_terms"), "auto", chapter_no, cumleler
        )
    )
    eklenen.update(
        glossary.merge_names(
            slug, veri.get("detected_names"), "auto", chapter_no, cumleler
        )
    )
    return eklenen


def _uyum_denetimi(veri: dict) -> dict[str, str]:
    """Çeviri, prompt'ta KURAL olarak verilen sözlüğe fiilen uydu mu?

    Ölçülen sebep (2026-08-30, Shadow Slave'in önbellekteki 110 bölümü): zincirin
    halkaları sözlük kuralına eşit uymuyor — 3.6-flash 60 bölümde 5 ihlal,
    flash-lite 4 bölümde 36. Zincir yalnız ERİŞİLEBİLİRLİĞE bakarak iniyor
    (kota dolunca bir alt halka) ve kaliteyi hiçbir yerde ölçmüyordu; lite'ın
    çevirisi sessizce kalıcı önbelleğe yazılıp bir daha kontrol edilmiyordu.

    Denetim `_sozluge_isle`'den SONRA çağrılsa da ölçüt bilerek `book_glossary`,
    yani bölüm çevrilirken prompt'ta DURAN sözlüktür — bu bölümde yeni algılanan
    terimlerin karşılığını model kendi seçti, ona uymadı diye suçlamak dairesel
    olurdu. Model yalnız kendisine KURAL olarak verilen karşılıktan sorumludur.

    Ölçüm BURADA YAPILMAZ, `translate_chapter`'dan alınır. İkinci bir kopya
    yazmak bu projede defalarca ayrışma üretti (künye alanları, motor adı) ve
    burada somut bir arızası var: pipeline `kosullar`ı görmüyor, yani KOŞULLU
    bir kayıt (`Saint -> Aziz [KOŞUL: rütbe anlamında]`) burada sahte ihlal
    sayılır — üstelik çeviri yolu onu onarımdan geçirip temiz ilan etmişken.

    Bayrak artık çeviri yolunda OTOMATİK onarımdan (tek tur, yalnız bozuk
    paragraflar) SONRA ölçülür; buraya ulaşan değer "onarıma rağmen kalan"dır.
    """
    return veri.get("glossary_leaks") or {}


def _fetch_translate_save(
    url: str, api_key: str, background: bool, refetch: bool = False
) -> dict:
    """Tek-uçuş korumalı paylaşılan iş: çek + çevir + önbelleğe yaz.

    `refetch` uçuşa KATILANLARA değil, uçuşu AÇANA göre uygulanır — `background`
    ile aynı kural. İki çağıran aynı URL için farklı bayrakla gelirse ilkinin
    davranışı geçerlidir; ikinci bir uçuş açmak aynı bölümü iki kez çevirirdi.
    """
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
        # URL bağlama burada girer: çeviriyi FİİLEN yapan uçuşu açandır, katılanlar
        # istek atmaz. Amaç (okuma/prefetch/toplu) giriş noktasından gelir.
        with api_durum.baglam(url=url):
            flight.result = _do_fetch_translate_save(
                url, api_key, background, flight.ticket, refetch
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


def _onbellek_kaynagi(url: str) -> dict | None:
    """Önbellekte hizalı İngilizce kaynak varsa ondan çevrilebilir bir bölüm kur.

    "Yeniden çevir" (`refresh=True`) eskiden önbelleği atlayınca doğrudan siteye
    iniyordu: Playwright + Cloudflare, deneme başına 60 sn zaman aşımı, üstüne
    kendi geri-çekilmeli tekrarı ve tek kalıcı profil yüzünden serileşme. Oysa
    kullanıcı "yeniden çevir" derken genellikle SÖZLÜĞÜ
    değiştirmiş oluyor — İNGİLİZCE KAYNAK aynı. Aynı metni yeniden indirmek
    tamamen boşa harcanan süreydi (ölçülen vaka: Shadow Slave 1. bölüm 1-2 dakika).

    Kod bu deseni zaten biliyordu: içe aktarılmış bölümler `raw_source` üzerinden
    web'e hiç gitmiyor. Bu, aynı yönlendirmenin web-yerli bölümler için karşılığı.

    None döner (→ siteye inilir) şu durumlarda: bölüm önbellekte yok; hizalama
    tutmadığı için `source` NULL; kullanıcı `refetch` ile indirmeyi zorlamış.

    NOT: bu yol `next_url`/`prev_url`'ü önbellekten TAŞIR, tazelemez. Zaten
    tazeleme işi ayrı: `refresh_metadata` (check-updates) onu yapıyor.
    """
    satir = cache.get_chapter(url)
    if satir is None or not (satir.get("source") or "").strip():
        return None
    return {
        "book_slug": satir["book_slug"],
        "book_title": satir["book_title"],
        "title": satir["title"],
        "chapter_no": satir["chapter_no"],
        "text": satir["source"],
        "next_url": satir["next_url"],
        "prev_url": satir["prev_url"],
    }


def _do_fetch_translate_save(
    url: str, api_key: str, background: bool, ticket, refetch: bool = False
) -> dict:
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
    elif not refetch and (onbellek := _onbellek_kaynagi(url)) is not None:
        # "Yeniden çevir": İngilizce kaynak zaten önbellekte → siteye HİÇ inme.
        # Kendini seçen bir daldır: bölüm önbellekte yoksa ya da kaynağı yoksa
        # `_onbellek_kaynagi` None döner ve akış aşağıdaki fetch'e düşer.
        chapter = onbellek
    else:
        # FetchError sızabilir. Toplu iş düşük öncelikli: okuyucu kapıda öne geçer.
        chapter = fetch_chapter(
            url, priority="bulk" if background else "interactive", ticket=ticket
        )

    # Birleştirilmiş kitap: slug'ı kanonikleştir, böylece bölüm/sözlük tek kitapta toplanır.
    book_slug = library.resolve_slug(chapter["book_slug"])
    # Kapak bu çekimden BEDAVAYA gelir (bölüm sayfasının og:image'ı) ve yalnız
    # boşsa yazılır. `.get`: önbellek kaynağından gelen `chapter` bu alanı
    # taşımaz — kapak yokluğu akışı bozmamalı, kapak süslemedir.
    library.set_cover(book_slug, chapter.get("cover"))
    book_title = chapter["book_title"]
    if book_slug != chapter["book_slug"]:
        merged = library.get_book(book_slug)
        if merged and merged.get("title"):
            book_title = merged["title"]

    book_glossary = glossary.ceviri_sozlugu(book_slug)
    # KOŞULLU karşılıklar: aynı İngilizce sözcüğün bağlama göre farklı çevrildiği
    # kayıtlar. Ayrı çekilir çünkü `get_glossary` sade eşlemeyi döndürmeye devam
    # ediyor — sözleşmesini değiştirmek `translate_chapter`'a kadar sızardı.
    book_kosullar = glossary.ceviri_kosullari(book_slug)
    # Çeviriden ÖNCE okunur: bu bölümün prompt'una giren sözlüğün sürümü. Çeviriden
    # sonra eklenen otomatik terimler bu prompt'ta YOKTU.
    sozluk_surumu = glossary.kitap_surumu(book_slug)
    book = library.get_book(book_slug)
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
                prev_context=prev_context, kosullar=book_kosullar,
            )
    else:
        result = translate_chapter(
            chapter["text"], api_key=api_key, glossary=book_glossary,
            prev_context=prev_context, kosullar=book_kosullar,
        )

    # Sözlüğe işleme uçuşun İÇİNDE: eklenen terimler künyenin parçası ve bölümle
    # birlikte cache'e yazılıyor, böylece bölüm ikinci açılışta (önbellek isabeti)
    # künyesini kaybetmiyor.
    eklenen = _sozluge_isle(book_slug, result, chapter.get("chapter_no"))
    ihlaller = _uyum_denetimi(result)

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
        # Zincirin FİİLEN çeviren halkası (3.6 mı flash-lite mı). `engine` yalnız
        # "gemini" der; kalite sorularının cevabı bu alanda.
        "model": result.get("model"),
        "added_terms": eklenen,
        # Sözlük uyum bayrağı: karşılığı KAYITLI olduğu hâlde İngilizce kalan terimler.
        "glossary_leaks": ihlaller,
        # İngilizce kalıntı bayrağı: onarım turundan SONRA hâlâ çevrilmemiş
        # paragraflar. Boş = temiz.
        "ingilizce_kalinti": result.get("ingilizce_kalinti") or {},
        # Bu çeviride kullanılan sözlüğün sürümü (künye).
        "sozluk_surumu": sozluk_surumu,
        "cached": False,
    }
    cache.save_chapter(url, payload)
    return payload


def _render_import_page(url: str, staged: dict, api_key: str) -> dict:
    """Görsel içerik bölümü (content_type="html"): PDF sayfasını çevir+render / EPUB
    HTML'ini yerinde çevir. Sonuç HTML olarak cache'lenir (tekrar açılışta yeniden
    render/çeviri yok). Medya, sahnelenen (pdf-/epub-) slug altında saklanır."""
    from . import import_translate

    if not _translate_mod.ceviri_anahtari_var_mi(api_key):
        raise TranslateError(_translate_mod.ANAHTAR_YOK_MESAJI)
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
        "engine": _translate_mod.motor_adi(model),
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
    if not _translate_mod.ceviri_anahtari_var_mi(api_key):
        raise TranslateError(_translate_mod.ANAHTAR_YOK_MESAJI)
    chapter = fetch_chapter(url, priority="interactive")
    # Bölünme fix: bu web serisinin host-türevli slug'ını (örn. renegade-immortal)
    # hedef kitaba alias'la → kullanıcı SONRAKI BÖLÜM ile normal okuyucudan devam
    # ettiğinde de bölümler AYRI kitap açmaz, resolve_slug hedefe çözer.
    host_slug = chapter.get("book_slug")
    if host_slug and host_slug != target_slug:
        library.set_alias(host_slug, target_slug)
    book_glossary = glossary.ceviri_sozlugu(target_slug)
    # Koşullar `_fetch_translate_save` ile AYNI: sözlüğü okuyan her yol koşulları
    # da okumalı, yoksa "web'den devam" ile eklenen bölüm kuralın dışında kalır —
    # `model` künyesinde tam bu hata yaşandı.
    book_kosullar = glossary.ceviri_kosullari(target_slug)
    sozluk_surumu = glossary.kitap_surumu(target_slug)  # `_fetch_translate_save` ile AYNI künye
    tail = cache.tail_chapter(target_slug)
    # NUMARA ÖNCELİĞİ (2026-09-02'de düzeltildi). Eskiden yalnız `tail+1` vardı ve
    # `fetch_chapter`'ın başlıktan/URL'den zaten çıkardığı numara yok sayılıyordu;
    # ARADAN bir bölüm eklendiğinde numara uydurulmuş oluyordu. Ölçülen gerçek vaka
    # (Shadow Slave): kuyruk 140'tayken eklenen `chapter-137` 141 numarasını, sonra
    # eklenen `chapter-141` 142'yi aldı — okuyucuda bölüm sırası ve adı kaydı.
    #
    # Ama "sayfanın numarası HER ZAMAN kazanır" da YANLIŞ olurdu: bu fonksiyonun
    # asıl işi PASTE-tabanlı bir kitabı web'e köprülemek ve orada web sayfasının
    # numarası BAŞKA bir numaralandırma evreninden gelir (paste kitabın 2. bölümü,
    # sitenin 1704. bölümü olabilir). Ölçüt bu yüzden kitabın KENDİ numaralandırması:
    # kuyruğun URL'sindeki numara kuyruğun `chapter_no`'suna eşitse kitap zaten
    # kaynağın numaralandırmasını izliyor demektir, sayfaya güvenilir. Paste
    # kitabında kuyruk `paste://…` olduğu için bu koşul tutmaz ve eski davranış
    # (tail+1) aynen korunur.
    sayfa_no = chapter.get("chapter_no")
    kuyruk_url_no = _url_bolum_no(tail["url"]) if tail else None
    kitap_kaynak_numarali = (
        tail is not None
        and kuyruk_url_no is not None
        and kuyruk_url_no == tail["chapter_no"]
    )
    if chapter_no is not None:
        no = chapter_no  # kullanıcı açıkça verdi: en üstün kaynak
    elif sayfa_no is not None and kitap_kaynak_numarali:
        no = sayfa_no  # kitap zaten kaynağın numaralandırmasını izliyor
    else:
        no = (tail["chapter_no"] or 0) + 1 if tail else 1  # köprüleme: sıraya ekle

    # ZİNCİR: yalnız gerçekten KUYRUĞA eklerken kuyruğa bağla. Köprülemede `prev`
    # kuyruk OLMALI (sayfanın kendi prev'i bu kitapta bulunmayan bir web adresidir).
    # ARAYA eklerken tersi geçerli: kuyruğun next'ini yeni bölüme çevirmek zinciri
    # koparır — 140'ın next'i 137'ye dönmüştü.
    kuyruga_ekleniyor = tail is None or no > (tail["chapter_no"] or 0)
    prev_url = (tail["url"] if tail else None) if kuyruga_ekleniyor else chapter.get("prev_url")
    book = library.get_book(target_slug)
    with api_durum.baglam(url=url):
        result = translate_chapter(
            chapter["text"], api_key=api_key, glossary=book_glossary,
            prev_context=cache.prev_translation(target_slug, prev_url, no),
            kosullar=book_kosullar,
        )
    book_title = (book and book.get("title")) or chapter["book_title"]
    eklenen = _sozluge_isle(target_slug, result, no)  # künyeye girecek, kayıttan ÖNCE
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
        # Uyum bayrağı da `_fetch_translate_save` ile AYNI: künyeyi üreten dört
        # noktadan biri eksik kalırsa o yoldan gelen bölüm sessizce denetimsiz olur
        # — `model` alanında tam bu hata yaşandı.
        "glossary_leaks": _uyum_denetimi(result),
        # Kalıntı bayrağı da `_fetch_translate_save` ile AYNI: bayrağı üreten
        # noktalardan biri eksik kalırsa o yoldan gelen bölüm sessizce
        # denetimsiz olur — `model` alanında tam bu hata yaşandı.
        "ingilizce_kalinti": result.get("ingilizce_kalinti") or {},
        "sozluk_surumu": sozluk_surumu,
        "cached": False,
    }
    cache.save_chapter(url, payload)
    if prev_url and kuyruga_ekleniyor:
        # YALNIZ kuyruğa eklerken: aradan bir bölüm eklenirken kuyruğun next'ini
        # yeni bölüme çevirmek zinciri koparıyordu (140 -> 137 -> 141 gibi).
        cache.set_next(prev_url, url)
    library.upsert_book(
        target_slug, book_title, url, chapter["title"], no, update_position=False
    )
    # Kapağı yazan İKİNCİ nokta (bkz. tests/test_kapak.py tel tuzağı): "web'den
    # devam" ile eklenen kitap da kapaksız kalmamalı.
    library.set_cover(target_slug, chapter.get("cover"))
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


def terim_etkisi(book_slug: str, source: str) -> dict:
    """Bir sözlük terimini düzeltmek ÇEVRİLMİŞ hangi bölümleri etkiler?

    Sözlük ekranındaki ipucu "değişiklik yeni bölümlerde geçerli; eski bölüm için
    Yeniden çevir" diyordu ama HANGİ eski bölümler olduğunu söylemiyordu —
    kullanıcı elle aramak zorundaydı.

    Eşleştirme `translate._term_regex` ile (yazım varyantı + çekim eki toleranslı),
    kaynak metin üzerinde. Kaynak metni olmayan bölümler sayılamaz; `kapsama`
    alanı bunu açıkça söyler ki "0 bölüm" yanıltıcı okunmasın.
    """
    bolumler = cache.kaynak_bolumleri(book_slug)
    toplam, kapsanan, _metin = cache.kaynak_kapsamasi(book_slug)
    terim = (source or "").strip()
    if not terim:
        return {"count": 0, "chapters": [], "kapsama": [kapsanan, toplam]}
    desen = _translate_mod._term_regex(terim)
    eslesen = []
    for b in bolumler:
        if not desen.search(b["source"]):
            continue
        # ÖRNEK: terimin geçtiği İngilizce cümle + HİZALI Türkçe paragraf. Kullanıcı
        # yeniden çevirmeden önce bugünkü çeviride terimin nasıl durduğunu görmeli.
        # Paragraf sayıları tutmuyorsa hangi Türkçe paragrafın karşılık olduğu
        # BİLİNMEZ; uydurmak yerine boş bırakılır.
        en_paras = b["source"].split("\n\n")
        tr_paras = (b.get("translation") or "").split("\n\n")
        idx = next((i for i, p in enumerate(en_paras) if desen.search(p)), None)
        ornek_tr = None
        if idx is not None and len(tr_paras) == len(en_paras):
            ornek_tr = tr_paras[idx].strip()[:ETKI_ORNEK_MAX] or None
        eslesen.append({
            "url": b["url"],
            "chapter_no": b["chapter_no"],
            "title": b["title"],
            "ornek_en": _translate_mod.cumle_bul(
                en_paras[idx] if idx is not None else b["source"], terim
            ),
            "ornek_tr": ornek_tr,
            "ceviri_zamani": b.get("ceviri_zamani"),
        })
    return {"count": len(eslesen), "chapters": eslesen, "kapsama": [kapsanan, toplam]}


# Etki listesindeki Türkçe örnek paragrafın üst sınırı: liste satırı bir alıntı değil,
# "bugün nasıl çevrilmiş" sorusuna göz ucuyla bakmaktır.
ETKI_ORNEK_MAX = 300

