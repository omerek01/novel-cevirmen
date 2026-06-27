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

from core import cache, epub_export, glossary, library  # noqa: E402
from core.fetch import FetchError, fetch_chapter  # noqa: E402
from core.translate import TranslateError, translate_chapter  # noqa: E402

load_dotenv(APP_DIR.parent / ".env")  # tek kaynak: novel-cevirmen/.env
API_KEY = os.getenv("GEMINI_API_KEY")

app = FastAPI(title="novel-cevirmen")

# Eski (sadece-önbellek) kurulumlardaki kitapları paylaşılan kütüphaneye taşı.
library.backfill_from_cache()


@app.get("/api/chapter")
def get_chapter(
    url: str = Query(..., description="novelbin bölüm URL'i"),
    refresh: bool = Query(False, description="Önbelleği yok say, yeniden çevir"),
) -> dict:
    """Bölümü çek + Türkçe'ye çevir. Önbellekte varsa anında döner.

    (Sync def: Playwright thread havuzunda çalışır.)
    """
    if not refresh:
        cached = cache.get_chapter(url)
        if cached is not None:
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

    if not API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY ayarlı değil.")
    try:
        chapter = fetch_chapter(url)
    except FetchError as exc:
        raise HTTPException(status_code=502, detail=f"Çekme hatası: {exc}")

    # Birleştirilmiş kitap: slug'ı kanonikleştir, böylece bölüm/sözlük tek kitapta toplanır.
    book_slug = library.resolve_slug(chapter["book_slug"])
    book_title = chapter["book_title"]
    if book_slug != chapter["book_slug"]:
        merged = library.get_book(book_slug)
        if merged and merged.get("title"):
            book_title = merged["title"]

    book_glossary = glossary.get_glossary(book_slug)
    try:
        result = translate_chapter(chapter["text"], api_key=API_KEY, glossary=book_glossary)
    except TranslateError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    payload = {
        "title": chapter["title"],
        "translation": result["translation"],
        "detected_names": result["detected_names"],
        "chunk_count": result["chunk_count"],
        "next_url": chapter["next_url"],
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


@app.post("/api/book/{slug}/merge-into")
def merge_book(slug: str, req: MergeRequest) -> dict:
    """`slug` kitabını `target` kitabıyla birleştir (aynı kitap, farklı slug)."""
    canonical = library.merge_books(slug, req.target)
    return {"ok": True, "canonical": canonical}


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
