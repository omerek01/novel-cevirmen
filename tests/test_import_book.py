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


def test_epub_import_stages_chapters():
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

    # Kitap rafta
    book = library.get_book(res["slug"])
    assert book is not None and book["current_url"] == res["first_url"]

    # Bölümler sahneli: raw_source dolu, çeviri YOK (staged)
    staged1 = cache.get_staged(res["first_url"])
    assert staged1 is not None
    assert "İlk paragraf" in staged1["raw_source"]
    assert cache.get_chapter(res["first_url"]) is None  # translation NULL → cache MISS (E-17)

    # Zincir: 1 → 2 → 3
    url2 = synthetic.chapter_url(res["slug"], 2, "epub://")
    assert staged1["next_url"] == url2
    staged2 = cache.get_staged(url2)
    assert staged2["prev_url"] == res["first_url"]
    assert staged2["chapter_no"] == 2

    # Paragraf sınırı korunmuş (çift satır sonu → translate hizalaması)
    assert "\n\n" in staged1["raw_source"]


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


def test_pdf_import_chapters_by_pages():
    data = _make_pdf([f"Sayfa {i} metni yeterince uzun olsun diye buraya yazildi." for i in range(1, 6)])
    # 5 sayfa, 2 sayfa = 1 bölüm → 3 bölüm (1-2, 3-4, 5)
    res = import_book.import_pdf(data, pages_per_chapter=2, filename="belge.pdf")
    assert res["chapter_count"] == 3
    assert res["slug"].startswith("pdf-")
    assert res["title"] == "belge"  # dosya adından (uzantısız)
    assert res["first_url"] == synthetic.chapter_url(res["slug"], 1, "pdf://")

    staged = cache.get_staged(res["first_url"])
    assert staged is not None and "Sayfa 1" in staged["raw_source"] and "Sayfa 2" in staged["raw_source"]
    assert cache.get_chapter(res["first_url"]) is None  # staged, çevrilmemiş


def test_pdf_import_api_endpoint():
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    import server

    data = _make_pdf([f"Ikinci belge sayfa {i} icerigi burada duruyor efendim." for i in range(1, 4)])
    client = TestClient(server.app)
    res = client.post("/api/import/pdf?filename=ikinci.pdf&pages_per_chapter=10", content=data)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["chapter_count"] == 1  # 3 sayfa, 10 sayfa/bölüm → 1 bölüm
    assert body["slug"].startswith("pdf-")
