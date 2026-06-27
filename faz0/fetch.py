"""novelbin bölüm çekme — Playwright ile Cloudflare'i aşar, içeriği ayıklar."""
from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

CONTENT_SELECTOR = "#chr-content"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class FetchError(Exception):
    """Bölüm çekilemediğinde fırlatılır (Cloudflare, eksik içerik vb.)."""


def fetch_chapter(url: str, headless: bool = True, timeout_ms: int = 60000) -> dict:
    """Bir novelbin bölüm sayfasını çeker.

    Döner: {"title": str, "text": str, "next_url": str | None}
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(user_agent=USER_AGENT, locale="en-US")
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            # İçerik seçicisini bekle — Cloudflare challenge geçince DOM'a gelir.
            page.wait_for_selector(CONTENT_SELECTOR, timeout=timeout_ms)
            html = page.content()
        except PlaywrightTimeout as exc:
            raise FetchError(
                "İçerik bulunamadı (muhtemelen Cloudflare engeli). "
                "Tekrar deneyin ya da --headed ile çalıştırın."
            ) from exc
        finally:
            browser.close()
    return _parse(html, url)


def _parse(html: str, base_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    content_el = soup.select_one(CONTENT_SELECTOR)
    if content_el is None:
        raise FetchError("Bölüm içeriği (#chr-content) sayfada bulunamadı.")

    # Reklam ve script artıklarını temizle.
    for junk in content_el.select("script, style, ins, .ads, .adsbygoogle"):
        junk.decompose()

    paragraphs = [p.get_text(" ", strip=True) for p in content_el.find_all("p")]
    paragraphs = [p for p in paragraphs if p]
    text = "\n\n".join(paragraphs) if paragraphs else content_el.get_text("\n", strip=True)

    title_el = soup.select_one("a.chr-title") or soup.select_one(".chr-title")
    if title_el is not None:
        title = title_el.get_text(strip=True)
    elif soup.title is not None:
        title = soup.title.get_text(strip=True)
    else:
        title = "Bölüm"

    next_url = _next_chapter_url(soup, base_url)
    return {"title": title, "text": text, "next_url": next_url}


def _next_chapter_url(soup: BeautifulSoup, base_url: str) -> str | None:
    # novelbin.com: a.js-chapter-nav[data-chapter-nav="next"] (gerçek href + data-chapter-url).
    # Eski/alternatif tema yedeği: a#next_chap.
    next_el = soup.select_one('a.js-chapter-nav[data-chapter-nav="next"]') or soup.select_one(
        "a#next_chap"
    )
    if next_el is None:
        return None
    href = next_el.get("href") or next_el.get("data-chapter-url")
    if not href or href.strip() in {"#", ""} or "javascript" in href:
        return None
    return urljoin(base_url, href)
