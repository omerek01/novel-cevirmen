"""novel-cevirmen backend — FastAPI.

Çalıştırma (proje kökünden):
    .venv\\Scripts\\python.exe app\\server.py
Telefondan erişim: http://<PC-LAN-IP>:8000  (aynı Wi-Fi)
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))  # 'core' paketini CWD'den bağımsız import et

import os  # noqa: E402

from dotenv import load_dotenv  # noqa: E402
from fastapi import FastAPI, HTTPException, Query, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from pydantic import BaseModel  # noqa: E402

from core import cache, epub_export, glossary, jobs, library, pipeline  # noqa: E402
from core.fetch import FetchError, CloudflareChallenge  # noqa: E402
from core.translate import TranslateError  # noqa: E402

load_dotenv(APP_DIR.parent / ".env")  # tek kaynak: novel-cevirmen/.env
API_KEY = os.getenv("GEMINI_API_KEY")

app = FastAPI(title="novel-cevirmen")

# Eski (sadece-önbellek) kurulumlardaki kitapları paylaşılan kütüphaneye taşı.
library.backfill_from_cache()


@app.get("/api/chapter")
def get_chapter(
    url: str = Query(..., description="novelbin bölüm URL'i"),
    refresh: bool = Query(False, description="Önbelleği yok say, yeniden çevir"),
    source: bool = Query(False, description="İki-dilli: hizalı İngilizce kaynağı da getir"),
) -> dict:
    """Bölümü çek + Türkçe'ye çevir. Önbellekte varsa anında döner.

    source=1: yanıtta paragraf-hizalı İngilizce kaynak (`source`) da gelir; eski bölümde
    yoksa bir kez yeniden çevrilerek eklenir. (Sync def: Playwright thread havuzunda.)
    """
    try:
        return pipeline.get_or_translate(url, API_KEY, refresh, want_source=source)
    except CloudflareChallenge as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "error_class": "CloudflareChallenge"
            }
        )
    except FetchError as exc:
        from core.fetch import CF_ORIGIN_ERRORS
        error_class = "FetchError"
        if any(f"HTTP {err}" in str(exc) for err in CF_ORIGIN_ERRORS):
            error_class = "OriginError"
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "error_class": error_class
            }
        )
    except TranslateError as exc:
        if not API_KEY:
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY ayarlı değil.")
        raise HTTPException(
            status_code=503,
            detail={
                "message": str(exc),
                "error_class": "TranslateError"
            }
        )


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


@app.post("/api/book/{slug}/merge-into")
def merge_book(slug: str, req: MergeRequest) -> dict:
    """`slug` kitabını `target` kitabıyla birleştir (aynı kitap, farklı slug)."""
    canonical = library.merge_books(slug, req.target)
    return {"ok": True, "canonical": canonical}


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


# PWA statik dosyaları kökten servis et (API rotalarından SONRA mount edilir).
app.mount("/", StaticFiles(directory=str(APP_DIR / "web"), html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
