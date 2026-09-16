"""novel-cevirmen backend — FastAPI.

Çalıştırma (proje kökünden):
    .venv\\Scripts\\python.exe app\\server.py
Telefondan erişim: http://<PC-LAN-IP>:8000  (aynı Wi-Fi)
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))  # 'core' paketini CWD'den bağımsız import et

import json  # noqa: E402
import mimetypes  # noqa: E402
import os  # noqa: E402

# Windows'ta mimetypes kayıt defterinden okur; .webmanifest tanımsız, .svg yanlış
# kayıtlı olabilir. Yanlış Content-Type → Chrome PWA ikonunu/manifesti reddeder.
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("image/svg+xml", ".svg")
# .woff2 de ayni tuzakta: yanlis Content-Type ile gelen font sessizce YOK SAYILIR
# ve yazi sistem fontuna duser — arizanin hicbir hata mesaji olmaz.
mimetypes.add_type("font/woff2", ".woff2")
# .js AÇIKÇA kaydedilir: okuyucu ES modülleriyle yükleniyor ve tarayıcı modül
# betiğini yalnız JavaScript MIME türüyle kabul eder. Windows kayıt defterinde
# `.js` bazı kurulumlarda `text/plain` görünür; o durumda uygulama HİÇ açılmaz
# ("Expected a JavaScript module script") ve hata yalnız konsolda görünür.
mimetypes.add_type("text/javascript", ".js")

from dotenv import load_dotenv  # noqa: E402
from fastapi import FastAPI, HTTPException, Query, Request, Response  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402

from pydantic import BaseModel  # noqa: E402

from core import cache, epub_export, glossary, import_book, jobs, kullanim, library, media, pipeline, reading_log, settings, synthetic  # noqa: E402
from core import translate as translate_mod  # noqa: E402
from core.synthetic import ImportedChapterMissing, MangaTranslating  # noqa: E402
from core.fetch import CloudflareChallenge, FetchError, refresh_clearance  # noqa: E402
from core.translate import (  # noqa: E402
    ANAHTAR_YOK_MESAJI,
    TranslateError,
    ceviri_anahtari_var_mi,
    suggest_term,
)

load_dotenv(APP_DIR.parent / ".env")  # tek kaynak: novel-cevirmen/.env
API_KEY = os.getenv("GEMINI_API_KEY")

app = FastAPI(title="novel-cevirmen")

# Eski (sadece-önbellek) kurulumlardaki kitapları paylaşılan kütüphaneye taşı.
library.backfill_from_cache()


@app.on_event("startup")
def resume_bulk_jobs() -> None:
    """Sunucu açılırken yarım kalan toplu işleri checkpoint'lerinden sürdür."""
    jobs.resume_running(API_KEY)


def _pipeline_http_error(exc: BaseException) -> HTTPException:
    """Pipeline istisnasını tipli HTTP hatasına çevir (error_class ile). Frontend
    kırılgan string yerine sınıfa göre dallanır (hata kartı, 'metni yapıştır')."""
    if isinstance(exc, ImportedChapterMissing):
        return HTTPException(404, {"message": str(exc), "error_class": "ImportedChapterMissing"})
    if isinstance(exc, CloudflareChallenge):
        return HTTPException(502, {"message": str(exc), "error_class": "CloudflareChallenge"})
    if isinstance(exc, FetchError):
        from core.fetch import CF_ORIGIN_ERRORS
        ec = "OriginError" if any(f"HTTP {e}" in str(exc) for e in CF_ORIGIN_ERRORS) else "FetchError"
        return HTTPException(502, {"message": str(exc), "error_class": ec})
    if isinstance(exc, TranslateError):
        # Ölçüt "API_KEY değişkeni dolu mu" DEĞİL: ikinci anahtar yalnız `.env`'de
        # duruyor olabilir (`GEMINI2_API_KEY`) ve onu görmeyen bir kapı, pekâlâ
        # çalışabilecek bir kurulumda 503 yerine yanıltıcı bir 500 "anahtar yok"
        # döndürürdü. Kapı tek değişkene değil anahtar HAVUZUNA bakar.
        if not ceviri_anahtari_var_mi(API_KEY):
            return HTTPException(500, ANAHTAR_YOK_MESAJI)
        return HTTPException(503, {"message": str(exc), "error_class": "TranslateError"})
    raise exc  # bilinmeyen → olduğu gibi yukarı


@app.get("/api/chapter")
def get_chapter(
    response: Response,
    url: str = Query(..., description="novelbin bölüm URL'i"),
    refresh: bool = Query(False, description="Önbelleği yok say, yeniden çevir"),
    source: bool = Query(False, description="İki-dilli: hizalı İngilizce kaynağı da getir"),
    track: bool = Query(True, description="Kitabın 'kaldığın yer' konumu bu bölüme ilerlesin mi"),
    refetch: bool = Query(False, description="Siteden yeniden indir (kaynağın kendisi bozuksa)"),
) -> dict:
    """Bölümü çek + Türkçe'ye çevir. Önbellekte varsa anında döner.

    source=1: yanıtta paragraf-hizalı İngilizce kaynak (`source`) da gelir; eski bölümde
    yoksa bir kez yeniden çevrilerek eklenir. (Sync def: Playwright thread havuzunda.)

    track=0: sonsuz okumada akışa ÖNDEN eklenen (henüz okunmamış) bölümler için —
    konumu ilerletme; konumu yalnız aktif bölümün position POST'u belirlesin.

    refetch=1: refresh yolunu SİTEDEN indirmeye zorlar. Varsayılan 0 — önbellekte
    hizalı İngilizce kaynak varsa "yeniden çevir" web'e hiç gitmez (Playwright +
    Cloudflare, deneme başına 60 sn zaman aşımı). Kullanıcı "yeniden çevir" derken
    genellikle sözlüğü/üslubu değiştirmiş oluyor; İngilizce kaynak aynı kalıyor.
    """
    try:
        return pipeline.get_or_translate(
            url, API_KEY, refresh, want_source=source, advance_position=track,
            refetch=refetch,
        )
    except MangaTranslating as exc:
        # Manga bölümü arka planda çevriliyor → sayfa henüz hazır değil. Okuyucu
        # "çevriliyor N/total" gösterip poll eder (hata değil, 200). no-store ŞART:
        # service worker bu geçici yanıtı cache'lerse (track'i anahtardan siler)
        # poll aynı bayat "translating"e düşer, sayfa asla html'e dönmez.
        response.headers["Cache-Control"] = "no-store"
        staged = cache.get_staged(url) or {}
        return {
            "content_type": "translating",
            "title": staged.get("title") or "Sayfa",
            "chapter_no": staged.get("chapter_no"),
            "next_url": staged.get("next_url"),
            "prev_url": staged.get("prev_url"),
            "book_slug": staged.get("book_slug"),
            "book_title": staged.get("book_title") or "Manga",
            "translation": "", "source": None, "detected_names": [], "chunk_count": 1,
            "done": exc.done, "total": exc.total, "cached": False,
        }
    except (ImportedChapterMissing, CloudflareChallenge, FetchError, TranslateError) as exc:
        raise _pipeline_http_error(exc)


class PrefetchRequest(BaseModel):
    url: str  # arka planda ısıtılacak bölümün (genelde next_url) http(s) adresi


# Uçuştaki prefetch'ler — aynı URL için ikinci tetiği (fetch/translate masrafı) engeller.
# Single-flight pipeline'da da tekilleştirir; bu set, thread bile açmadan erken kesip
# gereksiz iş parçacığı/DB dokunuşu üretmez.
_PREFETCH_INFLIGHT: set[str] = set()
_PREFETCH_LOCK = threading.Lock()


@app.post("/api/prefetch")
def prefetch_chapter(req: PrefetchRequest) -> dict:
    """Sonraki bölümü sessizce arka planda hazırla (sonsuz okuma ısıtması).

    Okuyucu bir bölüm açınca `next_url`'i bu uçla ısıtır: kullanıcı akışın sonuna
    geldiğinde bölüm cache'te hazır olur (0 bekleme). `background=True` → çekim ve
    çeviri DÜŞÜK öncelikli (okuyucunun canlı isteği kapıda öne geçer, E-1) ve
    kitabın "kaldığın yer" konumu İLERLETİLMEZ — ısıtılan bölüm okunmuş sayılmaz.
    Yalnız http(s) ısıtılır; sentetik şemalar (`paste://`) yok sayılır. Fire-and-
    forget: uç hemen döner, iş daemon thread'de sürer; hata yutulur (okuyucu bölümü
    gerçekten açınca zaten yeniden dener). reading-log'a hiç girmez (karar #8).
    """
    url = req.url
    if not API_KEY or not url or not url.startswith(("http://", "https://")):
        return {"ok": True, "queued": False}
    if cache.get_chapter(url) is not None:
        return {"ok": True, "queued": False, "cached": True}
    with _PREFETCH_LOCK:
        if url in _PREFETCH_INFLIGHT:
            return {"ok": True, "queued": False}
        _PREFETCH_INFLIGHT.add(url)

    def _run() -> None:
        try:
            pipeline.get_or_translate(url, API_KEY, background=True)
        except Exception:
            pass  # prefetch en iyi çabadır; okuyucu bölümü açınca yeniden dener
        finally:
            with _PREFETCH_LOCK:
                _PREFETCH_INFLIGHT.discard(url)

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "queued": True}


@app.delete("/api/chapter")
def delete_chapter(url: str = Query(..., description="Silinecek bölümün URL'i")) -> dict:
    """Çevrilmiş bölümü önbellekten sil (örn. farklı siteden gelen kopya).

    Bölüm kitabın 'kaldığın yer' işaretiyse o da temizlenir. Tekrar açılırsa
    bölüm yeniden çekilip çevrilir.
    """
    existing = cache.get_chapter(url)
    deleted = cache.delete_chapter(url)
    if deleted and existing and existing.get("book_slug"):
        library.clear_position_if(existing["book_slug"], url)
    return {"ok": deleted}


@app.get("/api/books")
def list_books() -> dict:
    """Paylaşılan kütüphane: tüm cihazlarda görünen kitaplar + son okuma konumu."""
    return {"books": library.list_books()}


@app.get("/api/book/{slug}/chapters")
def book_chapters(slug: str) -> dict:
    """Bir kitabın çevrilmiş (önbellekteki) bölümlerinin listesi."""
    return {"chapters": cache.list_chapters(slug)}


class GlossaryOrnek(BaseModel):
    # Okurken eklenen terimin kökeni: geçtiği cümle + bölüm numarası. YALNIZ boşsa
    # yazılır (bkz. glossary.ornek_doldur).
    kaynak_cumle: str | None = None
    bolum: int | None = None


class RetranslateRequest(BaseModel):
    urls: list[str]  # yeniden çevrilecek, bu kitabın ÇEVRİLMİŞ bölümleri


class GlossaryTerm(BaseModel):
    source: str
    target: str | None = None
    ornek: GlossaryOrnek | None = None
    # KOSUL: karsiligin hangi baglamda gecerli oldugunu anlatan serbest metin.
    # None = ALAN GONDERILMEDI (mevcut kosul KORUNUR); "" = temizle. Ayrim
    # sart: okuyucunun cevrimdisi kuyrugu yalniz {source,target} gonderiyor ve
    # None'i "sil" diye okumak, sıradan bir karsilik duzeltmesinin kurali
    # sessizce yok etmesi demekti.
    kosul: str | None = None
    # ÇAKIŞMA TABANI: istemcinin düzenlemeye başlarken gördüğü kayıt sürümü
    # (0 = "kayıt yok sanıyorum"). Uyuşmazsa 409 + güncel kayıt döner; öteki
    # cihazın düzeltmesi sessizce ezilmez. None = denetleme yok (eski istemci,
    # hızlı ekleme formu — orada üzerine yazmak bilinçli davranıştır).
    taban_surum: int | None = None


class GlossaryImportRequest(BaseModel):
    # İKİ biçim kabul edilir. `kayitlar`: tam kayıtlı yedek (koşul + köken, biçim
    # sürümü 2). `terms`: eski biçim (yalnız kaynak -> karşılık) — elde eski yedek
    # dosyaları var ve önbellekteki eski okuyucu yalnız bunu gönderir.
    terms: dict[str, str] | None = None
    kayitlar: list | None = None
    # "dosya" = dosyadaki alanlar kayıtlı terimin üzerine yazılır;
    # "mevcut" = yalnız eksikler eklenir (kullanıcı kaydı korunur).
    strateji: str = "mevcut"


class GlossarySuggestRequest(BaseModel):
    source: str
    context: str | None = None  # terimin geçtiği cümle: kişi mi yer mi, bağlam belirler


class MergeRequest(BaseModel):
    target: str


class PositionRequest(BaseModel):
    url: str
    ratio: float
    # Konum bir ÜÇLÜ: (url, ad, numara). Ad/numara OPSİYONEL — önbellekteki eski
    # bir app.js yalnız (url, ratio) gönderir ve 422 ile reddedilmemeli; sunucu o
    # durumda bayat adı temizler (bkz. library.set_position).
    title: str | None = None
    chapter_no: int | None = None


class BulkRequest(BaseModel):
    start_url: str
    count: int = 10


class ReadingLogRequest(BaseModel):
    day: str  # istemcinin YEREL günü (YYYY-MM-DD) — "bugün" UTC'ye kaymasın
    slug: str
    url: str


class StatusRequest(BaseModel):
    status: str  # okunuyor | beklemede | bitti


class CeviriModeliRequest(BaseModel):
    model: str


class PasteImportRequest(BaseModel):
    title: str  # bölüm başlığı
    text: str  # yapıştırılan İngilizce ham metin
    book_title: str | None = None  # yeni kitap adı (slug verilmediyse)
    slug: str | None = None  # mevcut paste-kitabına bölüm ekleme
    chapter_no: int | None = None  # elle geçersiz kılma (varsayılan: max+1)


class PasteUrlImportRequest(BaseModel):
    url: str  # takılan bölümün GERÇEK http(s) adresi
    slug: str  # ait olduğu (web) kitabın slug'ı
    text: str  # yapıştırılan İngilizce ham metin
    title: str | None = None  # bölüm başlığı (yoksa "Bölüm N")
    chapter_no: int | None = None


class FetchNextRequest(BaseModel):
    url: str  # bu kitaba sonraki bölüm olarak çekilecek web adresi
    chapter_no: int | None = None


class RefreshNavRequest(BaseModel):
    url: str  # gezinmesi (next/prev) web'den tazelenecek bölüm


@app.post("/api/book/{slug}/merge-into")
def merge_book(slug: str, req: MergeRequest) -> dict:
    """`slug` kitabını `target` kitabıyla birleştir (aynı kitap, farklı slug)."""
    try:
        canonical = library.merge_books(slug, req.target)
    except ValueError as exc:  # E-8: sentetik kitap birleştirilemez
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "canonical": canonical}


@app.delete("/api/book/{slug}")
def remove_book(slug: str) -> dict:
    """Kitabı + tüm bölümlerini/sözlüğünü kalıcı sil (boş/mükerrer kitap temizliği)."""
    ok = library.delete_book(library.resolve_slug(slug))
    if not ok:
        raise HTTPException(status_code=404, detail="Kitap bulunamadı.")
    return {"ok": True}


MAX_UPLOAD = 50 * 1024 * 1024  # 50MB yükleme sınırı (plan / D-B8)


async def _read_upload(request: Request) -> bytes:
    """Yükleme gövdesini oku + boyut sınırını uygula (dosya adı asla path'e geçmez)."""
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Boş dosya.")
    if len(body) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="Dosya 50MB sınırını aşıyor.")
    return body


@app.get("/media/{rel:path}")
def serve_media(rel: str) -> FileResponse:
    """İçe aktarılan kitapların medyası (render'lı sayfa PNG'leri, EPUB resimleri).
    Yalnız media kökü altındaki dosyalar (path traversal reddedilir). API'den SONRA,
    `/` catch-all'dan ÖNCE tanımlı (E-6)."""
    p = media.resolve(rel)
    if p is None:
        raise HTTPException(status_code=404, detail="Bulunamadı.")
    return FileResponse(str(p))


@app.post("/api/import/epub")
async def import_epub_endpoint(request: Request, filename: str = Query("")) -> dict:
    """EPUB dosyasını (ham gövde) sahneli kitaba çevir. Çeviri YAPMAZ — bölümler
    okununca ya da TOPLU ÇEVİR ile çevrilir (kota kapısı). Döner: {slug, title,
    chapter_count, first_url}. Ağır parse thread havuzunda (event loop bloklanmaz)."""
    body = await _read_upload(request)
    try:
        return await run_in_threadpool(import_book.import_epub, body, filename)
    except import_book.BookImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/import/pdf")
async def import_pdf_endpoint(
    request: Request,
    filename: str = Query(""),
    pages_per_chapter: int = Query(10, ge=1, le=200),
) -> dict:
    """PDF dosyasını sahneli kitaba çevir (N sayfa = 1 bölüm). Çeviri YAPMAZ."""
    body = await _read_upload(request)
    try:
        return await run_in_threadpool(
            import_book.import_pdf, body, pages_per_chapter, filename
        )
    except import_book.BookImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class MangaUrlRequest(BaseModel):
    url: str  # manga bölüm URL'si (asurascans vb.)


@app.post("/api/import/manga-url")
def import_manga_url_endpoint(req: MangaUrlRequest) -> dict:
    """Manga bölümünü WEB'den çek (URL) → sayfaları sahnele. Sync def: Playwright thread
    havuzunda. Döner: {slug, title, chapter_count, first_url}."""
    try:
        return import_book.import_manga_url(req.url)
    except (CloudflareChallenge, FetchError) as exc:
        raise _pipeline_http_error(exc)
    except import_book.BookImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class MangaContinueRequest(BaseModel):
    slug: str  # devam ettirilecek manga kitabının slug'ı


@app.post("/api/manga/continue")
def manga_continue(req: MangaContinueRequest) -> dict:
    """Manga bölümü bitince SONRAKİ bölümü site'den çek + zincire ekle (sonsuz devam).

    Kitapta saklı manga_next_url'i çeker, sayfaları dilimleyip mevcut kitaba ekler,
    kaynak/sonraki URL'i günceller, batch çeviriyi başlatır. Novel sonsuz okumanın manga
    karşılığı. Sync def: Playwright threadpool'da. Döner: {available, first_url, added,
    has_next}. available False → devam yok (son bölüm / manga değil / next yok)."""
    from core import manga_batch, manga_fetch

    slug = library.resolve_slug(req.slug)
    book = library.get_book(slug)
    if not book or not slug.startswith("manga-"):
        return {"available": False, "reason": "not_manga"}
    nxt = book.get("manga_next_url")
    if not nxt:
        return {"available": False, "reason": "no_next"}
    try:
        r = manga_fetch.fetch_manga_chapter(nxt)
    except (CloudflareChallenge, FetchError) as exc:
        raise _pipeline_http_error(exc)
    res = import_book.append_manga_chapter(slug, book["title"], r.get("images") or [])
    if not res.get("added"):
        return {"available": False, "reason": "empty"}  # boş çekim → retryable, next korunur
    library.set_manga_source(slug, nxt, r.get("next_url"))
    if API_KEY:
        manga_batch.ensure_started(slug, API_KEY)
    return {
        "available": True,
        "first_url": res.get("first_url"),
        "added": res.get("added", 0),
        "has_next": bool(r.get("next_url")),
    }


@app.post("/api/import/manga")
async def import_manga_endpoint(request: Request, filename: str = Query("")) -> dict:
    """Manga'yı (CBZ/ZIP ya da tek görsel, ham gövde) sahneli kitaba çevir. Çeviri
    YAPMAZ — sayfa okununca Gemini-vision ile balonlar çevrilir. Döner: {slug, title,
    chapter_count, first_url}."""
    body = await _read_upload(request)
    try:
        return await run_in_threadpool(import_book.import_manga, body, filename)
    except import_book.BookImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/import/paste")
def import_paste(req: PasteImportRequest) -> dict:
    """Yapıştırılan İngilizce metni sahneli bölüm olarak ekle + çeviri işini başlat.

    Bölüm `paste://` şemasıyla zincire eklenir (E-23, atomik); ham metin
    raw_source'ta kalıcıdır (E-18). Çeviri paste-import işi olarak arka planda
    koşar — rozet/ilerleme/checkpoint bulk ile aynıdır."""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Yapıştırılan metin boş.")
    title = (req.title or "").strip()
    if req.slug:
        slug = req.slug
        if not synthetic.is_synthetic_slug(slug):
            raise HTTPException(
                status_code=400, detail="Yalnız içe aktarılan kitaba bölüm eklenebilir."
            )
        book = library.get_book(slug)
        if book is None:
            raise HTTPException(status_code=404, detail="Kitap bulunamadı.")
        book_title = book["title"]
    else:
        book_title = (req.book_title or title or "İçe Aktarılan").strip()
        # "Aynı isim = aynı kitap": aynı başlık zaten içe aktarılmışsa YENİ bir
        # -2 kitabı açma, mevcut paste-kitabına bölüm ekle (mükerrer raf kaydını
        # önler — kullanıcı başlığı tekrar yazınca doğal davranış budur). Başlık
        # ilk kezse tahsis et (boş/simge başlık paste-<rastgele> alır, çakışmaz).
        base = synthetic.slugify_title(book_title)
        slug = base if library.get_book(base) is not None else synthetic.allocate_slug(book_title)
    ch = synthetic.append_chapter(
        slug, book_title, title or f"Bölüm", text, req.chapter_no
    )
    # Kitap rafta görünsün; okuma konumu İLERLETİLMEZ (arka plan kuralı).
    library.upsert_book(
        slug, book_title, ch["url"], title, ch["chapter_no"], update_position=False
    )
    job_id = jobs.start_bulk(slug, ch["url"], 1, API_KEY, job_type="paste-import")
    return {
        "ok": True, "slug": slug, "url": ch["url"],
        "chapter_no": ch["chapter_no"], "job_id": job_id,
    }


@app.post("/api/import/paste-url")
def import_paste_url(req: PasteUrlImportRequest) -> dict:
    """Takılan bir web bölümünün metnini GERÇEK URL'sine yapıştır (site engelli/çevrimdışı).

    Bölüm o http URL'nin altına sahnelenir (raw_source E-18); kitap web-yerli kalır
    (`paste://` üretilmez, merge sorunu yok). Çeviri paste-import işi olarak arka
    planda koşar. Pipeline raw_source-öncelikli routing ile web'e inmeden çevirir."""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Yapıştırılan metin boş.")
    url = (req.url or "").strip()
    if not url.startswith(("http://", "https://")) or synthetic.is_synthetic_url(url):
        raise HTTPException(status_code=400, detail="Geçerli bir web (http) adresi gerekli.")
    slug = library.resolve_slug(req.slug)
    if synthetic.is_synthetic_slug(slug):
        raise HTTPException(
            status_code=400,
            detail="Sentetik kitaba web bölümü doldurulamaz; METİN sekmesini kullanın.",
        )
    book = library.get_book(slug)
    if book is None:
        raise HTTPException(status_code=404, detail="Kitap bulunamadı.")
    title = (req.title or "").strip()
    ch = synthetic.stage_url_chapter(
        slug, book["title"], title or "Bölüm", text, url, req.chapter_no
    )
    # Konum İLERLETİLMEZ (arka plan kuralı); kitap zaten rafta.
    library.upsert_book(
        slug, book["title"], ch["url"], title, ch["chapter_no"], update_position=False
    )
    job_id = jobs.start_bulk(slug, ch["url"], 1, API_KEY, job_type="paste-import")
    return {
        "ok": True, "slug": slug, "url": ch["url"],
        "chapter_no": ch["chapter_no"], "job_id": job_id,
    }


@app.post("/api/book/{slug}/fetch-next")
def fetch_next(slug: str, req: FetchNextRequest) -> dict:
    """Verilen web URL'sini bu kitaba 'sonraki bölüm' olarak çek+çevir+bağla (B).

    Paste ya da web kitabında "web'den devam": sayfanın gerçek next'i korunur, sonraki
    bölümler siteden gelmeye devam eder. Çekme senkron (Playwright thread havuzunda);
    hata tipli döner → hata kartı 'metni yapıştır' önerebilir."""
    url = (req.url or "").strip()
    if not url.startswith(("http://", "https://")) or synthetic.is_synthetic_url(url):
        raise HTTPException(status_code=400, detail="Geçerli bir web (http) adresi gerekli.")
    canon = library.resolve_slug(slug)
    if library.get_book(canon) is None:
        raise HTTPException(status_code=404, detail="Kitap bulunamadı.")
    try:
        payload = pipeline.fetch_into_book(url, canon, API_KEY, req.chapter_no)
    except (CloudflareChallenge, FetchError, TranslateError) as exc:
        raise _pipeline_http_error(exc)
    return {"ok": True, "slug": canon, "url": url, "chapter_no": payload["chapter_no"]}


@app.post("/api/chapter/refresh-nav")
def refresh_nav(req: RefreshNavRequest) -> dict:
    """Bölümün gezinmesini (next/prev) web'den tazele (E-3, çeviri yakmaz).

    "Sonrakini web'den getir": yapıştırılan/eski bir bölümün sayfasını çekip next'ini
    öğrenir, cache'i günceller → okuyucu web'den devam edebilir. Site engelliyse tipli
    hata. Sentetik URL için fetch'e inmez, sahneli nav'ı döndürür."""
    url = (req.url or "").strip()
    try:
        nav = pipeline.refresh_metadata(url)
    except (CloudflareChallenge, FetchError) as exc:
        raise _pipeline_http_error(exc)
    return {"ok": True, **nav}


@app.post("/api/reading-log")
def post_reading_log(req: ReadingLogRequest) -> dict:
    """Okuyucuda başarıyla render edilen bölümü günlüğe yaz (best-effort).

    İstemci olayıdır: SW cache-first GET'i sunucuya ulaştırmadığı için sunucu-yanı
    loglama mümkün değil. Günde bölüm başına bir satır (UNIQUE ile tekil)."""
    logged = reading_log.log_read(req.day, library.resolve_slug(req.slug), req.url)
    return {"ok": logged}


@app.get("/api/stats")
def get_stats(day: str = Query(..., description="İstemcinin yerel günü (YYYY-MM-DD)")) -> dict:
    """Okuma istatistiği: bugün / toplam benzersiz bölüm (raf altı satır)."""
    return reading_log.stats(day)


@app.post("/api/book/{slug}/status")
def set_book_status(slug: str, req: StatusRequest) -> dict:
    """Kitabın yaşam durumu (okunuyor/beklemede/bitti) — raf filtresi bunu okur."""
    if req.status not in library.BOOK_STATUSES:
        raise HTTPException(status_code=400, detail="Geçersiz durum.")
    ok = library.set_status(library.resolve_slug(slug), req.status)
    if not ok:
        raise HTTPException(status_code=404, detail="Kitap bulunamadı.")
    return {"ok": True, "status": req.status}


@app.post("/api/book/{slug}/position")
def set_position(slug: str, req: PositionRequest) -> dict:
    """Okuma konumunu kaydet (cihazlar arası paylaşılır): url + oran + ad/numara.

    Ad ve numara URL ile BİRLİKTE gelir; ayrı yazılırlarsa kütüphane fişi okunan
    bölümden geride bir numara gösterir (bkz. library.set_position).
    """
    library.set_position(slug, req.url, req.ratio, req.title, req.chapter_no)
    return {"ok": True}


@app.post("/api/book/{slug}/bulk")
def start_bulk(slug: str, req: BulkRequest) -> dict:
    """Arka plan toplu çeviri başlat (sekme kapansa da sürer). İş kimliği döner."""
    count = max(1, min(500, req.count))
    job_id = jobs.start_bulk(slug, req.start_url, count, API_KEY)
    return {"job_id": job_id}


@app.get("/api/bulk/{job_id}")
def bulk_status(job_id: str) -> dict:
    """Toplu çeviri işinin durumu (polling)."""
    status = jobs.get_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="İş bulunamadı.")
    return status


@app.post("/api/bulk/{job_id}/stop")
def bulk_stop(job_id: str) -> dict:
    """Çalışan toplu çeviri işini durdur."""
    return {"ok": jobs.stop(job_id)}


@app.get("/api/book/{slug}/job")
def book_job(slug: str) -> dict:
    """Kitabın çalışan veya en son tamamlanan toplu işini keşfet."""
    return {"job": jobs.get_book_job(slug)}


@app.post("/api/clearance/refresh")
def clearance_refresh() -> dict:
    """Cloudflare tarayıcı oturumunu sunucuyu yeniden başlatmadan tazele."""
    try:
        return refresh_clearance()
    except FetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/api/book/{slug}/glossary")
def get_book_glossary(
    slug: str,
    bolum: str | None = Query(None, description="Bu bölümün kaynağında geçen terimler de dönsün"),
) -> dict:
    """Sözlük: sade eşleme (`terms`) + köken bilgili satırlar (`rows`).

    `terms` GERİYE DÖNÜK uyum için duruyor — çevrimdışı kuyruğu olan okuyucu ve
    eski önbelleğe alınmış istemci onu bekliyor. `rows` köken sütunlarını taşır
    (ne zaman, hangi yoldan, hangi bölümde girdi); sözlük ekranındaki süzme ve
    künye rozetindeki düzeltme bunu kullanır.
    """
    veri = {
        "terms": glossary.get_glossary(slug),
        "kosullar": glossary.get_kosullar(slug),
        "rows": glossary.get_glossary_rows(slug),
        # Yazım hatası olabilecek çiftler (`Orc`/`Ore`). Otomatik birleştirme YOK —
        # tek harf farkı gerçek bir anlam farkı olabilir; karar kullanıcınındır.
        "warnings": glossary.yakin_terimler(slug),
        # Kitabın sözlük sürümü: bölüm künyesindeki `sozluk_surumu` ile kıyaslanır.
        "surum": glossary.kitap_surumu(slug),
    }
    if bolum is not None:
        # "Bu bölümde geçenler" süzgeci. null = bölümün kaynağı yok (bilinmiyor).
        kaynak = cache.bolum_kaynagi(bolum)
        veri["bolumde"] = (
            None if kaynak is None
            else translate_mod.metinde_gecen_terimler(veri["terms"], kaynak)
        )
    return veri


def _surum_cakismasi(exc: glossary.SurumCakismasi) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "message": (
                "Bu terim başka bir cihazda değişti"
                if exc.guncel else "Bu terim başka bir cihazda silindi"
            ),
            "error_class": "SurumCakismasi",
            "guncel": exc.guncel,
        },
    )


@app.post("/api/book/{slug}/glossary")
def set_book_glossary(slug: str, term: GlossaryTerm) -> dict:
    # Karşılık + koşul TEK işlemde yazılır: iki ayrı yazım iki sürüm artışı ve
    # arada yarım bir kayıt demekti. KOŞUL yalnız ALANI GÖNDERİLDİĞİNDE yazılır —
    # okuyucunun çevrimdışı kuyruğu çoğu zaman {source, target} gönderiyor.
    try:
        kayit = glossary.terimi_yaz(
            slug, term.source, term.target,
            kosul=glossary.KORU if term.kosul is None else term.kosul,
            taban_surum=term.taban_surum,
        )
    except glossary.SurumCakismasi as exc:
        raise _surum_cakismasi(exc) from exc
    if term.ornek is not None:
        glossary.ornek_doldur(slug, term.source, term.ornek.kaynak_cumle, term.ornek.bolum)
    return {
        "terms": glossary.get_glossary(slug),
        "kosullar": glossary.get_kosullar(slug),
        # İstemci bir sonraki düzenlemenin tabanını buradan alır.
        "kayit": kayit,
    }


@app.delete("/api/book/{slug}/glossary")
def delete_book_glossary(
    slug: str, source: str = Query(...), taban_surum: int | None = Query(None)
) -> dict:
    # `silinen` GERİ ALMA içindir: okuyucu onu içe aktarma ucuyla (dosya
    # stratejisi) geri yazar; koşul, köken ve kimlik kaybolmaz. Terim yoksa null.
    try:
        silinen = glossary.delete_term(slug, source, taban_surum=taban_surum)
    except glossary.SurumCakismasi as exc:
        raise _surum_cakismasi(exc) from exc
    return {"terms": glossary.get_glossary(slug), "silinen": silinen}


@app.get("/api/book/{slug}/glossary/history")
def book_glossary_history(slug: str, source: str = Query(...)) -> dict:
    """Bir terimin değişiklik geçmişi (yeniden eskiye): kim, ne zaman, neyi neye."""
    return {"gecmis": glossary.gecmis(library.resolve_slug(slug), source)}


@app.post("/api/book/{slug}/glossary/suggest")
def suggest_book_glossary(slug: str, req: GlossarySuggestRequest) -> dict:
    """Okurken seçilen özel ad için karşılık öner (kaydetmez, yalnız önerir).

    Otomatik algılamayla AYNI kural: karakter adı İngilizce kalır, başka her özel ad
    Türkçe karşılığıyla girer. Kaydı kullanıcı onaylar — öneri yanlışsa sözlüğe
    yanlış bir KURAL yazılmış olurdu (model sözlüğü birebir uygular).
    """
    try:
        return suggest_term(req.source, req.context or "", API_KEY)
    except TranslateError as exc:
        raise _pipeline_http_error(exc) from exc


@app.get("/api/book/{slug}/glossary/export")
def export_book_glossary(slug: str) -> Response:
    """Sözlüğü JSON olarak indir (yedek + masaüstünde toplu düzenleme).

    Sözlük tek bir PC'deki tek bir SQLite dosyasında yaşıyor; yedeği yoktu ve
    telefon arayüzünde 267 satırı elden geçirmek pratik değil.
    """
    canonical = library.resolve_slug(slug)
    # TAM kayıt: koşullar ve köken olmadan boş bir veritabanına geri yüklenen
    # "yedek" sözlüğü geri getirmiyordu (bkz. glossary.disa_aktar).
    govde = json.dumps(glossary.disa_aktar(canonical), ensure_ascii=False, indent=2)
    return Response(
        content=govde,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="sozluk-{canonical}.json"'
        },
    )


@app.post("/api/book/{slug}/glossary/import")
def import_book_glossary(slug: str, req: GlossaryImportRequest) -> dict:
    """Dosyadan gelen terimleri birleştir.

    Varsayılan strateji "mevcut": kullanıcının hâlihazırdaki kaydı EZİLMEZ, yalnız
    eksikler eklenir (`merge_terms`, INSERT OR IGNORE). "dosya" stratejisi bilerek
    üzerine yazar — masaüstünde toplu düzeltme yapıp geri yüklemenin yolu budur.
    """
    canonical = library.resolve_slug(slug)
    if req.strateji not in glossary.IMPORT_STRATEJILERI:
        raise HTTPException(status_code=400, detail="Bilinmeyen strateji.")
    if req.kayitlar is not None:
        sonuc = glossary.ice_aktar(canonical, req.kayitlar, req.strateji)
        return {**sonuc, "terms": glossary.get_glossary(canonical)}
    if req.terms is None:
        raise HTTPException(status_code=400, detail="Dosyada ne 'kayitlar' ne 'terms' var.")
    gelen = {k: v for k, v in req.terms.items() if (k or "").strip()}
    if req.strateji == "dosya":
        for kaynak, hedef in gelen.items():
            glossary.set_term(canonical, kaynak, hedef, "import")
        eklenen = len(gelen)
    else:
        eklenen = len(glossary.merge_terms(canonical, gelen, "import"))
    return {
        "eklenen": eklenen,
        "gelen": len(gelen),
        "terms": glossary.get_glossary(canonical),
    }


@app.get("/api/book/{slug}/glossary/impact")
def book_glossary_impact(slug: str, source: str = Query(...)) -> dict:
    """Bu terim ÇEVRİLMİŞ kaç bölümde geçiyor (kaynak metne göre)?

    Sözlük ipucu "eski bölüm için Yeniden çevir" diyordu ama hangileri olduğunu
    söylemiyordu. `kapsama` alanı kaynak metni olan bölüm oranını taşır —
    kapsama düşükken "0 bölüm" yanıltıcı okunmasın.
    """
    return pipeline.terim_etkisi(library.resolve_slug(slug), source)


@app.post("/api/book/{slug}/retranslate")
def start_retranslate(slug: str, req: RetranslateRequest) -> dict:
    """Seçili bölümleri arka planda yeniden çevir (sözlük düzeltmesi eski bölümlere).

    Yalnız bu kitabın ÇEVRİLMİŞ bölümleri kabul edilir: adı "yeniden çevir" olan
    bir uç, hiç çevrilmemiş bir bölümü ya da başka kitabın bölümünü sessizce
    çevirmemeli (ücretli model seçiliyken para). İlerleme `/api/bulk/{job_id}`ten
    okunur; her bölümün sonucu işin `params.sonuclar` alanındadır.
    """
    canonical = library.resolve_slug(slug)
    urls = list(dict.fromkeys(u for u in req.urls if u))
    if not urls or len(urls) > 500:
        raise HTTPException(status_code=400, detail="1-500 arası bölüm seçilmeli.")
    cevrili = {c["url"] for c in cache.list_chapters(canonical) if c["translated"]}
    yabanci = [u for u in urls if u not in cevrili]
    if yabanci:
        raise HTTPException(
            status_code=400,
            detail=f"Bu kitabın çevrilmiş bölümü olmayan {len(yabanci)} adres var.",
        )
    return {"job_id": jobs.start_retranslate(canonical, urls, API_KEY)}


class ArsivGeriRequest(BaseModel):
    url: str
    id: int


@app.get("/api/chapter/arsiv")
def chapter_archive(url: str = Query(...)) -> dict:
    """Bölümün arşivlenmiş (eski) çevirileri: model, sözlük sürümü, zaman, uyum."""
    return {"arsiv": cache.arsiv_listesi(url)}


@app.post("/api/chapter/arsiv/geri")
def chapter_archive_restore(req: ArsivGeriRequest) -> dict:
    """Arşivdeki çeviriye dön. Şu anki çeviri de arşive düşer (geri alma geri alınabilir).

    Yanıt `ceviri_zamani` taşır: okuyucu telefondaki kopyayı tazelemesi gerektiğini
    buradan bilir."""
    if not cache.arsivden_geri_yukle(req.url, req.id):
        raise HTTPException(status_code=404, detail="Arşiv kaydı bulunamadı.")
    bolum = cache.get_chapter(req.url) or {}
    return {"ok": True, "ceviri_zamani": bolum.get("ceviri_zamani")}


@app.get("/api/settings/model")
def get_ceviri_modeli() -> dict:
    """Seçili çeviri modeli + seçenekler (etiket ve ölçüm notlarıyla).

    Seçenekleri SUNUCU veriyor, okuyucu sabit bir liste taşımıyor: iki yerde
    yazılsalardı bir model eklendiğinde okuyucu güncellenmeyi unutulabilir ve
    sunucunun tanımadığı bir ad gönderilirdi (sessizce yok sayılırdı).
    """
    return {
        "secili": settings.get(translate_mod.MODEL_AYAR_ANAHTARI,
                               translate_mod.VARSAYILAN_MODEL),
        "secenekler": list(translate_mod.SECILEBILIR_MODELLER),
        # Harcama GOSTERGESI (fren degil, kullanici karari): ucretli model elle
        # seciliyor ve ucretli halkaya sessizce dusulmuyor, yani surpriz harcamanin
        # kaynagi zaten kapali. Ayni istekte donuyor cunku okuyucu ikisini de ayni
        # panelde gosteriyor - ikinci bir fetch bos yere gecikme olurdu.
        "harcama": kullanim.ozet(),
    }


@app.post("/api/settings/model")
def set_ceviri_modeli(req: CeviriModeliRequest) -> dict:
    """Çeviri modelini seç. YALNIZ yeni çevrilen bölümlerde geçerlidir (sözlük ve
    önbellekteki bölümler yeniden çevrilmedikçe değişmez.

    Tanınmayan ad REDDEDİLİR: sessizce yok saymak, kullanıcıya "seçtim" dedirtip
    hiçbir şey değiştirmezdi. Seçim zincirin başına geçer, yerini almaz — tercih
    edilen model çeviremezse okuma alt halkalardan sürer.
    """
    if req.model not in translate_mod.SECILEBILIR_ADLAR:
        raise HTTPException(status_code=400, detail="Bilinmeyen model.")
    settings.set(translate_mod.MODEL_AYAR_ANAHTARI, req.model)
    return {"secili": req.model, "zincir": list(translate_mod.zincir_kur(req.model))}


@app.get("/api/book/{slug}/epub")
def book_epub(
    slug: str,
    start: int = Query(1, ge=1),
    count: int = Query(1000, ge=1, le=2000),
) -> Response:
    """Çevrilmiş bölümlerden ePub üret ve indir."""
    filename, data = epub_export.build_epub(slug, start=start, count=count)
    if not data:
        raise HTTPException(status_code=404, detail="Bu aralıkta çevrilmiş bölüm yok.")
    return Response(
        content=data,
        media_type="application/epub+zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Kabuk bayatlaması koruması: statik dosyalar Cache-Control olmadan servis
# edilince tarayıcı sezgisel önbelliyor; telefon eski app.js/sw.js'i günlerce
# tutabiliyor. no-cache = her istekte ETag ile doğrula (LAN'da ucuz 304),
# sw.js dahil — SW güncellemesi de böylece asla bayat kopyaya takılmaz.
@app.middleware("http")
async def no_cache_static(request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


# PWA statik dosyaları kökten servis et (API rotalarından SONRA mount edilir).
app.mount("/", StaticFiles(directory=str(APP_DIR / "web"), html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
