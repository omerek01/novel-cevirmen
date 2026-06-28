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
    # webnovel.com (resmi Qidian platformu). Sonraki/önceki bağlantı anchor DEĞİL;
    # sayfaya gömülü nextChapterId/preChapterId'den üretilir (_parse özel dalı).
    # NOT: "webnovel" anahtarı "freewebnovel" host'unu da kapsar → bu kayıt MUTLAKA
    # freewebnovel'den SONRA gelmeli (_site_for ilk eşleşeni döndürür).
    "webnovel": {
        "content": ".cha-words",
        "title": [".cha-tit h1", ".cha-tit"],
        "next": [],  # kullanılmaz; nav gömülü id'lerden
        "prev": [],
        "slug_mode": "after_book",  # /[dil/]book/<bookid>/<chapterid>
        "nav_mode": "webnovel_ids",
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


class CloudflareChallenge(FetchError):
    """Cloudflare doğrulaması geçilemediğinde fırlatılır."""


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

    FETCH_CDP_URL ayarlıysa (örn. http://127.0.0.1:9222), önce kullanıcının elle
    başlattığı gerçek Chrome'a CDP ile bağlanılır (otomasyon bayrağı yok → CF insan
    kabul eder, sert challenge'ları geçer). Chrome açık değilse otomatik olarak normal
    akışa düşülür; yani env ayarlı olsa bile normal/telefon kullanımı bozulmaz.
    Başlatma: `python scripts/start_chrome_cdp.py` (bkz. script başlığı).

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


# Cloudflare çözüm ipuçları (challenge mesajına eklenir). Akışa göre farklı.
_LAUNCH_SOLVE_HINT = (
    "Tek seferlik çözüm için sunucuyu FETCH_HEADLESS=0 ile başlatıp açılan pencerede "
    "doğrulamayı tamamlayın; sonraki çekimler otomatik geçer."
)
_CDP_SOLVE_HINT = (
    "Açık olan gerçek Chrome penceresinde siteye girip 'Verify you are human' "
    "kutusunu çözün (pencereyi açık bırakın); sonraki çekimler otomatik geçer."
)


def _fetch_locked(url: str, headless: bool, timeout_ms: int) -> dict:
    site = _site_for(url)
    host = urlparse(url).hostname or "kaynak site"
    # FETCH_CDP_URL ayarlıysa önce kullanıcının elle başlattığı gerçek Chrome'a (CDP)
    # bağlanmayı dene — otomasyon bayrakları olmadığı için Cloudflare onu insan kabul
    # eder. Bağlanamazsa (Chrome açık değil) None döner → normal paket-Chromium akışına
    # düşülür. Böylece env ayarlı olsa bile telefon/normal kullanım hiçbir zaman bozulmaz.
    cdp_url = os.getenv("FETCH_CDP_URL", "").strip()
    html = None
    if cdp_url:
        html = _fetch_via_cdp(cdp_url, url, site, host, timeout_ms)
    if html is None:
        html = _fetch_via_launch(url, headless, site, host, timeout_ms)
    return _parse(html, url, site)


def _fetch_via_launch(
    url: str, headless: bool, site: dict, host: str, timeout_ms: int
) -> str:
    """Paket Chromium'u kalıcı profille başlatıp sayfayı çeker (varsayılan/sabah akışı)."""
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
            return _extract_html(page, url, site, host, timeout_ms, _LAUNCH_SOLVE_HINT)
        finally:
            context.close()


def _fetch_via_cdp(
    cdp_url: str, url: str, site: dict, host: str, timeout_ms: int
) -> str | None:
    """Açık gerçek Chrome'a (CDP) bağlanıp çeker; Chrome erişilemezse None döner.

    Kullanıcının elle başlattığı gerçek Chrome (Playwright otomasyon bayrakları YOK)
    Cloudflare tarafından insan kabul edilir → sert challenge'da bile kullanıcı bir kez
    çözünce o profile cookie yazılır, sonraki çekimler otomatik geçer. Bağlantı
    kurulamazsa (debug-portu kapalı) None → çağıran normal akışa düşer. Bağlanıp da
    içerik gelmezse (challenge/yavaş) hata fırlatır — gerçek Chrome'un verdiği sonuç
    nihaidir, daha zayıf paket-Chromium'a düşmenin anlamı yok.
    """
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(cdp_url, timeout=4000)
        except Exception:
            return None  # gerçek Chrome (debug-portu) açık değil → normal akışa düş
        page = None
        try:
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.new_page()  # kullanıcının sekmelerine dokunmadan yeni sekme
            return _extract_html(page, url, site, host, timeout_ms, _CDP_SOLVE_HINT)
        finally:
            if page is not None:
                try:
                    page.close()  # yalnız açtığımız sekmeyi kapat
                except Exception:
                    pass
            # Kullanıcının Chrome'unu KAPATMA — sadece CDP bağlantısını bırak.


def _extract_html(
    page, url: str, site: dict, host: str, timeout_ms: int, solve_hint: str
) -> str:
    """Sayfaya gidip içerik selektörünü bekler ve HTML'i döndürür (akıştan bağımsız).

    Hata semantiği: 52x origin → FetchError; challenge → FetchError(solve_hint);
    içerik gelmedi/yavaş → _Transient (yeniden denenebilir).
    """
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
            raise CloudflareChallenge("Cloudflare doğrulaması geçilemedi. " + solve_hint) from exc
        # İçerik gelmedi: yavaş yükleme olabilir → geçici say, yeniden dene.
        raise _Transient(
            f"İçerik bulunamadı ({site['content']} sayfada yok). Site yapısı "
            "değişmiş, URL yanlış olabilir ya da sayfa geç yüklendi."
        ) from exc
    return page.content()


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
    webnovel = site.get("nav_mode") == "webnovel_ids"
    # webnovel: kilitli (ücretli/giriş gerektiren) bölümde metin sayfaya hiç gelmez.
    if webnovel and _webnovel_locked(soup):
        raise FetchError(
            "Bu bölüm webnovel.com'da kilitli (ücretli/giriş gerektiriyor); "
            "yalnızca ücretsiz bölümler okunabilir."
        )
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

    if webnovel:
        slug, _ = _book_info(base_url, "after_book")
        book_title = _webnovel_book_title(soup) or slug
        next_url = _webnovel_nav_url(html, base_url, "nextChapterId")
        prev_url = _webnovel_nav_url(html, base_url, "preChapterId")
        chapter_no = _chapter_no_from_title(title)
    else:
        slug, book_title = _book_info(base_url, site["slug_mode"])
        next_url = _nav_chapter_url(soup, base_url, site["next"])
        prev_url = _nav_chapter_url(soup, base_url, site.get("prev", []))
        chapter_no = _chapter_no(base_url)
    return {
        "title": title,
        "text": text,
        "next_url": next_url,
        "prev_url": prev_url,
        "book_slug": slug,
        "book_title": book_title,
        "chapter_no": chapter_no,
    }


def _webnovel_locked(soup: BeautifulSoup) -> bool:
    """webnovel bölümü kilitli mi (data-islock="1")."""
    el = soup.select_one("[data-islock]")
    return el is not None and (el.get("data-islock") or "") == "1"


def _webnovel_book_title(soup: BeautifulSoup) -> str | None:
    """Sayfa <title>'ından kitap adını ayıkla ("Bölüm - Kitap - WebNovel")."""
    if not soup.title:
        return None
    segs = [s.strip() for s in soup.title.get_text(strip=True).split(" - ") if s.strip()]
    if len(segs) >= 3 and segs[-1].lower() == "webnovel":
        return segs[-2]
    return None


def _webnovel_nav_url(html: str, base_url: str, key: str) -> str | None:
    """Gömülü nextChapterId/preChapterId'den bölüm URL'i üretir (anchor yok).

    base_url .../book/<bookid>/<chapterid> biçiminde; son segmenti (chapterid) yeni
    id ile değiştirir → dil ön eki (/tr) ve bookid korunur. -1/0/boş → None.
    """
    m = re.search(re.escape(key) + r'["\']?\s*[:=]\s*["\']?(-?\d+)', html)
    if not m:
        return None
    cid = m.group(1)
    if cid in ("", "0", "-1"):
        return None
    parent = base_url.split("?")[0].split("#")[0].rstrip("/").rsplit("/", 1)[0]
    return f"{parent}/{cid}"


def _chapter_no_from_title(title: str) -> int | None:
    """"Bölüm 12: ..." / "Chapter 12" başlığından bölüm numarasını çıkarır."""
    m = re.search(r"(?:b[öo]l[üu]m|chapter)\s*(\d+)", title or "", re.IGNORECASE)
    return int(m.group(1)) if m else None


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
    elif slug_mode == "after_book" and "book" in parts:
        idx = parts.index("book")
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
