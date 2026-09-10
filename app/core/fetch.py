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
# Düz threading.Lock yerine iki-öncelikli kapı: okuyucunun /api/chapter isteği
# ("interactive") toplu çeviri işinin ("bulk") önüne geçer. threading.Lock adalet
# garantisi vermez — kapı boşaldığında bir bulk worker, zaten bekleyen okuyucunun
# önüne dalabilirdi (barging). Bekleyen okuyucu varken bulk kapıyı hiç alamaz;
# böylece toplu çeviri sürerken okumaya devam edilebilir.
class GateTicket:
    """Kapı beklerken önceliği yükseltilebilir bilet (E-1, tek-uçuş boost'u).

    Arka plan uçuşu kapıda beklerken interaktif bir okuyucu uçuşa katılırsa
    `boost()` çağrılır: bekleyen acquire interactive önceliğine yükselir
    (aksi halde okuyucu bulk önceliğiyle bekler, kapının varlık sebebi delinir).
    Boost yalnız kapı beklemesini kapsar; süren çeviri kesilmez (E-24 sınırı).
    """

    def __init__(self, gate: "_PriorityGate", priority: str) -> None:
        self._gate = gate
        self.interactive = priority != "bulk"
        self._in_acquire = False

    def boost(self) -> None:
        with self._gate._cond:
            if self.interactive:
                return
            self.interactive = True
            if self._in_acquire:  # şu an kapıda bekliyor → sayaç + uyandır
                self._gate._interactive_waiting += 1
                self._gate._cond.notify_all()


class _PriorityGate:
    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._busy = False
        self._interactive_waiting = 0

    def ticket(self, priority: str) -> GateTicket:
        return GateTicket(self, priority)

    def acquire(self, priority: str, ticket: GateTicket | None = None) -> None:
        interactive = priority != "bulk"
        if ticket is not None:
            interactive = interactive or ticket.interactive
            ticket._in_acquire = True
        with self._cond:
            counted = interactive  # girişte saydıysak çıkışta düşeceğiz
            if counted:
                self._interactive_waiting += 1
            try:
                # Boost mid-bekleme (E-1): predikat her uyanışta bileti yeniden okur.
                while True:
                    eff = interactive or (ticket is not None and ticket.interactive)
                    if not self._busy and (eff or self._interactive_waiting == 0):
                        break
                    self._cond.wait()
                self._busy = True
            finally:
                # boost() bekleme sırasında +1 eklediyse (bilet bulk girip
                # interactive'e yükseldi) o sayacı da düş — sızıntı olmasın.
                if ticket is not None and ticket.interactive and not counted:
                    self._interactive_waiting -= 1
                if counted:
                    self._interactive_waiting -= 1
                if ticket is not None:
                    ticket._in_acquire = False

    def release(self) -> None:
        with self._cond:
            self._busy = False
            self._cond.notify_all()


_FETCH_GATE = _PriorityGate()

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
    priority: str = "interactive",
    ticket: GateTicket | None = None,
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

    priority="bulk" toplu çeviri işinden gelen çekimleri işaretler: bekleyen bir
    okuyucu (interactive) varken kapıyı alamazlar (bkz. _PriorityGate).

    Döner: {"title": str, "text": str, "next_url": str | None, "prev_url": ..., ...}
    """
    # E-24: yalnız bilinen öncelikler. Aksi halde "bulk olmayan her şey
    # interactive" sayılır ve örn. "check-updates" yanlışlıkla okuyucu
    # önceliği kazanırdı.
    if priority not in ("interactive", "bulk"):
        raise ValueError(f"Bilinmeyen fetch önceliği: {priority!r}")
    if headless is None:
        headless = os.getenv("FETCH_HEADLESS", "1") != "0"
    delay = 2.0
    last_exc: Exception | None = None
    # Kapı her denemede ayrı alınır; geri-çekilme uykusu kapı DIŞINDA geçer,
    # böylece yeniden deneme beklerken okuyucu (veya başka iş) çekim yapabilir.
    for attempt in range(retries + 1):
        _FETCH_GATE.acquire(priority, ticket)
        try:
            return _fetch_locked(url, headless, timeout_ms)
        except _Transient as exc:
            last_exc = exc
        finally:
            _FETCH_GATE.release()
        if attempt < retries:
            time.sleep(delay)
            delay *= 2
            continue
        raise FetchError(
            str(last_exc) or "Bölüm geçici olarak çekilemedi; biraz sonra deneyin."
        ) from last_exc
    raise FetchError("Bölüm çekilemedi.") from last_exc  # teorik olarak ulaşılmaz


def refresh_clearance(timeout_ms: int = 30000) -> dict:
    """Kalıcı profil/CDP oturumunu yeniden açıp Cloudflare cookie'sini tazeler.

    Hedef, isteğe bağlı `FETCH_CLEARANCE_URL`; aksi halde novelbin ana sayfasıdır.
    Bölüm çekmez ve ayrıştırmaz, yalnızca hafif bir sayfa ziyareti yapar.
    """
    url = os.getenv("FETCH_CLEARANCE_URL", "https://novelbin.com/").strip()
    headless = os.getenv("FETCH_HEADLESS", "1") != "0"
    host = urlparse(url).hostname or "kaynak site"
    _FETCH_GATE.acquire("interactive")  # kullanıcı tetikler → okuyucu önceliği
    try:
        cdp_url = os.getenv("FETCH_CDP_URL", "").strip()
        if cdp_url and _refresh_clearance_via_cdp(cdp_url, url, host, timeout_ms):
            return {"ok": True, "mode": "cdp"}
        _refresh_clearance_via_launch(url, headless, host, timeout_ms)
    finally:
        _FETCH_GATE.release()
    return {"ok": True, "mode": "launch"}


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


def _refresh_clearance_via_launch(
    url: str, headless: bool, host: str, timeout_ms: int
) -> None:
    """Paket Chromium kalıcı profilini açıp hafif sayfa ziyareti yapar."""
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
        context.add_init_script(STEALTH_JS)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            _visit_clearance_page(page, url, host, timeout_ms, _LAUNCH_SOLVE_HINT)
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


def _refresh_clearance_via_cdp(
    cdp_url: str, url: str, host: str, timeout_ms: int
) -> bool:
    """Gerçek Chrome CDP oturumuyla hafif sayfa ziyareti; yoksa False."""
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(cdp_url, timeout=4000)
        except Exception:
            return False
        page = None
        try:
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.new_page()
            _visit_clearance_page(page, url, host, timeout_ms, _CDP_SOLVE_HINT)
            return True
        finally:
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass


def _visit_clearance_page(
    page, url: str, host: str, timeout_ms: int, solve_hint: str
) -> None:
    """İçerik ayrıştırmadan sayfayı ziyaret eder; challenge bitişini bekler."""
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    except PlaywrightTimeout as exc:
        raise FetchError("Cloudflare oturumu yenilenirken sayfa zaman aşımına uğradı.") from exc
    status = resp.status if resp else 0
    if status in CF_ORIGIN_ERRORS:
        raise FetchError(f"Kaynak site ({host}) şu an yanıt vermiyor (HTTP {status}).")
    deadline = time.monotonic() + timeout_ms / 1000
    while _looks_like_challenge(page) and time.monotonic() < deadline:
        page.wait_for_timeout(500)
    if _looks_like_challenge(page):
        raise CloudflareChallenge("Cloudflare doğrulaması geçilemedi. " + solve_hint)


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
        # URL ile sayfa başlığı çelişebiliyor (örn. novelfull slug'ı 1768,
        # gerçek başlık 1788). Sayfanın kendi bölüm başlığı daha güvenilirdir.
        chapter_no = _chapter_no_from_title(title)
        if chapter_no is None:
            chapter_no = _chapter_no(base_url)
    return {
        "title": title,
        "text": text,
        "next_url": next_url,
        "prev_url": prev_url,
        "book_slug": slug,
        "book_title": book_title,
        "chapter_no": chapter_no,
        "cover": _kapak_adresi(soup, base_url),
    }


def _kapak_adresi(soup: BeautifulSoup, base_url: str) -> str | None:
    """Kitap kapaginin adresi — BOLUM sayfasindan, ek istek OLMADAN.

    OLCULDU (2026-09-10, freewebnovel/shadow-slave): `og:image` bolum sayfasinda
    da duruyor ve KITAP sayfasindakiyle birebir ayni adresi veriyor. Yani kapak
    icin ayri bir sayfa cekmek — tek kalici profilden Cloudflare'e bir kez daha
    inmek — tamamen gereksizdi; mevcut cekimden bedavaya gelir.

    Adres MUTLAKLASTIRILIR: goreli birakilirsa okuyucu onu KENDI kokunde arar ve
    kapak sessizce kirik cikar. Kapagi olmayan site None dondurur ve akis bundan
    etkilenmez — kapak susleme, icerik degil.
    """
    for secici in ('meta[property="og:image"]', 'meta[name="twitter:image"]'):
        el = soup.select_one(secici)
        deger = (el.get("content") or "").strip() if el else ""
        if deger:
            return urljoin(base_url, deger)
    return None


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
