"""EPUB/PDF dosyalarından kitap içe aktarımı — bölümleri sahneli (raw_source) yazar.

Çıkarılan bölümler `epub://`/`pdf://` şemalı sahneli satır olur (translation NULL,
raw_source dolu, E-18); okuma/bulk pipeline raw_source-öncelikli routing ile web'e
inmeden çevirir. İçe aktarım ÇEVİRMEZ, yalnız sahneler — çeviri ON-DEMAND (okunan
bölüm) ya da TOPLU ÇEVİR ile yapılır. Böylece tek dosya günlük Gemini kotasını sessizce
yutmaz (planın "kota kapısı" davranışı: örnek bölüm okununca beğenilirse kalanı sıraya).

E-13 hijyeni: geçici yükleme dosyası iş sonunda silinir; boş slugify → <prefix>-<rastgele6>.
"""
from __future__ import annotations

import os
import tempfile

from . import library, synthetic

MAX_CHAPTERS = 5000  # akıl-sağlığı üst sınırı (tek dosyadan sınırsız satır üretmeyelim)
_MIN_CHARS = 20  # bundan kısa "bölümler" (kapak, nav, boş sayfa) atlanır


class BookImportError(Exception):
    """İçe aktarım başarısız: bozuk/desteklenmeyen dosya ya da çevrilebilir bölüm yok."""


def _epub_chapters(path: str) -> tuple[str, list[tuple[str, str]]]:
    """EPUB'ı spine (okuma) sırasında gez; her doküman = bölüm. (kitap_başlığı, [(başlık, metin)])."""
    from bs4 import BeautifulSoup
    from ebooklib import ITEM_DOCUMENT, epub

    book = epub.read_epub(path)
    md = book.get_metadata("DC", "title")
    book_title = ((md[0][0] if md and md[0] else "") or "").strip() or "İçe Aktarılan Kitap"

    chapters: list[tuple[str, str]] = []
    seen: set[str] = set()
    for spine_id, _linear in book.spine:
        item = book.get_item_with_id(spine_id)
        if item is None or item.get_type() != ITEM_DOCUMENT or item.id in seen:
            continue
        # EPUB3 nav (içindekiler) dokümanı da ITEM_DOCUMENT'tir → bölüm sayma (atla).
        # Sınıf (EpubNav) VEYA manifest 'nav' özelliği ile yakala (üreticiye göre değişir).
        if isinstance(item, epub.EpubNav) or "nav" in (getattr(item, "properties", None) or []):
            continue
        seen.add(item.id)
        soup = BeautifulSoup(item.get_content(), "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        # Paragraf sınırlarını KORU (translate \n\n'e böler, iki-dilli hizalama buna dayanır).
        ps = soup.find_all("p")
        if ps:
            paras = [p.get_text(" ", strip=True) for p in ps]
        else:  # <p> yoksa satır bazında böl
            paras = [ln.strip() for ln in soup.get_text("\n").split("\n") if ln.strip()]
        text = "\n\n".join(t for t in paras if t)
        if len(text.strip()) < _MIN_CHARS:
            continue  # kapak/nav/boş → atla
        h = soup.find(["h1", "h2", "h3"])
        title = (h.get_text(" ", strip=True) if h else "").strip()
        chapters.append((title, text))
    return book_title, chapters


def import_epub(data: bytes, filename: str = "") -> dict:
    """EPUB baytlarını sahneli kitaba çevir. Döner: {slug, title, chapter_count, first_url}."""
    fd, path = tempfile.mkstemp(suffix=".epub")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        try:
            book_title, chapters = _epub_chapters(path)
        except Exception as exc:  # bozuk/desteklenmeyen dosya
            raise BookImportError(f"EPUB okunamadı: {exc}") from exc
    finally:
        try:
            os.remove(path)  # E-13: geçici dosya silinir
        except OSError:
            pass
    return _stage_book(book_title, chapters, "epub", "epub://")


def import_pdf(data: bytes, pages_per_chapter: int = 10, filename: str = "") -> dict:
    """PDF baytlarını sahneli kitaba çevir (PyMuPDF ile metin; N sayfa = 1 bölüm)."""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise BookImportError(
            "PDF içe aktarımı için PyMuPDF kurulu değil (pip install PyMuPDF)."
        ) from exc
    n = max(1, int(pages_per_chapter or 10))
    book_title = (os.path.splitext(os.path.basename(filename or ""))[0] or "").strip() or "İçe Aktarılan PDF"
    chapters: list[tuple[str, str]] = []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise BookImportError(f"PDF okunamadı: {exc}") from exc
    try:
        page_texts = [doc.load_page(i).get_text("text") for i in range(doc.page_count)]
    finally:
        doc.close()
    for start in range(0, len(page_texts), n):
        block = "\n\n".join(t.strip() for t in page_texts[start : start + n] if t.strip())
        # PDF metninde tek satır sonları paragraf değildir; çift satır sonu = paragraf.
        block = "\n\n".join(seg.strip() for seg in block.split("\n\n") if seg.strip())
        if len(block.strip()) < _MIN_CHARS:
            continue
        chapters.append(("", block))
    return _stage_book(book_title, chapters, "pdf", "pdf://")


def _stage_book(book_title: str, chapters: list[tuple[str, str]], prefix: str, scheme: str) -> dict:
    if not chapters:
        raise BookImportError("Dosyada çevrilebilir bölüm bulunamadı.")
    if len(chapters) > MAX_CHAPTERS:
        chapters = chapters[:MAX_CHAPTERS]
    slug = synthetic.allocate_slug(book_title, prefix)
    first_url = synthetic.chapter_url(slug, 1, scheme)
    first_title = chapters[0][0] or "Bölüm 1"
    # Kitabı rafa yaz (slug'ı rezerve eder) + konum bölüm 1.
    library.upsert_book(slug, book_title, first_url, first_title, 1)
    for i, (title, text) in enumerate(chapters, start=1):
        synthetic.append_chapter(
            slug, book_title, title or f"Bölüm {i}", text, chapter_no=i, scheme=scheme
        )
    return {
        "slug": slug,
        "title": book_title,
        "chapter_count": len(chapters),
        "first_url": first_url,
    }
