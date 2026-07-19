"""İçe aktarılan sayfaları OKUDUKÇA çevir+render et (on-demand, kota-güvenli).

PDF: kaynak PDF'in sayfasını aç → metin bloklarını bbox'larıyla çıkar → hizalı
(``[[n]]`` işaretçili) Türkçe çeviri (translate_chapter'ı yeniden kullanır) → orijinal
yazıyı redaction ile sil, aynı bbox'a Türkçe'yi yaz (font kutuya sığana dek küçülür) →
sayfayı PNG render et → media'ya kaydet. Bölümün "translation"ı, PNG'yi gösteren
``<img>`` HTML'i olur (content_type="html"). Resimler/düzen korunur.

Çeviri okuyucu bölümü açınca yapılır; sayfa metni yoksa (saf resim) orijinal render edilir.
"""
from __future__ import annotations

import html as _html
import os

from . import media, translate

RENDER_DPI = 150  # sayfa görsel çözünürlüğü (kalite/boyut dengesi)
_MIN_FONT = 5.0

_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\ARIAL.TTF",
    r"C:\Windows\Fonts\calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
]


def _tr_font() -> str | None:
    """Türkçe glif destekli bir TTF yolu (yoksa None → PDF'in gömülü 'helv'i)."""
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def _insert_flow(page, rect, text, fontfile, fontname, size=11.0):
    """Metni rect'e yerleştir (rect ALTA kadar uzun tutulur); KULLANILAN yüksekliği döndür.

    Türkçe İngilizce'den uzun → sabit kutuya sığdırıp taşırmak yerine, blok gerektiği
    kadar satır kullanır ve bir sonraki blok bunun ALTINDAN başlar (üst üste binme yok).
    insert_textbox pozitif artan boşluk döndürür → used = rect.height - artan. Sayfa
    sonuna sığmazsa font küçültülür."""
    while size >= _MIN_FONT:
        leftover = page.insert_textbox(rect, text, fontfile=fontfile, fontname=fontname, fontsize=size)
        if leftover >= 0:
            return rect.height - leftover  # kullanılan dikey yükseklik
        size -= 0.5
    page.insert_textbox(rect, text, fontfile=fontfile, fontname=fontname, fontsize=_MIN_FONT)
    return rect.height  # sığmadı → tüm alanı kullandı say (nadir, çok yoğun sayfa)


def translate_pdf_page(slug: str, page_no: int, api_key: str) -> str:
    """slug kitabının page_no sayfasını çevirip render et → media-göreli PNG yolu için <img> HTML."""
    import fitz

    src = media.book_dir(slug) / "source.pdf"
    if not src.is_file():
        raise translate.TranslateError("Kaynak PDF bulunamadı (yeniden içe aktarın).")
    doc = fitz.open(str(src))
    try:
        if page_no < 1 or page_no > doc.page_count:
            raise translate.TranslateError("Sayfa aralık dışı.")
        page = doc.load_page(page_no - 1)
        texts, bboxes = [], []
        for b in page.get_text("dict")["blocks"]:
            if b.get("type", 1) != 0:  # yalnız metin blokları (resimler dokunulmaz)
                continue
            txt = " ".join(s["text"] for ln in b["lines"] for s in ln["spans"]).strip()
            if txt:
                texts.append(txt)
                bboxes.append(fitz.Rect(b["bbox"]))

        if texts:
            joined = "\n\n".join(texts)
            result = translate.translate_chapter(joined, api_key=api_key)
            tr_blocks = [t.strip() for t in (result["translation"] or "").split("\n\n")]
            fontfile = _tr_font()
            fontname = "trf" if fontfile else "helv"
            # 1) orijinal metni sil (redaction). Resimler/çizimler metin bbox'ları
            #    dışında kaldığından korunur.
            for bbox in bboxes:
                page.add_redact_annot(bbox)
            page.apply_redactions()
            # 2) Türkçe'yi yaz — DİKEY AKIŞ (Y-takibi): her blok bir öncekinin altından
            #    başlar, orijinal X (sütun) konumu korunur → uzun Türkçe üst üste binmez.
            page_bottom = page.rect.height - 12
            if len(tr_blocks) == len(texts):
                order = sorted(range(len(bboxes)), key=lambda i: (round(bboxes[i].y0, 1), bboxes[i].x0))
                cursor = 0.0
                for i in order:
                    tr = tr_blocks[i]
                    if not tr:
                        continue
                    bbox = bboxes[i]
                    top = max(bbox.y0, cursor)
                    if top >= page_bottom:
                        break  # sayfa doldu (nadir; çok yoğun sayfa)
                    rect = fitz.Rect(bbox.x0, top, bbox.x1, page_bottom)
                    used = _insert_flow(page, rect, tr, fontfile, fontname)
                    cursor = top + used + 4  # sonraki blok bunun altından
            else:
                area = fitz.Rect(
                    min(b.x0 for b in bboxes), min(b.y0 for b in bboxes),
                    max(b.x1 for b in bboxes), page_bottom,
                )
                _insert_flow(page, area, result["translation"] or "", fontfile, fontname)

        pixmap = page.get_pixmap(dpi=RENDER_DPI)
        png = pixmap.tobytes("png")
        w, h = pixmap.width, pixmap.height
    finally:
        doc.close()
    rel = media.write_bytes(slug, f"page-{page_no}.png", png)
    return page_image_html(rel, page_no, w, h)


def page_image_html(media_rel: str, page_no: int, w: int | None = None, h: int | None = None) -> str:
    """Sayfa PNG'sini gösteren güvenli <img> HTML'i (okuyucu innerHTML olarak basar).

    width/height verilir → tarayıcı görselin yerini yüklemeden ÖNCE (en-boy oranıyla)
    ayırır. Kritik: sonsuz kaydırma sentinel geometrisi doğru olur, kısa PDF sayfalarında
    akış takılmaz (aksi halde lazy görsel 0 yükseklikte → sentinel kaymaz)."""
    dims = f' width="{w}" height="{h}"' if w and h else ""
    return (
        f'<img class="page-img" src="/media/{_html.escape(media_rel, quote=True)}"{dims} '
        f'alt="Sayfa {page_no}" loading="lazy">'
    )


# EPUB HTML'i okuyucuya innerHTML olarak basılır → temizlenmeli (yerinde çeviri).
_ALLOWED_TAGS = {
    "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "em", "i", "strong", "b",
    "u", "blockquote", "ul", "ol", "li", "figure", "figcaption", "img", "span",
    "div", "sup", "sub", "small", "table", "thead", "tbody", "tr", "td", "th",
}
_ALLOWED_ATTRS = {"src", "alt", "class", "width", "height"}  # href/style/on* dışarıda


def _sanitize(soup) -> None:
    """script/style/iframe ve on*/javascript: gibi tehlikeli her şeyi ayıkla (in-place)."""
    for tag in soup(["script", "style", "iframe", "object", "embed", "link", "meta", "head"]):
        tag.decompose()
    for tag in list(soup.find_all(True)):
        if tag.name not in _ALLOWED_TAGS:
            tag.unwrap()  # etiketi kaldır, içeriğini bırak
            continue
        for attr in list(tag.attrs):
            if attr not in _ALLOWED_ATTRS:
                del tag[attr]
        src = tag.get("src", "")
        if tag.name == "img" and not (src.startswith("/media/") or src.startswith("data:image/")):
            del tag["src"]  # yalnız yerel medya / data-uri görselleri


def translate_epub_html(raw_html: str, slug: str, api_key: str) -> str:
    """EPUB bölümünün HTML'ini YERİNDE çevir: blok metinleri Türkçe'yle değiştir,
    resimleri/yapıyı koru, temizlenmiş HTML döndür."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(raw_html or "", "html.parser")
    _sanitize(soup)
    blocks, texts = [], []
    for el in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "figcaption"]):
        t = el.get_text(" ", strip=True)
        if t:
            blocks.append(el)
            texts.append(t)
    if texts:
        result = translate.translate_chapter("\n\n".join(texts), api_key=api_key)
        tr = [t.strip() for t in (result["translation"] or "").split("\n\n")]
        if len(tr) == len(blocks):  # hizalama tuttu → blok-blok değiştir
            for el, t in zip(blocks, tr):
                el.clear()
                el.append(t)
        # hizalama tutmadıysa orijinali bırak (nadir; bozuk göstermekten iyi)
    return str(soup)


# --- Manga: Gemini-vision ile balon OCR + çeviri + görsele geri yazma ---

_MANGA_PROMPT = (
    "Bu bir manga/çizgi roman sayfası. İçindeki TÜM okunabilir metinleri bul: konuşma "
    "balonları, anlatı/düşünce kutuları, önemli tabelalar. Her metin için kutu "
    "koordinatını [ymin,xmin,ymax,xmax] biçiminde 0-1000 aralığında NORMALİZE ver ve "
    "İngilizce'den (veya kaynağı ne ise) akıcı Türkçe'ye çevir. Çeviri kısa ve doğal "
    "olsun (balona sığacak). Ses efektlerini (SFX) ATLA. SADECE şu JSON dizisini "
    'döndür, başka hiçbir şey yazma: '
    '[{"box_2d":[ymin,xmin,ymax,xmax],"text":"orijinal","tr":"türkçe"}]'
)


def _manga_regions(image_bytes: str, api_key: str) -> list[dict]:
    """Gemini-vision: manga sayfasından [{box_2d, text, tr}] döndür (model yedekli)."""
    import json

    from google import genai
    from google.genai import types

    from .translate import DEFAULT_MODELS, SAFETY_SETTINGS, _Retryable, genai_errors

    client = genai.Client(api_key=api_key)
    part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
    last: Exception | None = None
    for model in DEFAULT_MODELS:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[part, _MANGA_PROMPT],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=0.2,
                    safety_settings=SAFETY_SETTINGS,
                ),
            )
        except genai_errors.APIError as exc:
            last = exc
            continue  # kota/erişim → sıradaki model
        raw = (resp.text or "").strip()
        if not raw:
            last = _Retryable()
            continue
        try:
            data = json.loads(raw)
        except Exception:
            m = re.search(r"\[.*\]", raw, re.S)
            data = json.loads(m.group(0)) if m else []
        return [d for d in data if isinstance(d, dict)]
    if last:
        raise translate.TranslateError(f"Manga çeviri hatası: {last}")
    return []


def translate_manga_page(slug: str, page_no: int, api_key: str) -> str:
    """Manga sayfasını çevir: Gemini-vision balon OCR+çeviri → orijinali kapat, Türkçe'yi
    üstüne yaz → PNG render → media'ya kaydet → <img> HTML döndür."""
    from PIL import Image, ImageDraw, ImageFont

    src = media.book_dir(slug) / f"src-{page_no}"
    if not src.is_file():
        raise translate.TranslateError("Manga sayfası bulunamadı (yeniden içe aktarın).")
    img = Image.open(str(src)).convert("RGB")  # PIL formatı içerikten algılar (jpg/png/webp)
    # Gemini'ye PNG olarak gönder
    import io

    buf = io.BytesIO()
    img.save(buf, "PNG")
    regions = _manga_regions(buf.getvalue(), api_key)

    W, H = img.size
    draw = ImageDraw.Draw(img)
    fontfile = _tr_font()
    for r in regions:
        box = r.get("box_2d") or r.get("bbox")
        tr = (r.get("tr") or r.get("translation") or "").strip()
        if not box or len(box) != 4 or not tr:
            continue
        ymin, xmin, ymax, xmax = box
        x0, y0 = xmin / 1000 * W, ymin / 1000 * H
        x1, y1 = xmax / 1000 * W, ymax / 1000 * H
        if x1 <= x0 or y1 <= y0:
            continue
        _draw_translated_bubble(draw, (x0, y0, x1, y1), tr, fontfile)

    out = io.BytesIO()
    img.save(out, "PNG")
    rel = media.write_bytes(slug, f"page-{page_no}.png", out.getvalue())
    return page_image_html(rel, page_no, W, H)


def _draw_translated_bubble(draw, box, text, fontfile):
    """Balonu beyazla kapat + Türkçe'yi kutuya sığdırarak yaz (satır sar, font küçült)."""
    from PIL import ImageFont

    x0, y0, x1, y1 = box
    draw.rectangle((x0, y0, x1, y1), fill=(255, 255, 255))
    bw, bh = x1 - x0 - 8, y1 - y0 - 6
    size = 22
    while size >= 9:
        font = ImageFont.truetype(fontfile, size) if fontfile else ImageFont.load_default()
        lines, line = [], ""
        for w in text.split():
            t = (line + " " + w).strip()
            if draw.textlength(t, font=font) > bw and line:
                lines.append(line)
                line = w
            else:
                line = t
        if line:
            lines.append(line)
        if len(lines) * (size + 3) <= bh or size == 9:
            break
        size -= 1
    yy = y0 + 3
    for ln in lines:
        draw.text((x0 + 4, yy), ln, fill=(0, 0, 0), font=font)
        yy += size + 3
