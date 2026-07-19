"""EPUB içe aktarım — çevrimdışı (ebooklib ile mini EPUB üretilir, Gemini yok).

Doğrular: spine sırasında her doküman = sahneli bölüm (raw_source dolu, translation
NULL), zincir (next_url) kurulur, kitap rafa yazılır, first_url = epub://slug/1,
slug epub- önekli. API ucu ham gövdeyle çalışır.
"""
import os
import tempfile

import pytest

from core import cache, import_book, library, synthetic


def _make_epub(title, chapters):
    """chapters: [(bölüm_başlığı, paragraf_listesi)] → EPUB baytları."""
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_title(title)
    book.set_language("en")
    items = []
    for i, (ch_title, paras) in enumerate(chapters, start=1):
        c = epub.EpubHtml(title=ch_title, file_name=f"ch{i}.xhtml", lang="en")
        body = f"<h2>{ch_title}</h2>" + "".join(f"<p>{p}</p>" for p in paras)
        c.content = f"<html><body>{body}</body></html>"
        book.add_item(c)
        items.append(c)
    book.toc = tuple(items)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *items]
    fd, path = tempfile.mkstemp(suffix=".epub")
    os.close(fd)
    try:
        epub.write_epub(path, book)
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.remove(path)


def test_epub_import_html_mode():
    data = _make_epub("Kayıp Krallık", [
        ("Chapter 1", ["İlk paragraf metni.", "İkinci paragraf."]),
        ("Chapter 2", ["Üçüncü bölüm paragrafı biraz daha uzun olsun diye yazıldı."]),
        ("Chapter 3", ["Son bölüm paragrafı."]),
    ])
    res = import_book.import_epub(data, "kayip.epub")
    assert res["chapter_count"] == 3
    assert res["title"] == "Kayıp Krallık"
    assert res["slug"].startswith("epub-")
    assert res["first_url"] == synthetic.chapter_url(res["slug"], 1, "epub://")
    assert library.get_book(res["slug"])["current_url"] == res["first_url"]

    # Yerinde-HTML modu: content_type html, raw_source = gövde HTML'i (yapı korunur)
    staged1 = cache.get_staged(res["first_url"])
    assert staged1["content_type"] == "html"
    assert "<p" in staged1["raw_source"] and "İlk paragraf" in staged1["raw_source"]
    assert cache.get_chapter(res["first_url"]) is None  # sahneli, henüz çevrilmedi

    # Zincir 1 → 2
    url2 = synthetic.chapter_url(res["slug"], 2, "epub://")
    assert staged1["next_url"] == url2
    assert cache.get_staged(url2)["prev_url"] == res["first_url"]


def test_epub_image_extracted_to_media():
    import io
    from PIL import Image
    from ebooklib import epub

    buf = io.BytesIO()
    Image.new("RGB", (6, 6), (200, 50, 50)).save(buf, "PNG")
    png = buf.getvalue()

    book = epub.EpubBook()
    book.set_title("Resimli")
    book.set_language("en")
    img = epub.EpubImage(uid="i1", file_name="images/pic.png", media_type="image/png", content=png)
    book.add_item(img)
    c = epub.EpubHtml(title="Bir", file_name="c1.xhtml", lang="en")
    c.content = '<html><body><h2>Bir</h2><p>Metin yeterince uzun burada.</p><img src="images/pic.png"/></body></html>'
    book.add_item(c)
    book.toc = (c,)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", c]
    fd, path = tempfile.mkstemp(suffix=".epub")
    os.close(fd)
    epub.write_epub(path, book)
    with open(path, "rb") as f:
        data = f.read()
    os.remove(path)

    from core import media

    res = import_book.import_epub(data, "resimli.epub")
    staged = cache.get_staged(res["first_url"])
    assert "/media/" in staged["raw_source"]  # img src /media'ya yeniden yazıldı
    assert (media.book_dir(res["slug"]) / "pic.png").is_file()  # resim çıkarıldı


def test_epub_page_translates_html_in_place(monkeypatch):
    from core import pipeline

    _stub_translate(monkeypatch)
    data = _make_epub("Roman", [("Bir", ["The old man spoke softly to the boy."])])
    res = import_book.import_epub(data, "roman.epub")
    payload = pipeline.get_or_translate(res["first_url"], api_key="test-key")
    assert payload["content_type"] == "html"
    assert "Çeviri:" in payload["translation"]  # blok metni yerinde çevrildi
    assert "<p" in payload["translation"]  # HTML yapısı korundu


def test_epub_no_chapters_raises():
    data = _make_epub("Boş", [("Kapak", [""])])  # <20 karakter → atlanır
    with pytest.raises(import_book.BookImportError):
        import_book.import_epub(data, "bos.epub")


def test_epub_import_api_endpoint():
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    import server

    data = _make_epub("API Kitabı", [
        ("Bir", ["Bu bölümün metni yeterince uzun olmalı ki atlanmasın diye."]),
        ("İki", ["İkinci bölüm de burada duruyor efendim."]),
    ])
    client = TestClient(server.app)
    res = client.post("/api/import/epub?filename=api.epub", content=data)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["chapter_count"] == 2
    assert body["slug"].startswith("epub-")
    assert library.get_book(body["slug"]) is not None


def test_epub_empty_body_400():
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    import server

    res = TestClient(server.app).post("/api/import/epub", content=b"")
    assert res.status_code == 400


def _make_pdf(pages):
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    for txt in pages:
        page = doc.new_page()
        page.insert_text((72, 72), txt, fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


def test_pdf_import_page_mode():
    # Sayfa görsel modu: HER SAYFA = 1 bölüm (content_type html), kaynak PDF saklanır.
    data = _make_pdf([f"Sayfa {i} metni yeterince uzun olsun diye buraya yazildi." for i in range(1, 6)])
    res = import_book.import_pdf(data, filename="belge.pdf")
    assert res["chapter_count"] == 5  # 5 sayfa → 5 bölüm
    assert res["slug"].startswith("pdf-")
    assert res["title"] == "belge"
    assert res["first_url"] == synthetic.chapter_url(res["slug"], 1, "pdf://")

    from core import media

    assert (media.book_dir(res["slug"]) / "source.pdf").is_file()  # render için kaynak saklandı
    staged = cache.get_staged(res["first_url"])
    assert staged["content_type"] == "html"
    assert cache.get_chapter(res["first_url"]) is None  # sahneli, henüz render edilmedi


def _stub_translate(monkeypatch):
    from core import import_translate

    def fake(text, api_key, glossary=None, models=("x",)):
        blocks = text.split("\n\n")
        return {
            "translation": "\n\n".join("Çeviri: " + b for b in blocks),
            "source": None, "detected_names": [], "chunk_count": 1,
        }

    monkeypatch.setattr(import_translate.translate, "translate_chapter", fake)


def test_pdf_page_renders_translated_image(monkeypatch):
    import re
    from core import media, pipeline

    _stub_translate(monkeypatch)
    data = _make_pdf([f"Page {i}: the old man opened his eyes slowly here." for i in range(1, 4)])
    res = import_book.import_pdf(data, filename="roman.pdf")

    # Sayfa 1'i aç → çevrilmiş sayfa PNG render edilir, <img> HTML döner
    payload = pipeline.get_or_translate(res["first_url"], api_key="test-key")
    assert payload["content_type"] == "html"
    assert '<img class="page-img"' in payload["translation"]
    m = re.search(r'src="/media/([^"]+)"', payload["translation"])
    assert m and media.resolve(m.group(1)) is not None  # PNG dosyası gerçekten var

    # Tekrar aç → cache isabeti (cached=True), yeniden render/çeviri yapılmaz
    p2 = pipeline.get_or_translate(res["first_url"], api_key="test-key")
    assert p2["content_type"] == "html" and p2["cached"] is True


def test_pdf_import_api_endpoint():
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    import server

    data = _make_pdf([f"Ikinci belge sayfa {i} icerigi burada duruyor efendim." for i in range(1, 4)])
    client = TestClient(server.app)
    res = client.post("/api/import/pdf?filename=ikinci.pdf", content=data)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["chapter_count"] == 3  # 3 sayfa → 3 bölüm (sayfa modu)
    assert body["slug"].startswith("pdf-")


def _make_cbz(n):
    import io
    import zipfile

    from PIL import Image

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i in range(1, n + 1):
            b = io.BytesIO()
            Image.new("RGB", (400, 600), (210, 210, 210)).save(b, "PNG")
            z.writestr(f"page-{i:03}.png", b.getvalue())
    return buf.getvalue()


def test_manga_cbz_stages_pages():
    from core import media

    res = import_book.import_manga(_make_cbz(3), "seri.cbz")
    assert res["chapter_count"] == 3
    assert res["slug"].startswith("manga-")
    assert res["first_url"] == synthetic.chapter_url(res["slug"], 1, "manga://")
    assert (media.book_dir(res["slug"]) / "src-1").is_file()  # kaynak sayfa saklandı
    staged = cache.get_staged(res["first_url"])
    assert staged["content_type"] == "html"
    assert cache.get_chapter(res["first_url"]) is None  # sahneli, henüz çevrilmedi


def test_manga_single_image():
    import io
    from PIL import Image

    b = io.BytesIO()
    Image.new("RGB", (300, 400), (120, 120, 120)).save(b, "PNG")
    res = import_book.import_manga(b.getvalue(), "tek.png")
    assert res["chapter_count"] == 1 and res["slug"].startswith("manga-")


def test_manga_non_image_rejected():
    with pytest.raises(import_book.BookImportError):
        import_book.import_manga(b"not an image or zip", "x.cbz")


def test_manga_url_import_stages_pages(monkeypatch):
    import io

    from PIL import Image

    from core import manga_fetch

    def fake_fetch(url, priority="interactive", ticket=None):
        imgs = []
        for _ in range(4):
            b = io.BytesIO()
            Image.new("RGB", (400, 600), (60, 60, 60)).save(b, "PNG")
            imgs.append(b.getvalue())
        return {"title": "Solo Leveling Chapter 1", "images": imgs}

    monkeypatch.setattr(manga_fetch, "fetch_manga_chapter", fake_fetch)
    res = import_book.import_manga_url("https://asurascans.com/comics/x/chapter/1")
    assert res["chapter_count"] == 4 and res["slug"].startswith("manga-")
    assert cache.get_staged(res["first_url"])["content_type"] == "html"


def test_is_manga_url():
    from core import manga_fetch

    assert manga_fetch.is_manga_url("https://asurascans.com/comics/x/chapter/1")
    assert not manga_fetch.is_manga_url("https://novelbin.com/b/x/chapter-1")


def test_pick_page_images_excludes_cover_and_sorts():
    from core import manga_fetch

    imgs = [
        {"u": "https://s/covers/series.webp", "w": 400, "h": 600},  # kapak (ayrı dizin)
        {"u": "https://s/ch/5/010.webp", "w": 720, "h": 4000},
        {"u": "https://s/ch/5/001.webp", "w": 720, "h": 4000},
        {"u": "https://s/ch/5/002.webp", "w": 720, "h": 4000},
        {"u": "https://s/ui/icon.png", "w": 40, "h": 40},  # küçük → atla
    ]
    picked = manga_fetch._pick_page_images(imgs)
    assert len(picked) == 3  # yalnız en kalabalık dizin (/ch/5/), kapak+ikon hariç
    assert picked[0].endswith("001.webp") and picked[-1].endswith("010.webp")  # doğal sıra


def test_manga_engine_triggers_batch(monkeypatch):
    from core import manga_batch, manga_engine, pipeline
    from core.synthetic import MangaTranslating

    monkeypatch.setattr(manga_engine, "available", lambda: True)
    calls = []
    monkeypatch.setattr(
        manga_batch, "ensure_started",
        lambda slug, key: (calls.append(slug), {"done": 2, "total": 5})[1],
    )
    res = import_book.import_manga(_make_cbz(3), "m.cbz")
    with pytest.raises(MangaTranslating) as ei:
        pipeline.get_or_translate(res["first_url"], api_key="test-key")
    assert ei.value.done == 2 and ei.value.total == 5
    assert calls  # batch iş tetiklendi


def test_manga_translating_api_response(monkeypatch):
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from core import manga_batch, manga_engine
    import server

    monkeypatch.setattr(manga_engine, "available", lambda: True)
    monkeypatch.setattr(manga_batch, "ensure_started", lambda slug, key: {"done": 1, "total": 4})
    monkeypatch.setattr(server, "API_KEY", "test-key")
    res = import_book.import_manga(_make_cbz(2), "m.cbz")
    r = TestClient(server.app).get("/api/chapter", params={"url": res["first_url"]})
    assert r.status_code == 200
    # no-store ŞART: SW bu geçici yanıtı cache'lemesin (poll bayat placeholder'a kilitlenir).
    assert r.headers.get("cache-control") == "no-store"
    body = r.json()
    assert body["content_type"] == "translating" and body["total"] == 4
    assert body["next_url"] == synthetic.chapter_url(res["slug"], 2, "manga://")


def test_manga_page_renders_translated_image(monkeypatch):
    import re

    from core import import_translate, manga_engine, media, pipeline

    # Yerel motor kurulu olsa bile bu test VİSİON YEDEĞİNİ doğrular (motoru kapat).
    monkeypatch.setattr(manga_engine, "available", lambda: False)
    # Gemini-vision yerine sabit bölge (gerçek çağrı yok)
    monkeypatch.setattr(
        import_translate, "_manga_regions",
        lambda img, key: [{"box_2d": [120, 100, 320, 700], "text": "Hello!", "tr": "Merhaba dünya!"}],
    )
    res = import_book.import_manga(_make_cbz(2), "m.cbz")
    payload = pipeline.get_or_translate(res["first_url"], api_key="test-key")
    assert payload["content_type"] == "html"
    assert '<img class="page-img"' in payload["translation"]
    m = re.search(r'src="/media/([^"]+)"', payload["translation"])
    assert m and media.resolve(m.group(1)) is not None  # çevrilmiş sayfa PNG'si var
    # tekrar aç → cache isabeti (yeniden vision çağrısı yok)
    assert pipeline.get_or_translate(res["first_url"], api_key="test-key")["cached"] is True
