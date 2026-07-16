"""Çevrilmiş (önbellekteki) bölümlerden ePub üret."""
from __future__ import annotations

import os
import tempfile
from html import escape

from ebooklib import epub

from . import cache, library


def build_epub(slug: str, start: int = 1, count: int = 1000) -> tuple[str, bytes]:
    """slug kitabının bölümlerini ePub'a paketler.

    start: başlangıç bölüm numarası, count: kaç bölüm.
    Döner: (dosya_adi, epub_baytlari). Uygun bölüm yoksa ("", b"").
    """
    all_chapters = cache.list_chapters(slug)  # bölüm no'ya göre sıralı
    numbered = [c for c in all_chapters if c["chapter_no"] is not None]
    selected = [c for c in numbered if c["chapter_no"] >= start]
    # Hiçbir bölümde numara yoksa (bazı siteler chapter_no üretmez) aralık filtresi
    # anlamsızdır → hepsini al. Numaralı bölüm VARSA start'a saygı gösterilir
    # (aralık dışı istek boş döner). Böylece numarasız kitaplar da ePub'a paketlenir.
    if not numbered:
        selected = all_chapters
    selected = selected[:count]
    if not selected:
        return ("", b"")

    meta = library.get_book(slug) or {}
    title = meta.get("title") or slug

    book = epub.EpubBook()
    book.set_identifier(f"novellink-{slug}")
    book.set_title(title)
    book.set_language("tr")
    book.add_author("NOVELLINK")

    items = []
    for idx, ch in enumerate(selected, 1):
        full = cache.get_chapter(ch["url"]) or {}
        translation = full.get("translation", "") or ""
        ch_title = ch["title"] or f"Bölüm {ch['chapter_no']}"
        paragraphs = "".join(
            f"<p>{escape(p.strip())}</p>"
            for p in translation.split("\n\n")
            if p.strip()
        )
        item = epub.EpubHtml(title=ch_title, file_name=f"chap_{idx:04d}.xhtml", lang="tr")
        item.content = f"<h2>{escape(ch_title)}</h2>{paragraphs}"
        book.add_item(item)
        items.append(item)

    book.toc = tuple(items)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *items]

    tmp = tempfile.NamedTemporaryFile(suffix=".epub", delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        epub.write_epub(tmp_path, book)
        with open(tmp_path, "rb") as fh:
            data = fh.read()
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    first = selected[0]["chapter_no"] or 1
    last = selected[-1]["chapter_no"] or len(selected)
    return (f"{slug}-{first}-{last}.epub", data)
