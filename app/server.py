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

import mimetypes  # noqa: E402
import os  # noqa: E402

# Windows'ta mimetypes kayıt defterinden okur; .webmanifest tanımsız, .svg yanlış
# kayıtlı olabilir. Yanlış Content-Type → Chrome PWA ikonunu/manifesti reddeder.
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("image/svg+xml", ".svg")

from dotenv import load_dotenv  # noqa: E402
from fastapi import FastAPI, HTTPException, Query, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from pydantic import BaseModel  # noqa: E402

from core import cache, epub_export, glossary, jobs, library, pipeline, reading_log, synthetic  # noqa: E402
from core.synthetic import ImportedChapterMissing  # noqa: E402
from core.fetch import CloudflareChallenge, FetchError, refresh_clearance  # noqa: E402
from core.translate import TranslateError  # noqa: E402

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
        if not API_KEY:
            return HTTPException(500, "GEMINI_API_KEY ayarlı değil.")
        return HTTPException(503, {"message": str(exc), "error_class": "TranslateError"})
    raise exc  # bilinmeyen → olduğu gibi yukarı


@app.get("/api/chapter")
def get_chapter(
    url: str = Query(..., description="novelbin bölüm URL'i"),
    refresh: bool = Query(False, description="Önbelleği yok say, yeniden çevir"),
    source: bool = Query(False, description="İki-dilli: hizalı İngilizce kaynağı da getir"),
    track: bool = Query(True, description="Kitabın 'kaldığın yer' konumu bu bölüme ilerlesin mi"),
) -> dict:
    """Bölümü çek + Türkçe'ye çevir. Önbellekte varsa anında döner.

    source=1: yanıtta paragraf-hizalı İngilizce kaynak (`source`) da gelir; eski bölümde
    yoksa bir kez yeniden çevrilerek eklenir. (Sync def: Playwright thread havuzunda.)

    track=0: sonsuz okumada akışa ÖNDEN eklenen (henüz okunmamış) bölümler için —
    konumu ilerletme; konumu yalnız aktif bölümün position POST'u belirlesin.
    """
    try:
        return pipeline.get_or_translate(
            url, API_KEY, refresh, want_source=source, advance_position=track
        )
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


class GlossaryTerm(BaseModel):
    source: str
    target: str | None = None


class MergeRequest(BaseModel):
    target: str


class PositionRequest(BaseModel):
    url: str
    ratio: float


class BulkRequest(BaseModel):
    start_url: str
    count: int = 10


class ReadingLogRequest(BaseModel):
    day: str  # istemcinin YEREL günü (YYYY-MM-DD) — "bugün" UTC'ye kaymasın
    slug: str
    url: str


class StatusRequest(BaseModel):
    status: str  # okunuyor | beklemede | bitti


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
    """Bölüm-içi okuma oranını (0..1) kaydet (cihazlar arası paylaşılır)."""
    library.set_position(slug, req.url, req.ratio)
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
def get_book_glossary(slug: str) -> dict:
    return {"terms": glossary.get_glossary(slug)}


@app.post("/api/book/{slug}/glossary")
def set_book_glossary(slug: str, term: GlossaryTerm) -> dict:
    glossary.set_term(slug, term.source, term.target)
    return {"terms": glossary.get_glossary(slug)}


@app.delete("/api/book/{slug}/glossary")
def delete_book_glossary(slug: str, source: str = Query(...)) -> dict:
    glossary.delete_term(slug, source)
    return {"terms": glossary.get_glossary(slug)}


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
