"""Bölümü önce DÜZ HTTP ile çek; olmazsa tarayıcı yoluna düş.

Ölçülen bulgu (2026-09-11): freewebnovel'in Cloudflare koruması ANA SAYFADA
var ama BÖLÜM sayfalarında yok. 5 kitap x 12 bölüm denendi (bölüm 4'ten
1880'e), hepsi HTTP 200 döndü ve ayrıştırılan metin önbellektekiyle BİREBİR
aynı çıktı (ör. shadow-slave #381: 5789 karakter, 55 paragraf). Süre 1-8 sn;
aynı bölüm Playwright'la 68 sn sürüyor ve çoğu zaman challenge'a takılıyordu.

Kazanç yalnız hız değil: tarayıcısız yol bulut sunucuda Chromium'u tümden
gereksiz kılıyor (RAM/disk düşer, proxy trafiği ~60 KB/bölüme iner).

Tarayıcı yolu SİLİNMEZ, yedek kalır. Site yarın korumayı bölümlere yayarsa
akış kendiliğinden eski yola düşer — bu yüzden her başarısızlık `None` döner,
istisna fırlatmaz.

Ağa çıkmaz — `requests.get` sahtelenir.
"""
import pytest

from core import fetch

URL = "https://freewebnovel.com/novel/shadow-slave/chapter-382"

# freewebnovel içerik seçicisi `#article` (bkz. fetch.SITES).
DOLU_HTML = (
    "<html><body><div id='article'>"
    + "<p>Uzunca bir paragraf metni burada duruyor.</p>" * 40
    + "</div></body></html>"
)
# Cloudflare bekleme sayfası 200 DÖNEBİLİR — durum kodu tek başına ölçüt değil.
CF_BEKLEME_HTML = "<html><body><h1>Just a moment...</h1></body></html>"


class _SahteYanit:
    def __init__(self, durum, metin):
        self.status_code = durum
        self.text = metin


def _kur(monkeypatch, yanit=None, hata=None, cagrilar=None):
    """`_http_get` sahtelenir — hangi HTTP kütüphanesi kullanıldığı testi
    ilgilendirmez, sözleşme (url, headers, proxies, timeout) sabittir."""

    def sahte_get(url, headers, proxies, timeout):
        if cagrilar is not None:
            cagrilar.append(
                {"url": url, "headers": headers, "proxies": proxies, "timeout": timeout}
            )
        if hata is not None:
            raise hata
        return yanit

    monkeypatch.setattr(fetch, "_http_get", sahte_get)


def test_basarili_cekimde_html_doner(monkeypatch):
    _kur(monkeypatch, yanit=_SahteYanit(200, DOLU_HTML))
    assert fetch._fetch_via_http(URL, fetch._site_for(URL), 30000) == DOLU_HTML


def test_403_none_doner(monkeypatch):
    """CF challenge → tarayıcı yoluna düşülmeli, istisna FIRLATILMAMALI."""
    _kur(monkeypatch, yanit=_SahteYanit(403, CF_BEKLEME_HTML))
    assert fetch._fetch_via_http(URL, fetch._site_for(URL), 30000) is None


def test_200_ama_icerik_yoksa_none(monkeypatch):
    """Durum kodu YETMEZ: CF bekleme sayfası da 200 döner.

    Ölçüt içerik seçicisinin fiilen dolu olmasıdır; boş dönerse yedek yol
    denenmeli, yoksa kullanıcı boş bölüm okur.
    """
    _kur(monkeypatch, yanit=_SahteYanit(200, CF_BEKLEME_HTML))
    assert fetch._fetch_via_http(URL, fetch._site_for(URL), 30000) is None


def test_ag_hatasinda_none(monkeypatch):
    """Bu yol BEST-EFFORT: hata yukarı sızarsa tarayıcı yedeği hiç denenmezdi."""
    _kur(monkeypatch, hata=RuntimeError("baglanti koptu"))
    assert fetch._fetch_via_http(URL, fetch._site_for(URL), 30000) is None


def test_kapali_ayarda_istek_ATILMAZ(monkeypatch):
    """`FETCH_HTTP_FIRST=0` acil çıkış: site korumayı yayarsa yol kapatılabilir."""
    cagrilar = []
    _kur(monkeypatch, yanit=_SahteYanit(200, DOLU_HTML), cagrilar=cagrilar)
    monkeypatch.setenv("FETCH_HTTP_FIRST", "0")

    assert fetch._fetch_via_http(URL, fetch._site_for(URL), 30000) is None
    assert cagrilar == [], "kapalıyken ağa hiç çıkılmamalı"


def test_proxy_requestse_gecirilir(monkeypatch):
    """Sunucuda çıkış proxy'den olmalı; bu yol da `FETCH_PROXY`'yi kullanmalı."""
    cagrilar = []
    _kur(monkeypatch, yanit=_SahteYanit(200, DOLU_HTML), cagrilar=cagrilar)
    monkeypatch.setenv("FETCH_PROXY", "http://kul:parola@proxy.ornek:8000")

    fetch._fetch_via_http(URL, fetch._site_for(URL), 30000)

    assert cagrilar[0]["proxies"] == {
        "http": "http://kul:parola@proxy.ornek:8000",
        "https": "http://kul:parola@proxy.ornek:8000",
    }


def test_proxysizken_proxies_none(monkeypatch):
    cagrilar = []
    _kur(monkeypatch, yanit=_SahteYanit(200, DOLU_HTML), cagrilar=cagrilar)
    monkeypatch.delenv("FETCH_PROXY", raising=False)

    fetch._fetch_via_http(URL, fetch._site_for(URL), 30000)

    assert cagrilar[0]["proxies"] is None


# --- TLS parmak izi: Chrome taklidi ŞART ----------------------------------

def test_http_get_chrome_tls_imzasi_taklit_eder(monkeypatch):
    """Ölçülen arıza (2026-09-11): Linux sunucudan düz `requests` ile
    freewebnovel **403 + "just a moment"** dönüyor; AYNI anda ev makinesinden
    (Windows) 200 geliyordu. Beş farklı ülkeden beş proxy IP'si de 403 verdi
    (0/5), yani IP itibarı DEĞİL. Fark TLS parmak izinde: Linux OpenSSL'in
    JA3 imzası Cloudflare tarafından reddediliyor.

    `curl_cffi` Chrome'un TLS imzasını taklit edince sunucudan da 200 geldi —
    üstelik proxy OLMADAN. Bu yüzden `impersonate` parametresi süsleme değil,
    yolun çalışmasının TEK şartı; kaldırılırsa sunucuda çekim tümden durur.
    """
    yakalanan = {}

    def sahte_curl_get(url, **kw):
        yakalanan.update(kw)
        return _SahteYanit(200, DOLU_HTML)

    monkeypatch.setattr(fetch._curl, "get", sahte_curl_get)

    fetch._http_get(URL, headers={"User-Agent": "x"}, proxies=None, timeout=30)

    assert yakalanan.get("impersonate"), (
        "Chrome TLS taklidi kapalı — sunucudan Cloudflare 403 döner"
    )


# --- Sıralama: düz HTTP ÖNCE, tarayıcı YEDEK -------------------------------

def test_http_basarilisa_tarayici_HIC_acilmaz(monkeypatch):
    """Asıl kazanç bu: bölüm başına tarayıcı doğmaz (68 sn -> 1 sn)."""
    acildi = []
    monkeypatch.setattr(fetch, "_fetch_via_http", lambda *a, **k: DOLU_HTML)
    monkeypatch.setattr(
        fetch, "_fetch_via_launch",
        lambda *a, **k: acildi.append("launch") or DOLU_HTML,
    )
    monkeypatch.setattr(
        fetch, "_fetch_via_cdp",
        lambda *a, **k: acildi.append("cdp") or DOLU_HTML,
    )

    veri = fetch._fetch_locked(URL, headless=True, timeout_ms=30000)

    assert acildi == [], "düz HTTP yettiğinde tarayıcı açılmamalı"
    assert veri["text"]


def test_http_basarisizsa_tarayiciya_duser(monkeypatch):
    """Yedek zincir korunmalı: site korumayı yayarsa akış eski yola düşer."""
    acildi = []
    monkeypatch.setattr(fetch, "_fetch_via_http", lambda *a, **k: None)
    monkeypatch.delenv("FETCH_CDP_URL", raising=False)

    def sahte_launch(*a, **k):
        acildi.append("launch")
        return DOLU_HTML

    monkeypatch.setattr(fetch, "_fetch_via_launch", sahte_launch)

    veri = fetch._fetch_locked(URL, headless=True, timeout_ms=30000)

    assert acildi == ["launch"]
    assert veri["text"]


def test_http_basarisizsa_CDP_varsa_once_CDP(monkeypatch):
    """CDP yedeği düz HTTP'den SONRA ama launch'tan ÖNCE gelmeli (eski sıra)."""
    sira = []
    monkeypatch.setattr(fetch, "_fetch_via_http", lambda *a, **k: None)
    monkeypatch.setenv("FETCH_CDP_URL", "http://127.0.0.1:9222")
    monkeypatch.setattr(
        fetch, "_fetch_via_cdp",
        lambda *a, **k: sira.append("cdp") or DOLU_HTML,
    )
    monkeypatch.setattr(
        fetch, "_fetch_via_launch",
        lambda *a, **k: sira.append("launch") or DOLU_HTML,
    )

    fetch._fetch_locked(URL, headless=True, timeout_ms=30000)

    assert sira == ["cdp"], "CDP yettiğinde launch denenmemeli"
