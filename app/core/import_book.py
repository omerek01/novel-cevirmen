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
import re
import tempfile

from . import library, media, synthetic

MAX_CHAPTERS = 5000  # akıl-sağlığı üst sınırı (tek dosyadan sınırsız satır üretmeyelim)
_MIN_CHARS = 20  # bundan kısa "bölümler" (kapak, nav, boş sayfa) atlanır


class BookImportError(Exception):
    """İçe aktarım başarısız: bozuk/desteklenmeyen dosya ya da çevrilebilir bölüm yok."""


_IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


def _natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def _row_flatness(im):
    """Her satırın 'düzlüğü' (0 = tekdüze/gutter, yüksek = içerik/kenar). Saf PIL
    (app venv'de numpy YOK): 16-geniş BOX küçültme → satır başına 16 örnek; yatay
    yayılım (max-min) düşükse satır tekdüzedir (boşluk şeridi) → güvenli kesim yeri."""
    from PIL import Image

    small = im.convert("L").resize((16, im.height), Image.BOX)
    px = list(small.getdata())
    return [max(px[i * 16:i * 16 + 16]) - min(px[i * 16:i * 16 + 16]) for i in range(im.height)]


def _expand_tall_pages(images, target=3600, max_h=4600, search=450):
    """Uzun webtoon şeritlerini (>max_h px) ~target px parçalara böl; kesimi en 'düz'
    (gutter/boşluk) satıra hizala → konuşma balonu ortadan bölünmez.

    Neden: asurascans tarzı siteler bölümü ~15000px devasa şeritler olarak verir.
    Motor tam şeridi CPU'da ~26s'de çevirir; ~3700px parçayı ~6-10s'de. Parçalayınca
    içerik OKUYUCUYA AKARAK gelir (her ~7s'de yeni parça) ve ilk içerik çok daha erken
    belirir — toplam süre ~aynı ama algılanan hız 4x. Kısa görsel (CBZ/normal manga
    sayfası) dokunulmadan geçer."""
    import io

    from PIL import Image

    out: list[bytes] = []
    for raw in images:
        try:
            im = Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception:
            out.append(raw)  # açılamıyorsa olduğu gibi bırak
            continue
        w, h = im.size
        if h <= max_h:
            out.append(raw)  # kısa → parçalama yok, orijinal formatı koru
            continue
        flat = _row_flatness(im)
        cuts = [0]
        while h - cuts[-1] > max_h:  # kalan hâlâ uzunsa böl (son parça <= max_h)
            y = cuts[-1] + target
            lo = max(cuts[-1] + 1200, y - search)
            hi = min(h - 1200, y + search)
            cut = min(range(lo, hi), key=lambda r: flat[r]) if hi > lo else min(y, h)
            cuts.append(cut)
        cuts.append(h)
        for a, b in zip(cuts, cuts[1:]):
            if b - a < 300:
                continue  # aşırı ince artık → atla
            buf = io.BytesIO()
            im.crop((0, a, w, b)).save(buf, "JPEG", quality=90)  # hızlı kodlama, OCR'a yeter
            out.append(buf.getvalue())
    return out


def import_manga(data: bytes, filename: str = "") -> dict:
    """Manga'yı içe aktar: CBZ/ZIP (sayfa görselleri) ya da tek görsel. Kaynak sayfalar
    media'ya saklanır, HER SAYFA = 1 bölüm (manga://slug/N, content_type="html").

    Çeviri YAPILMAZ — sayfa OKUNUNCA (on-demand) Gemini-vision ile balon metni okunup
    Türkçe'ye çevrilir, orijinal kapatılıp Türkçe yazılır (import_translate)."""
    import io
    import zipfile

    from PIL import Image

    book_title = (os.path.splitext(os.path.basename(filename or ""))[0] or "").strip() or "İçe Aktarılan Manga"
    images: list[bytes] = []
    if zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = sorted(
                (n for n in z.namelist()
                 if n.lower().endswith(_IMG_EXT) and not n.endswith("/")),
                key=_natural_key,
            )
            images = [z.read(n) for n in names]
    else:  # tek görsel dosyası?
        try:
            Image.open(io.BytesIO(data)).verify()
            images = [data]
        except Exception as exc:
            raise BookImportError("Manga: CBZ/ZIP ya da görsel dosyası bekleniyor.") from exc
    return _stage_manga(book_title, images)


def import_manga_url(url: str) -> dict:
    """Manga bölümünü WEB'den çek (asurascans vb.) → sayfaları sahnele. Çeviri okudukça."""
    from . import manga_fetch

    r = manga_fetch.fetch_manga_chapter(url)
    return _stage_manga(r["title"], r["images"])


def _stage_manga(book_title: str, images: list[bytes]) -> dict:
    """Manga sayfa görsellerini (CBZ ya da web) media'ya + manga:// bölümlere sahnele."""
    if not images:
        raise BookImportError("Manga: sayfa (görsel) bulunamadı.")
    images = _expand_tall_pages(images)  # uzun şeritleri ~3600px parçalara böl (akan çeviri)
    if len(images) > MAX_CHAPTERS:
        images = images[:MAX_CHAPTERS]
    slug = synthetic.allocate_slug(book_title, "manga")
    for i, raw in enumerate(images, start=1):
        media.write_bytes(slug, f"src-{i}", raw)  # kaynak sayfa (PIL içerikten algılar)
    first_url = synthetic.chapter_url(slug, 1, "manga://")
    library.upsert_book(slug, book_title, first_url, "Sayfa 1", 1)
    for i in range(1, len(images) + 1):
        synthetic.append_chapter(
            slug, book_title, f"Sayfa {i}", "(manga sayfası)",
            chapter_no=i, scheme="manga://", content_type="html",
        )
    return {"slug": slug, "title": book_title, "chapter_count": len(images), "first_url": first_url}


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
