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

from . import library, media, synthetic

MAX_CHAPTERS = 5000  # akıl-sağlığı üst sınırı (tek dosyadan sınırsız satır üretmeyelim)
_MIN_CHARS = 20  # bundan kısa "bölümler" (kapak, nav, boş sayfa) atlanır


class BookImportError(Exception):
    """İçe aktarım başarısız: bozuk/desteklenmeyen dosya ya da çevrilebilir bölüm yok."""


def _epub_html_docs(path: str) -> tuple[str, list[tuple[str, str, list[str]]]]:
    """EPUB'ı spine sırasında gez; her doküman = bölüm HTML'i (resimler korunur).

    Döner: (kitap_başlığı, [(bölüm_başlığı, gövde_html, [resim_basename...])]).
    <img> src'leri BASENAME'e indirgenir (media rewrite import_epub'da yapılır)."""
    from bs4 import BeautifulSoup
    from ebooklib import ITEM_DOCUMENT, epub

    book = epub.read_epub(path)
    md = book.get_metadata("DC", "title")
    book_title = ((md[0][0] if md and md[0] else "") or "").strip() or "İçe Aktarılan Kitap"

    docs: list[tuple[str, str, list[str]]] = []
    seen: set[str] = set()
    for spine_id, _linear in book.spine:
        item = book.get_item_with_id(spine_id)
        if item is None or item.get_type() != ITEM_DOCUMENT or item.id in seen:
            continue
        if isinstance(item, epub.EpubNav) or "nav" in (getattr(item, "properties", None) or []):
            continue  # EPUB3 içindekiler dokümanı → atla
        seen.add(item.id)
        soup = BeautifulSoup(item.get_content(), "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        body = soup.body or soup
        imgs: list[str] = []
        for img in body.find_all("img"):
            src = (img.get("src") or "").split("?")[0]
            base = os.path.basename(src)
            if base:
                imgs.append(base)
                img["src"] = "@@IMG@@" + base  # media rewrite'ta değiştirilecek yer tutucu
            else:
                img.decompose()
        text = body.get_text(strip=True)
        if len(text) < _MIN_CHARS and not imgs:
            continue  # kapak/nav/boş → atla
        h = body.find(["h1", "h2", "h3"])
        title = (h.get_text(" ", strip=True) if h else "").strip()
        html = "".join(str(c) for c in body.contents)
        docs.append((title, html, imgs))
    return book_title, docs


def _epub_images(path: str) -> dict[str, bytes]:
    """EPUB'ın gömülü resimlerini basename→bayt olarak indeksle."""
    from ebooklib import ITEM_IMAGE, epub

    book = epub.read_epub(path)
    out: dict[str, bytes] = {}
    for item in book.get_items_of_type(ITEM_IMAGE):
        out[os.path.basename(item.get_name())] = item.get_content()
    return out


def import_epub(data: bytes, filename: str = "") -> dict:
    """EPUB'ı yerinde-HTML modunda içe aktar: gömülü resimler media'ya çıkarılır,
    her doküman = bölüm (content_type="html", raw_source = resim-src'leri /media'ya
    yeniden yazılmış gövde HTML'i). Çeviri OKUNUNCA yapılır (translate_epub_html:
    blok metinleri yerinde Türkçe, resimler/yapı korunur)."""
    fd, path = tempfile.mkstemp(suffix=".epub")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        try:
            book_title, docs = _epub_html_docs(path)
            images = _epub_images(path)
        except Exception as exc:
            raise BookImportError(f"EPUB okunamadı: {exc}") from exc
    finally:
        try:
            os.remove(path)  # E-13: geçici dosya silinir
        except OSError:
            pass
    if not docs:
        raise BookImportError("EPUB'da çevrilebilir bölüm bulunamadı.")
    if len(docs) > MAX_CHAPTERS:
        docs = docs[:MAX_CHAPTERS]

    slug = synthetic.allocate_slug(book_title, "epub")
    # Kullanılan resimleri media'ya yaz; basename → /media/<slug>/<name> eşlemesi.
    used = {b for _, _, imgs in docs for b in imgs}
    img_url = {}
    for base in used:
        if base in images:
            rel = media.write_bytes(slug, base, images[base])
            img_url[base] = "/media/" + rel
    first_url = synthetic.chapter_url(slug, 1, "epub://")
    library.upsert_book(slug, book_title, first_url, docs[0][0] or "Bölüm 1", 1)
    for i, (title, html, _imgs) in enumerate(docs, start=1):
        # Yer tutucuları gerçek /media URL'leriyle değiştir (bulunmayan resim boşalır).
        for base in _imgs:
            html = html.replace("@@IMG@@" + base, img_url.get(base, ""))
        synthetic.append_chapter(
            slug, book_title, title or f"Bölüm {i}", html,
            chapter_no=i, scheme="epub://", content_type="html",
        )
    return {"slug": slug, "title": book_title, "chapter_count": len(docs), "first_url": first_url}


def import_pdf(data: bytes, pages_per_chapter: int = 1, filename: str = "") -> dict:
    """PDF'i sayfa görsel modunda içe aktar: kaynak PDF saklanır, HER SAYFA = 1 bölüm.

    Sayfalar `pdf://slug/N` şemalı, content_type="html" sahneli satır olur. Çeviri
    YAPILMAZ — bir sayfa OKUNUNCA (on-demand) metni yerinde Türkçe'yle değiştirilip
    sayfa PNG render edilir (import_translate). raw_source = sayfa metni (yalnız
    referans/arama; render kaynak PDF'ten yapılır)."""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise BookImportError(
            "PDF içe aktarımı için PyMuPDF kurulu değil (pip install PyMuPDF)."
        ) from exc
    book_title = (os.path.splitext(os.path.basename(filename or ""))[0] or "").strip() or "İçe Aktarılan PDF"
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise BookImportError(f"PDF okunamadı: {exc}") from exc
    try:
        n = doc.page_count
        page_texts = [doc.load_page(i).get_text("text") for i in range(min(n, MAX_CHAPTERS))]
    finally:
        doc.close()
    if n == 0:
        raise BookImportError("PDF'de sayfa yok.")

    slug = synthetic.allocate_slug(book_title, "pdf")
    media.write_bytes(slug, "source.pdf", data)  # render için kaynak saklanır
    first_url = synthetic.chapter_url(slug, 1, "pdf://")
    library.upsert_book(slug, book_title, first_url, "Sayfa 1", 1)
    for i, txt in enumerate(page_texts, start=1):
        synthetic.append_chapter(
            slug, book_title, f"Sayfa {i}", txt.strip() or "(resim sayfası)",
            chapter_no=i, scheme="pdf://", content_type="html",
        )
    return {
        "slug": slug,
        "title": book_title,
        "chapter_count": len(page_texts),
        "first_url": first_url,
    }
