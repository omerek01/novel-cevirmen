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


def test_fetch_locked_uses_launch_when_no_cdp_env(monkeypatch):
    """FETCH_CDP_URL yokken: sadece normal (launch) akış — CDP'ye hiç dokunma."""
    monkeypatch.delenv("FETCH_CDP_URL", raising=False)
    monkeypatch.setattr(fetch, "_fetch_via_launch", lambda *a, **k: "<html>LAUNCH</html>")

    def _boom(*a, **k):
        raise AssertionError("env yokken CDP çağrılmamalı")

    monkeypatch.setattr(fetch, "_fetch_via_cdp", _boom)
    monkeypatch.setattr(fetch, "_parse", lambda html, url, site: {"html": html})
    out = fetch._fetch_locked("https://novelbin.com/b/x/chapter-1", True, 1000)
    assert out["html"] == "<html>LAUNCH</html>"


def test_fetch_locked_prefers_cdp_when_env_set(monkeypatch):
    """FETCH_CDP_URL varsa ve bağlanırsa: gerçek Chrome (CDP) sonucu kullanılır."""
    monkeypatch.setenv("FETCH_CDP_URL", "http://127.0.0.1:9222")
    monkeypatch.setattr(fetch, "_fetch_via_cdp", lambda *a, **k: "<html>CDP</html>")
    monkeypatch.setattr(fetch, "_fetch_via_launch", lambda *a, **k: "<html>LAUNCH</html>")
    monkeypatch.setattr(fetch, "_parse", lambda html, url, site: {"html": html})
    out = fetch._fetch_locked("https://freewebnovel.com/novel/x/chapter-1", True, 1000)
    assert out["html"] == "<html>CDP</html>"


def test_fetch_locked_falls_back_when_cdp_unavailable(monkeypatch):
    """Env ayarlı ama gerçek Chrome açık değilse (None): normal akışa düş — bozulma yok."""
    monkeypatch.setenv("FETCH_CDP_URL", "http://127.0.0.1:9222")
    monkeypatch.setattr(fetch, "_fetch_via_cdp", lambda *a, **k: None)
    monkeypatch.setattr(fetch, "_fetch_via_launch", lambda *a, **k: "<html>LAUNCH</html>")
    monkeypatch.setattr(fetch, "_parse", lambda html, url, site: {"html": html})
    out = fetch._fetch_locked("https://freewebnovel.com/novel/x/chapter-1", True, 1000)
    assert out["html"] == "<html>LAUNCH</html>"


def test_cdp_connect_failure_returns_none():
    """Kapalı bir porta CDP bağlantısı None döner (gerçek, hızlı: bağlantı reddedilir)."""
    site = fetch._site_for("https://freewebnovel.com/novel/x/chapter-1")
    out = fetch._fetch_via_cdp(
        "http://127.0.0.1:1", "https://freewebnovel.com/novel/x/chapter-1",
        site, "freewebnovel.com", 1000,
    )
    assert out is None


def test_chapter_no_and_book_info():
    assert fetch._chapter_no("https://novelbin.com/b/solo-leveling/chapter-42") == 42
    assert fetch._chapter_no("https://x/foo") is None
    slug, title = fetch._book_info("https://novelbin.com/b/solo-leveling/chapter-1", "after_b")
    assert slug == "solo-leveling"
    assert title == "Solo Leveling"


# ---------- webnovel.com (gömülü id navigasyonu) ----------
WN_BASE = "https://m.webnovel.com/tr/book/235/63431738856096320"


def test_site_for_webnovel_vs_freewebnovel():
    # "webnovel" alt-dizgesi "freewebnovel" host'unu da kapsar → çakışma korunmalı.
    assert fetch._site_for("https://www.webnovel.com/tr/book/1/2")["nav_mode"] == "webnovel_ids"
    assert fetch._site_for("https://freewebnovel.com/novel/x/chapter-1")["content"] == "#article"


def test_webnovel_nav_url_from_embedded_ids():
    html = 'var x = {"nextChapterId":"999","preChapterId":"-1"};'
    nxt = fetch._webnovel_nav_url(html, WN_BASE, "nextChapterId")
    assert nxt == "https://m.webnovel.com/tr/book/235/999"  # son segment (chapterid) değişir
    assert fetch._webnovel_nav_url(html, WN_BASE, "preChapterId") is None  # -1 → None


def test_webnovel_parse_full():
    html = (
        "<head><title>Surviving (1) - Outside Of Time - WebNovel</title></head>"
        '<div class="cha-tit"><h1>Bölüm 1: Surviving (1)</h1></div>'
        '<div class="chapter_content" data-islock="0">'
        '<div class="cha-words"><p>Birinci.</p><p>İkinci.</p></div></div>'
        '<script>g={"nextChapterId":"777","preChapterId":"-1"}</script>'
    )
    out = fetch._parse(html, WN_BASE, fetch.SITES["webnovel"])
    assert out["title"] == "Bölüm 1: Surviving (1)"
    assert out["book_title"] == "Outside Of Time"
    assert out["book_slug"] == "235"
    assert out["chapter_no"] == 1
    assert out["next_url"].endswith("/777")
    assert out["prev_url"] is None
    assert "Birinci." in out["text"] and "İkinci." in out["text"]


def test_webnovel_locked_raises():
    import pytest

    html = (
        '<div class="cha-tit"><h1>Bölüm 5</h1></div>'
        '<div class="chapter_content" data-islock="1"></div>'
    )
    with pytest.raises(fetch.FetchError, match="kilitli"):
        fetch._parse(html, WN_BASE, fetch.SITES["webnovel"])
