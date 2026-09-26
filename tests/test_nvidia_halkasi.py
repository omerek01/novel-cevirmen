"""NVIDIA halkası (`z-ai/glm-5.3`): Google DIŞI, ÜCRETSİZ son halka (2026-09-26).

Kullanıcı kararı + ölçüm (`scratch/nvidia_kiyas.py`, 3 gerçek bölüm): oran medyanı
0,966, hizalama 3/3, sıfır sözlük ihlali; bölüm başına 2-3 dk. Zincirin öteki
halkaları tek sağlayıcının (Google) kaderini paylaşıyor — bu halka onu kırar.
Testler çevrimdışı: `httpx.stream` sahtelenir.
"""
import json

import httpx
import pytest

from core import api_durum, translate

GLM = "z-ai/glm-5.3"


@pytest.fixture(autouse=True)
def _temiz_ortam(monkeypatch):
    """`server` importu `.env`i sürece yüklüyor: geliştiricinin anahtarı görünmesin."""
    for ad in translate.anahtar_degiskenleri():
        monkeypatch.delenv(ad, raising=False)
    translate.anahtar_sogumalarini_temizle()
    translate.anahtar_rotasyonunu_sifirla()
    monkeypatch.setattr(translate.time, "sleep", lambda s: None)
    yield
    translate.anahtar_sogumalarini_temizle()


class _SahteAkis:
    """`httpx.stream(...)` bağlam yöneticisinin bu yolda kullanılan yüzeyi."""

    def __init__(self, kod=200, satirlar=(), govde="", hata=None):
        self.status_code = kod
        self._satirlar = list(satirlar)
        self.text = govde
        self._hata = hata

    def __enter__(self):
        if self._hata:
            raise self._hata
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.text.encode()

    def iter_lines(self):
        yield from self._satirlar


def _akis_satirlari(*parcalar):
    satirlar = [
        "data: " + json.dumps({"choices": [{"delta": {"content": p}}]}) for p in parcalar
    ]
    return [": keep-alive", *satirlar, "data: [DONE]"]


def _sahte_stream(monkeypatch, akis, istekler=None):
    def stream(method, url, **kw):
        if istekler is not None:
            istekler.append(kw)
        return akis

    monkeypatch.setattr(translate.httpx, "stream", stream)


def _fabrika_kullanilmamali(indeks=0):
    raise AssertionError("NVIDIA halkası Gemini fabrikasına dokunmamalı")


_fabrika_kullanilmamali.anahtar_sayisi = 1


# ---------- zincirdeki yeri ----------

def test_glm_zincirin_SON_halkasi():
    """Sonda: 3.6-flash ölçümde daha iyi ve glm bölüm başına 2-3 dk sürüyor; yalnız
    Gemini halkalarının hepsi elendiğinde inilmeli."""
    assert translate.DEFAULT_MODELS[-1] == GLM
    assert all(translate.gemini_modeli(m) for m in translate.DEFAULT_MODELS[:-1])


def test_glm_ucretsiz_ve_secilebilir():
    """Seçilebilir listede ÜCRETSİZ işaretli: ücretli rozeti taşısaydı kullanıcı
    seçmekten kaçınırdı; taşımaması da sürpriz harcama riski olmadığı içindir."""
    secenek = [m for m in translate.SECILEBILIR_MODELLER if m["ad"] == GLM]
    assert len(secenek) == 1
    assert not secenek[0].get("ucretli")
    assert "Ücretsiz" in secenek[0]["not"]


def test_glm_secilince_basa_gecer_gemini_yedek_kalir():
    zincir = translate.zincir_kur(GLM)
    assert zincir[0] == GLM
    assert set(zincir) == set(translate.DEFAULT_MODELS)
    assert len(zincir) == len(set(zincir))


def test_kunye_motoru_nvidia():
    """Rozet "GEMINI ile çevrildi" dememeli (Mistral dersi)."""
    assert translate.motor_adi(GLM) == "nvidia"
    assert translate.motor_adi(f"gemini-3.6-flash + {GLM}") == "gemini + nvidia"


def test_nvidia_anahtari_kapidan_gecirir(monkeypatch):
    assert not translate.ceviri_anahtari_var_mi(None)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    assert translate.ceviri_anahtari_var_mi(None)
    assert "NVIDIA_API_KEY" in translate.anahtar_degiskenleri()


# ---------- çağrı ----------

def test_akis_parcalari_birlesir_ve_dusunme_low_gider(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    istekler = []
    _sahte_stream(
        monkeypatch, _SahteAkis(satirlar=_akis_satirlari('{"translation": ', '"merhaba"}')),
        istekler,
    )
    yanit, model = translate._generate_with_fallback(_fabrika_kullanilmamali, (GLM,), "p")
    assert model == GLM
    assert yanit.text == '{"translation": "merhaba"}'
    govde = istekler[0]["json"]
    assert govde["model"] == GLM and govde["stream"] is True
    assert govde["reasoning_effort"] == "low"  # kullanıcı isteği


def test_anahtarsiz_halka_sessizce_atlanir(monkeypatch):
    """Anahtar yoksa halka ANAHTARSIZ sayılır; Gemini de yoksa mesaj "anahtar yok"
    der, "meşgul" DEMEZ."""
    monkeypatch.setattr(translate.httpx, "stream", lambda *a, **k: pytest.fail("istek atıldı"))
    with pytest.raises(translate.TranslateError) as hata:
        translate._generate_with_fallback(_fabrika_kullanilmamali, (GLM,), "p")
    assert str(hata.value) == translate.ANAHTAR_YOK_MESAJI


@pytest.mark.parametrize("kod", [429, 500, 503])
def test_yogunluk_gecici_sayilir_ve_TEK_deneme(monkeypatch, kod):
    """429 bilerek geçici: Google'ın kota gövdesi ayrıştırılmaz, anahtar soğutulmaz.
    TEK deneme — başarısız bir NVIDIA denemesi dakikalar sürebiliyor."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    istekler = []
    _sahte_stream(monkeypatch, _SahteAkis(kod=kod, govde="yogun"), istekler)
    with pytest.raises(translate.TranslateError) as hata:
        translate._generate_with_fallback(_fabrika_kullanilmamali, (GLM,), "p")
    assert "meşgul" in str(hata.value)
    assert len(istekler) == 1


def test_tasima_hatasi_gecici(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    _sahte_stream(monkeypatch, _SahteAkis(hata=httpx.ReadTimeout("yavaş")))
    with pytest.raises(translate.TranslateError) as hata:
        translate._generate_with_fallback(_fabrika_kullanilmamali, (GLM,), "p")
    assert "meşgul" in str(hata.value)


def test_anahtar_reddi_meşgul_demez(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    _sahte_stream(monkeypatch, _SahteAkis(kod=401, govde="unauthorized"))
    with pytest.raises(translate.TranslateError) as hata:
        translate._generate_with_fallback(_fabrika_kullanilmamali, (GLM,), "p")
    assert "meşgul" not in str(hata.value)


def test_gemini_tukenince_glm_e_inilir(monkeypatch):
    """Asıl kazanç: Gemini halkalarının TAMAMI düştüğünde çeviri durmaz."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    _sahte_stream(monkeypatch, _SahteAkis(satirlar=_akis_satirlari('{"translation": "x"}')))

    def gemini_yok(indeks=0):  # Gemini anahtarı yok -> Gemini halkaları anahtarsız
        raise translate.TranslateError(translate.ANAHTAR_YOK_MESAJI)

    gemini_yok.anahtar_sayisi = 1
    _, model = translate._generate_with_fallback(gemini_yok, translate.DEFAULT_MODELS, "p")
    assert model == GLM


def test_nvidia_cagrisi_gemini_kaydina_YAZILMAZ(monkeypatch):
    """Kayıt Gemini ANAHTAR x model tablosudur; NVIDIA çağrısı oraya yazılsaydı
    Gemini anahtarı #1'in satırına düşerdi."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    _sahte_stream(monkeypatch, _SahteAkis(satirlar=_akis_satirlari('{"translation": "x"}')))
    kayitlar = []
    monkeypatch.setattr(api_durum, "istek_kaydet", lambda *a, **k: kayitlar.append(a))
    translate._generate_with_fallback(_fabrika_kullanilmamali, (GLM,), "p")
    assert kayitlar == []
    assert not translate.gemini_modeli(GLM)
