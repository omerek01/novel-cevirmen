"""`FETCH_PROXY`: çekim trafiğini residential proxy üzerinden çıkarır.

Neden ölçülerek gerekli: Cloudflare 2026 itibarıyla öncelikli olarak IP
itibarına bakıyor ve veri merkezi ASN'lerini otomatik en yüksek risk skoruna
alıyor — parmak izi taklidi bunu kurtarmıyor (ölçüm: VPS IP'sinde stealth
Playwright, challenge'ların ~%5'ini geçiyor). Projenin buluta taşınmasının
önündeki TEK engel buydu; çeviri ve önbellek yolları IP itibarına duyarlı değil.

Ev makinesinde değişken BOŞTUR ve akış bugünkü gibi doğrudan çıkar — varsayılan
davranış değişmez.

Ağa çıkmaz — Playwright sahtelenir.
"""
import pathlib

from core import fetch


class _SahteBaglam:
    def __init__(self):
        self.scriptler = []

    def add_init_script(self, s):
        self.scriptler.append(s)


class _SahteChromium:
    def __init__(self):
        self.kwargs = {}

    def launch_persistent_context(self, **kw):
        self.kwargs = kw
        return _SahteBaglam()


class _SahtePlaywright:
    def __init__(self):
        self.chromium = _SahteChromium()


def test_proxy_ayarsizken_none(monkeypatch):
    monkeypatch.delenv("FETCH_PROXY", raising=False)
    assert fetch._proxy_ayari() is None


def test_proxy_bos_dizeyken_none(monkeypatch):
    """`.env`'de anahtar var ama değeri boş — ayarlanmamış sayılır."""
    monkeypatch.setenv("FETCH_PROXY", "   ")
    assert fetch._proxy_ayari() is None


def test_kimlik_bilgisi_AYRI_alanlara_gider(monkeypatch):
    """Playwright `server` içine gömülü kullanıcı/parolayı YOK SAYAR.

    URL'de bırakılırsa proxy kimlik doğrulaması sessizce başarısız olur ve
    arıza "Cloudflare geçilemedi" kılığına girer — yanlış yerde aranır.
    """
    monkeypatch.setenv("FETCH_PROXY", "http://kul:parola@proxy.ornek:8000")
    assert fetch._proxy_ayari() == {
        "server": "http://proxy.ornek:8000",
        "username": "kul",
        "password": "parola",
    }


def test_kimliksiz_proxy_sadece_server_verir(monkeypatch):
    monkeypatch.setenv("FETCH_PROXY", "http://proxy.ornek:8000")
    assert fetch._proxy_ayari() == {"server": "http://proxy.ornek:8000"}


def test_yuzde_kodlu_parola_cozulur(monkeypatch):
    """Parolada `@` ya da `:` varsa `.env`'de yüzde-kodlu yazılır."""
    monkeypatch.setenv("FETCH_PROXY", "http://kul:a%40b@proxy.ornek:8000")
    assert fetch._proxy_ayari()["password"] == "a@b"


def test_baglam_proxyi_playwrighte_gecirir(monkeypatch):
    monkeypatch.setenv("FETCH_PROXY", "http://kul:parola@proxy.ornek:8000")
    p = _SahtePlaywright()

    fetch._baglam_ac(p, headless=True)

    assert p.chromium.kwargs["proxy"] == {
        "server": "http://proxy.ornek:8000",
        "username": "kul",
        "password": "parola",
    }


def test_proxysiz_baglam_none_gecirir(monkeypatch):
    """Ev makinesi: proxy alanı None olmalı, Playwright onu yok sayar."""
    monkeypatch.delenv("FETCH_PROXY", raising=False)
    p = _SahtePlaywright()

    fetch._baglam_ac(p, headless=True)

    assert p.chromium.kwargs["proxy"] is None


def test_baglam_stealth_scriptini_kurar(monkeypatch):
    """Ortaklaştırma sırasında kaybolmamalı — CF'i geçiren parça bu."""
    monkeypatch.delenv("FETCH_PROXY", raising=False)
    p = _SahtePlaywright()

    ctx = fetch._baglam_ac(p, headless=True)

    assert ctx.scriptler == [fetch.STEALTH_JS]


def test_baglam_TEK_yerde_acilir():
    """Statik tel tuzağı: `launch_persistent_context` tek çağrı noktası.

    İkinci bir çağrı eklenirse proxy oraya geçirilmeyi unutulabilir. Clearance
    yolunda unutulursa Cloudflare cookie'si YANLIŞ IP'yle alınıp kalıcı profile
    yazılır ve sonraki proxy'li çekimlerde sessizce reddedilir — arıza proxy'de
    değil, cookie'de olur ve teşhisi zordur.
    """
    kaynak = pathlib.Path("app/core/fetch.py").read_text(encoding="utf-8")
    assert kaynak.count("launch_persistent_context(") == 1
