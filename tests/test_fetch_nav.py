"""fetch: gezinme linki çıkarımı (next/prev) + slug/bölüm-no türetme."""
from bs4 import BeautifulSoup

from core import fetch

BASE = "https://novelbin.com/b/solo-leveling/chapter-2"


def _soup(html):
    return BeautifulSoup(html, "html.parser")


def test_nav_extracts_prev_and_next():
    soup = _soup(
        '<a id="prev_chap" href="/b/solo-leveling/chapter-1">prev</a>'
        '<a id="next_chap" href="/b/solo-leveling/chapter-3">next</a>'
    )
    assert fetch._nav_chapter_url(soup, BASE, ["a#prev_chap"]).endswith("chapter-1")
    assert fetch._nav_chapter_url(soup, BASE, ["a#next_chap"]).endswith("chapter-3")


def test_nav_rejects_hash_and_javascript():
    soup = _soup('<a id="next_chap" href="#">x</a><a id="prev_chap" href="javascript:void(0)">y</a>')
    assert fetch._nav_chapter_url(soup, BASE, ["a#next_chap"]) is None
    assert fetch._nav_chapter_url(soup, BASE, ["a#prev_chap"]) is None


def test_nav_missing_returns_none():
    soup = _soup("<p>içerik</p>")
    assert fetch._nav_chapter_url(soup, BASE, ["a#next_chap", "a[rel=next]"]) is None


def test_nav_data_chapter_url_fallback():
    soup = _soup('<a id="next_chap" data-chapter-url="/b/x/chapter-9">next</a>')
    assert fetch._nav_chapter_url(soup, BASE, ["a#next_chap"]).endswith("chapter-9")


def test_nav_first_matching_selector_wins():
    soup = _soup('<a rel="next" href="/b/x/chapter-5">n</a>')
    out = fetch._nav_chapter_url(soup, BASE, ["a#next_chap", "a[rel=next]"])
    assert out.endswith("chapter-5")


def test_parse_returns_prev_and_next():
    html = (
        '<a class="chr-title">Bölüm 2</a>'
        '<div id="chr-content"><p>Birinci paragraf.</p><p>İkinci paragraf.</p></div>'
        '<a class="js-chapter-nav" data-chapter-nav="prev" href="/b/x/chapter-1">prev</a>'
        '<a class="js-chapter-nav" data-chapter-nav="next" href="/b/x/chapter-3">next</a>'
    )
    out = fetch._parse(html, BASE, fetch.SITES["novelbin"])
    assert out["prev_url"].endswith("chapter-1")
    assert out["next_url"].endswith("chapter-3")
    assert "Birinci paragraf." in out["text"]
    assert out["title"] == "Bölüm 2"


def test_parse_missing_content_raises():
    import pytest

    with pytest.raises(fetch.FetchError):
        fetch._parse("<p>boş</p>", BASE, fetch.SITES["novelbin"])


def test_chapter_no_and_book_info():
    assert fetch._chapter_no("https://novelbin.com/b/solo-leveling/chapter-42") == 42
    assert fetch._chapter_no("https://x/foo") is None
    slug, title = fetch._book_info("https://novelbin.com/b/solo-leveling/chapter-1", "after_b")
    assert slug == "solo-leveling"
    assert title == "Solo Leveling"
