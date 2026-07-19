"""Manga bölümünü WEB'den çek: bölüm URL'sinden sayfa görsellerini çıkar + indir.

asurascans gibi manga sitelerinden okuma. Novel `fetch.py`'nin Playwright + kapı +
kalıcı profil (Cloudflare çözülü) altyapısını paylaşır; ama METİN değil, sayfa
GÖRSELLERİNİ çıkarır. Sezgi (site-bağımsız): büyük görselleri DOM sırasında topla,
URL DİZİNİNE göre grupla, en çok görsel içeren dizin = okuyucu (kapak/avatar/UI ayrı
dizinde kalır), o dizini doğal sırayla al. İndirme tarayıcı context'iyle (çerez+referer)
yapılır. Çıktı import_book.import_manga_url ile manga:// sayfalarına sahnelenir.
"""
from __future__ import annotations

import os
import time
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from .fetch import (
    PROFILE_DIR,
    STEALTH_JS,
    CloudflareChallenge,
    FetchError,
    GateTicket,
    _FETCH_GATE,
)

# Bilinen manga siteleri (URL tab'ı bunları manga akışına yönlendirir). Genişletilebilir.
MANGA_SITES = ("asurascans.com", "asuracomic.net", "asurascans", "reaperscans", "flamecomics", "mangadex.org")

_EXTRACT_JS = """
() => {
  const out = [];
  for (const i of document.querySelectorAll('img')) {
    const u = i.currentSrc || i.src || i.getAttribute('data-src') || '';
    if (!/\\.(webp|jpe?g|png)(\\?|$)/i.test(u)) continue;
    out.push({ u, w: i.naturalWidth || 0, h: i.naturalHeight || 0 });
  }
  return out;
}
"""


def is_manga_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(s in host for s in MANGA_SITES)


def _basename_noext(u: str) -> str:
    return u.split("?")[0].rsplit("/", 1)[-1].rsplit(".", 1)[0]


def _pick_page_images(imgs: list[dict]) -> list[str]:
    """Sayfa akışını izole et. Sayfalar SAYI-adlı bir dizinde (…/<bölüm>/001.webp);
    reklam/öneri gridleri hash-adlı ayrı dizinde (…/profiles/<hash>.webp) ve genelde
    DAHA ÇOK görsel içerir. Bu yüzden "en kalabalık dizin" değil, SAYI-adlı görseli en
    çok olan dizin seçilir; içinden yalnız sayı-adlılar (araya giren reklam elenir)."""
    import re
    from collections import OrderedDict

    groups: "OrderedDict[str, list[str]]" = OrderedDict()
    seen: set[str] = set()
    for it in imgs:
        base = it["u"].split("?")[0]
        if it["w"] < 400 or base in seen:  # küçük (ikon/avatar) veya tekrar → atla
            continue
        seen.add(base)
        d = base.rsplit("/", 1)[0]
        groups.setdefault(d, []).append(it["u"])
    if not groups:
        return []

    def numeric_count(urls):
        return sum(1 for u in urls if _basename_noext(u).isdigit())

    # Sayı-adlı en çok olan dizin (eşitlikte daha kalabalık) = gerçek sayfalar.
    best = max(groups.values(), key=lambda urls: (numeric_count(urls), len(urls)))
    numeric = [u for u in best if _basename_noext(u).isdigit()]
    chosen = numeric if len(numeric) >= 3 else best  # sayısal desen yoksa dizini olduğu gibi

    def key(u):
        name = u.split("?")[0].rsplit("/", 1)[-1]
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]

    return sorted(chosen, key=key)


def _title_from(page, url: str) -> str:
    t = (page.title() or "").strip()
    for suf in (" - Read Online", " | Asura Scans", " - Asura Scans"):
        if suf in t:
            t = t.split(suf)[0]
    return t or urlparse(url).path.strip("/").replace("/", "-") or "Manga"


def fetch_manga_chapter(url: str, priority: str = "interactive", ticket: GateTicket | None = None) -> dict:
    """Manga bölüm URL'sinden sayfaları çek. Döner: {title, images:[bytes...]}.

    Kapı (gate) ile serileşir; kalıcı profil (CF çözülü) + stealth kullanır. Görseller
    tarayıcı context'iyle (çerez+referer) indirilir → hotlink koruması aşılır."""
    headless = os.getenv("FETCH_HEADLESS", "1") != "0"
    _FETCH_GATE.acquire(priority, ticket)
    try:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 2000},
            )
            try:
                ctx.add_init_script(STEALTH_JS)
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                except Exception as exc:
                    raise FetchError(f"Manga sayfası açılamadı: {exc}") from exc
                time.sleep(2)
                body = (page.inner_text("body")[:300] if page.query_selector("body") else "").lower()
                if "checking your browser" in body or "cloudflare" in body and len(body) < 200:
                    raise CloudflareChallenge("Cloudflare doğrulaması gerekiyor (manga).")
                # lazy-load: sona kadar kaydır
                for _ in range(14):
                    page.mouse.wheel(0, 3000)
                    time.sleep(0.35)
                time.sleep(1.2)
                imgs = page.evaluate(_EXTRACT_JS)
                urls = _pick_page_images(imgs)
                if not urls:
                    raise FetchError("Manga sayfası görselleri bulunamadı (site yapısı desteklenmiyor olabilir).")
                title = _title_from(page, url)
                images: list[bytes] = []
                for u in urls:
                    try:
                        r = ctx.request.get(u, headers={"referer": url}, timeout=30000)
                        if r.status == 200:
                            images.append(r.body())
                    except Exception:
                        continue  # tek görsel düşerse diğerleri devam
                if not images:
                    raise FetchError("Manga sayfaları indirilemedi.")
                return {"title": title, "images": images}
            finally:
                ctx.close()
    finally:
        _FETCH_GATE.release()
