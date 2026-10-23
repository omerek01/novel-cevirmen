"""Karakter defteri SEÇİLİ çeviri modeliyle koşar (2026-10-23, kullanıcı isteği).

Önceki durum: defter modeli yalnız `DEFTER_MODELI` ortam değişkeninden ya da
`VARSAYILAN_MODEL`den geliyordu. Ölçülen sonuç (canlı `defter_isleme`, 1117
bölüm): kullanıcı okuyucudan `vertex/gemini-4-argon` seçmiş olduğu hâlde defterin
TAMAMI `vertex/gemini-3.8-flash` ile işlenmişti — 13,26M giriş + 3,08M çıkış
token, 21,49 $. Yani ayarlar panelindeki model seçimi defteri HİÇ etkilemiyordu
ve kullanıcı iki ayrı modele para ödediğini hiçbir yerden okuyamıyordu.

Yeni öncelik: SEÇİLİ çeviri modeli > `DEFTER_MODELI` > `VARSAYILAN_MODEL`.
Seçim `ceviri_asamalari` ile aynı kuralla okunur (kayıtlı ayar önce), yani
okuyucudan yapılan tek seçim hem çeviriyi hem defteri sürükler.

Maliyet uyarısı testte de duruyor: Argon 3.8'in ~2,7 katı fiyatlı, yani aynı
defter koşusu Argon seçiliyken ~57 $ eder. Seçimi takip etmek kullanıcının
kararıdır; bu testler yalnız kararın SESSİZCE kaybolmamasını tutar.
"""
import pytest

from core import cache, karakter_defteri as kd
from core import settings, translate


@pytest.fixture
def sema():
    """`bolum_isle` `chapters`a bakıyor; geçici DB'de tablo henüz yok."""
    cache.get_chapter("https://yok/")


def test_secili_ceviri_modeli_deftere_gecer():
    settings.set(translate.MODEL_AYAR_ANAHTARI, "vertex/gemini-4-argon")
    assert kd.model_adi() == "vertex/gemini-4-argon"


def test_secim_ortam_degiskenini_EZER(monkeypatch):
    """Okuyucudan yapılan seçim kazanır: yoksa düğme "Argon" derken defter
    sessizce başka bir modele para harcamaya devam ederdi."""
    monkeypatch.setenv("DEFTER_MODELI", "vertex/gemini-3.6-flash")
    settings.set(translate.MODEL_AYAR_ANAHTARI, "vertex/gemini-4-argon")
    assert kd.model_adi() == "vertex/gemini-4-argon"


def test_secim_yoksa_ortam_degiskeni_gecerli(monkeypatch):
    monkeypatch.setenv("DEFTER_MODELI", "vertex/gemini-3.6-flash")
    assert kd.model_adi() == "vertex/gemini-3.6-flash"


def test_secim_ve_ortam_yoksa_varsayilan(monkeypatch):
    monkeypatch.delenv("DEFTER_MODELI", raising=False)
    assert kd.model_adi() == kd.VARSAYILAN_MODEL


def test_taninmayan_secim_SESSIZCE_yok_sayilir(monkeypatch):
    """Ayar tablosunda elle bozulmuş bir değer defterin her çağrısını 404'e
    çarptırırdı ve arıza "model meşgul" kılığına girerdi. `zincir_kur` aynı
    kuralı uyguluyor; defter de aynı yerden geçmeli."""
    monkeypatch.delenv("DEFTER_MODELI", raising=False)
    settings.set(translate.MODEL_AYAR_ANAHTARI, "uydurma-model")
    assert kd.model_adi() == kd.VARSAYILAN_MODEL


def test_ayar_okunamazsa_varsayilana_duser(monkeypatch):
    """Kilitli veritabanı defteri durdurmamalı — `ceviri_asamalari._kayit` deseni."""
    import sqlite3

    def patlat(*a, **k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.delenv("DEFTER_MODELI", raising=False)
    monkeypatch.setattr(settings, "get", patlat)
    assert kd.model_adi() == kd.VARSAYILAN_MODEL


def test_bolum_isle_secimi_SORAR(sema, monkeypatch):
    """Seçim yalnız `model_adi()`de kalmamalı: işleme yolu onu okumalı."""
    soruldu = []
    monkeypatch.setattr(kd, "model_adi", lambda: soruldu.append(1) or "vertex/gemini-4-argon")
    kd.bolum_isle("yok-boyle-kitap", 1, kuru=True)
    assert soruldu == [1]


def test_acik_model_argumani_secimi_EZER(sema, monkeypatch):
    """Betikler (`scripts/karakter_defteri.py --model`) hâlâ zorlayabilir:
    ölçüm koşusu okuyucunun seçimine bağlı kalırsa tekrarlanamaz olurdu —
    açık argüman verildiğinde ayara HİÇ bakılmaz."""
    def patlat():
        raise AssertionError("açık model verilmişken ayar okunmamalı")

    monkeypatch.setattr(kd, "model_adi", patlat)
    kd.bolum_isle("yok-boyle-kitap", 1, kuru=True, model="vertex/gemini-3.6-flash")
