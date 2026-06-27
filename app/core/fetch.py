"""novelbin bölüm çekme — Playwright ile Cloudflare'i aşar, içeriği ayıklar."""
from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

CONTENT_SELECTOR = "#chr-content"
# Cloudflare origin-hata ailesi: origin (novelbin) sunucusu yanıt vermiyor.
# Bunlar beklemekle düzelmez (challenge değil) → anında, doğru mesajla başarısız ol.
CF_ORIGIN_ERRORS = frozenset({520, 521, 522, 523, 524, 525, 526})
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Çözülen cf_clearance cookie'sinin saklandığı kalıcı tarayıcı profili.
# Cloudflare doğrulaması bir kez geçilince diske yazılır, sonraki çekimlerde
# yeniden kullanılır → her bölümde challenge çözmek gerekmez.
PROFILE_DIR = Path(__file__).resolve().parent.parent.parent / "cache" / ".pw-profile"

# Aynı profili iki çekimin eşzamanlı açıp kilitlemesini önler (Chromium SingletonLock).
_FETCH_LOCK = threading.Lock()

# Headless Chromium'un Cloudflare'e ele veren izlerini gizler (goto'dan önce enjekte).
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
window.chrome = window.chrome || { runtime: {} };
const _q = window.navigator.permissions && window.navigator.permissions.query;
if (_q) {
  window.navigator.permissions.query = (p) =>
    p && p.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : _q(p);
}
"""

LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]

# "Just a moment…" / Turnstile bekleme sayfası başlık imzaları.
CF_CHALLENGE_TITLES = ("just a moment", "attention required", "checking your browser")

# Site başına ayrıştırma kuralları (domain → selektörler). Cloudflare'i aştıktan
# sonra içerik çıkarımı site-özeldir; yeni site eklemek için buraya kayıt ekle.
SITES = {
    "novelbin": {
        "content": "#chr-content",
        "title": ["a.chr-title", ".chr-title"],
        "next": ['a.js-chapter-nav[data-chapter-nav="next"]', "a#next_chap"],
        "prev": ['a.js-chapter-nav[data-chapter-nav="prev"]', "a#prev_chap"],
        "slug_mode": "after_b",  # /b/<slug>/...
    },
    "novelfull": {
        "content": "#chapter-content",
        "title": ["a.chapter-title", ".chapter-title", ".chapter-text"],
        "next": ["a#next_chap", "a[rel=next]"],
        "prev": ["a#prev_chap", "a[rel=prev]"],
        "slug_mode": "first",  # /<slug>/chapter-...
    },
    "freewebnovel": {
        "content": "#article",
        "title": ["span.chapter", ".chapter-title"],
        "next": ["a#next_url"],
        "prev": ["a#prev_url"],
        "slug_mode": "after_novel",  # /novel/<slug>/chapter-...
    },
}

# Bilinmeyen site → birleşik selektörlerle en iyi çaba.
GENERIC_SITE = {
    "content": "#chr-content, #chapter-content, #article, .chapter-content, .chapter-c",
    "title": ["a.chr-title", ".chr-title", "a.chapter-title", ".chapter-title", "span.chapter"],
    "next": [
        'a.js-chapter-nav[data-chapter-nav="next"]',
        "a#next_chap",
        "a#next_url",
        "a[rel=next]",
    ],
    "prev": [
        'a.js-chapter-nav[data-chapter-nav="prev"]',
        "a#prev_chap",
        "a#prev_url",
        "a[rel=prev]",
    ],
    "slug_mode": "first",
}


def _site_for(url: str) -> dict:
    """URL'in domainine göre ayrıştırma kuralını seçer."""
    host = (urlparse(url).hostname or "").lower()
    for key, cfg in SITES.items():
        if key in host:
            return cfg
    return GENERIC_SITE


class FetchError(Exception):
    """Bölüm çekilemediğinde fırlatılır (Cloudflare, eksik içerik vb.)."""


class _Transient(Exception):
    """İç sinyal: geçici çekme hatası (yavaş yükleme/network) → yeniden denenebilir."""


def fetch_chapter(
    url: str,
    headless: bool | None = None,
    timeout_ms: int = 60000,
    retries: int = 2,
) -> dict:
    """Bir novelbin bölüm sayfasını çeker.

    headless=None ise FETCH_HEADLESS ortam değişkenine bakar ("0" → görünür pencere,
    Cloudflare doğrulamasını bir kez elle çözmek için). Çözülen cookie kalıcı profile
    yazılır; sonraki çekimler headless olarak otomatik geçer.

    Geçici hatalar (yavaş yükleme, network) üstel geri-çekilmeyle `retries` kez
    yeniden denenir. Kalıcı hatalar (Cloudflare challenge, origin 52x) denenmez.

    Döner: {"title": str, "text": str, "next_url": str | None, "prev_url": ..., ...}
    """
    if headless is None:
        headless = os.getenv("FETCH_HEADLESS", "1") != "0"
    delay = 2.0
    last_exc: Exception | None = None
    # Tek kilit: aynı kalıcı profili eşzamanlı açan çekimleri sıraya sokar.
    with _FETCH_LOCK:
        for attempt in range(retries + 1):
            try:
                return _fetch_locked(url, headless, timeout_ms)
            except _Transient as exc:
                last_exc = exc
                if attempt < retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise FetchError(
                    str(exc) or "Bölüm geçici olarak çekilemedi; biraz sonra deneyin."
                ) from exc
    raise FetchError("Bölüm çekilemedi.") from last_exc  # teorik olarak ulaşılmaz


def _fetch_locked(url: str, headless: bool, timeout_ms: int) -> dict:
    site = _site_for(url)
    host = urlparse(url).hostname or "kaynak site"
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=headless,
            user_agent=USER_AGENT,
            locale="en-US",
            viewport={"width": 1280, "height": 800},
            args=LAUNCH_ARGS,
        )
        context.add_init_script(STEALTH_JS)  # tüm sayfalara, goto'dan önce
        page = context.pages[0] if context.pages else context.new_page()
        try:
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            except PlaywrightTimeout as exc:
                raise _Transient("Sayfa yüklenmedi (zaman aşımı).") from exc
            status = resp.status if resp else 0
            if status in CF_ORIGIN_ERRORS:
                raise FetchError(
                    f"Kaynak site ({host}) şu an yanıt vermiyor (HTTP {status}). "
                    "Bu sitenin sunucu sorunu; başka bir kaynaktan deneyin veya bekleyin."
                )
            try:
                page.wait_for_selector(site["content"], timeout=timeout_ms)
            except PlaywrightTimeout as exc:
                if _looks_like_challenge(page):
                    raise FetchError(
                        "Cloudflare doğrulaması geçilemedi. Tek seferlik çözüm için "
                        "sunucuyu FETCH_HEADLESS=0 ile başlatıp açılan pencerede "
                        "doğrulamayı tamamlayın; sonraki çekimler otomatik geçer."
                    ) from exc
                # İçerik gelmedi: yavaş yükleme olabilir → geçici say, yeniden dene.
                raise _Transient(
                    f"İçerik bulunamadı ({site['content']} sayfada yok). Site yapısı "
                    "değişmiş, URL yanlış olabilir ya da sayfa geç yüklendi."
                ) from exc
            html = page.content()
        finally:
            context.close()
    return _parse(html, url, site)


def _looks_like_challenge(page) -> bool:
    """Sayfanın bir Cloudflare bekleme/doğrulama ekranı olup olmadığını anlar."""
    try:
        title = (page.title() or "").lower()
    except Exception:
        title = ""
    if any(sig in title for sig in CF_CHALLENGE_TITLES):
        return True
    try:
        return bool(
            page.query_selector(
                '#challenge-form, iframe[src*="challenges.cloudflare.com"]'
            )
        )
    except Exception:
        return False


def _parse(html: str, base_url: str, site: dict) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    content_el = soup.select_one(site["content"])
    if content_el is None:
        raise FetchError(f"Bölüm içeriği ({site['content']}) sayfada bulunamadı.")

    for junk in content_el.select("script, style, ins, .ads, .adsbygoogle"):
        junk.decompose()

    paragraphs = [p.get_text(" ", strip=True) for p in content_el.find_all("p")]
    paragraphs = [p for p in paragraphs if p]
    text = "\n\n".join(paragraphs) if paragraphs else content_el.get_text("\n", strip=True)

    title = ""
    for sel in site["title"]:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            title = el.get_text(strip=True)
            break
    if not title:
        title = soup.title.get_text(strip=True) if soup.title else "Bölüm"

    slug, book_title = _book_info(base_url, site["slug_mode"])
    return {
        "title": title,
        "text": text,
        "next_url": _nav_chapter_url(soup, base_url, site["next"]),
        "prev_url": _nav_chapter_url(soup, base_url, site.get("prev", [])),
        "book_slug": slug,
        "book_title": book_title,
        "chapter_no": _chapter_no(base_url),
    }


def _book_info(url: str, slug_mode: str = "first") -> tuple[str, str]:
    """URL'den seri kısa-adı (slug) ve okunabilir başlığı türet.

    slug_mode="after_b": /b/<slug>/... (novelbin) | "first": /<slug>/... (novelfull vb.)
    """
    parts = [p for p in urlparse(url).path.split("/") if p]
    slug = "kitap"
    if slug_mode == "after_b" and "b" in parts:
        idx = parts.index("b")
        if idx + 1 < len(parts):
            slug = parts[idx + 1]
    elif slug_mode == "after_novel" and "novel" in parts:
        idx = parts.index("novel")
        if idx + 1 < len(parts):
            slug = parts[idx + 1]
    elif parts:
        slug = parts[0]
    slug = slug.removesuffix(".html")  # novelfull novel sayfası /<slug>.html olabilir
    title = slug.replace("-", " ").replace("_", " ").strip().title() or "Kitap"
    return slug, title


def _chapter_no(url: str) -> int | None:
    match = re.search(r"chapter[-_/](\d+)", url, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _nav_chapter_url(soup: BeautifulSoup, base_url: str, selectors: list[str]) -> str | None:
    """İlk eşleşen gezinme ("sonraki"/"önceki") selektörünü kullanır.

    next ve prev için tek saf fonksiyon (DRY). data-chapter-url yedeği; `#`, boş ve
    javascript: href'leri elenir → o yönde geçerli link yoksa None.
    """
    nav_el = None
    for sel in selectors:
        nav_el = soup.select_one(sel)
        if nav_el is not None:
            break
    if nav_el is None:
        return None
    href = nav_el.get("href") or nav_el.get("data-chapter-url")
    if not href or href.strip() in {"#", ""} or "javascript" in href:
        return None
    return urljoin(base_url, href)
