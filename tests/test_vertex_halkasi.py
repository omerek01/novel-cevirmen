"""Vertex halkası (`vertex/gemini-3.6-flash`): AYNI 3.6-flash, Google Cloud kredisiyle.

ÜCRETLİ (deneme kredisinden düşer). İki yönlü emniyet: ücretsiz zincir ASLA buraya
inmez; seçilince başa geçer ve Vertex çeviremezse ücretsiz halkalara düşülür
(ücretliden ücretsize inmek para harcatmaz). Testler çevrimdışı: istemci sahtelenir.
"""
import pytest

from core import api_durum, kullanim, translate

VERTEX = "vertex/gemini-3.6-flash"


@pytest.fixture(autouse=True)
def _temiz_ortam(monkeypatch):
    for ad in translate.anahtar_degiskenleri():
        monkeypatch.delenv(ad, raising=False)
    translate.anahtar_sogumalarini_temizle()
    translate.anahtar_rotasyonunu_sifirla()
    translate._VERTEX_ISTEMCI.clear()
    monkeypatch.setattr(translate.time, "sleep", lambda s: None)
    yield
    translate._VERTEX_ISTEMCI.clear()


class _Meta:
    prompt_token_count = 5000
    candidates_token_count = 4000
    thoughts_token_count = 3000


class _Yanit:
    text = '{"translation": "tamam"}'
    usage_metadata = _Meta()


class _APIHatasi(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


def _sahte_istemci(monkeypatch, sonuc, cagrilar=None):
    class _Modeller:
        def generate_content(self, **kw):
            if cagrilar is not None:
                cagrilar.append(kw)
            if isinstance(sonuc, Exception):
                raise sonuc
            return sonuc

    class _Istemci:
        def __init__(self, **kw):
            if cagrilar is not None:
                cagrilar.append({"kurulum": kw})
            self.models = _Modeller()

    monkeypatch.setattr(translate.genai, "Client", _Istemci)
    monkeypatch.setattr(translate.genai_errors, "APIError", _APIHatasi)


def _fabrika_kullanilmamali(indeks=0):
    raise AssertionError("Vertex halkası Gemini anahtar havuzuna dokunmamalı")


_fabrika_kullanilmamali.anahtar_sayisi = 1


def test_ucretsiz_zincir_ASLA_vertexe_inmez():
    """Sessiz harcamanın kapısı kapalı: hiçbir ücretsiz seçimin zincirinde yok."""
    assert VERTEX not in translate.DEFAULT_MODELS
    for ad in translate.SECILEBILIR_ADLAR:
        if translate._ucretli_modeli(ad):
            continue
        assert not any(translate._ucretli_modeli(m) for m in translate.zincir_kur(ad))


def test_secilince_basa_gecer_ucretsizler_yedek():
    zincir = translate.zincir_kur(VERTEX)
    assert zincir == (VERTEX, *translate.DEFAULT_MODELS)


def test_ucretli_isaretli_ve_notunda_soyleniyor():
    secenek = [m for m in translate.SECILEBILIR_MODELLER if m["ad"] == VERTEX][0]
    assert secenek["ucretli"] and "ÜCRETLİ" in secenek["not"]


def test_ayni_gemini_modeli_ve_ayni_ayarlar(monkeypatch):
    """Vertex AYNI 3.6-flash'ı AYNI ayarlarla çağırmalı; iki kopya ayrışırdı."""
    monkeypatch.setenv("VERTEX_PROJE", "proje-x")
    cagrilar = []
    _sahte_istemci(monkeypatch, _Yanit(), cagrilar)
    yanit, model = translate._generate_with_fallback(_fabrika_kullanilmamali, (VERTEX,), "p")
    assert model == VERTEX and yanit.text == _Yanit.text
    kurulum = cagrilar[0]["kurulum"]
    assert kurulum["vertexai"] is True and kurulum["project"] == "proje-x"
    assert kurulum["location"] == "global"
    istek = cagrilar[1]
    assert istek["model"] == "gemini-3.6-flash"
    assert istek["config"] == translate._gemini_yapilandirmasi(
        translate.SYSTEM_INSTRUCTION, translate.MAX_OUTPUT_TOKENS
    )


def test_harcama_gostergesine_yazilir_gemini_kaydina_yazilmaz(monkeypatch):
    """Ücretli: token harcama göstergesine gider (düşünme dahil). Gemini anahtar
    tablosuna yazılsaydı anahtar #1'in satırına düşerdi."""
    monkeypatch.setenv("VERTEX_PROJE", "proje-x")
    _sahte_istemci(monkeypatch, _Yanit())
    harcama, kayit = [], []
    monkeypatch.setattr(kullanim, "ekle", lambda *a, **k: harcama.append(a))
    monkeypatch.setattr(api_durum, "istek_kaydet", lambda *a, **k: kayit.append(a))
    translate._generate_with_fallback(_fabrika_kullanilmamali, (VERTEX,), "p")
    assert harcama == [(VERTEX, 5000, 7000)]
    assert kayit == []
    assert VERTEX in kullanim.FIYAT


def test_proje_yoksa_halka_anahtarsiz_atlanir(monkeypatch):
    _sahte_istemci(monkeypatch, AssertionError("istek atılmamalı"))
    with pytest.raises(translate.TranslateError) as hata:
        translate._generate_with_fallback(_fabrika_kullanilmamali, (VERTEX,), "p")
    assert str(hata.value) == translate.ANAHTAR_YOK_MESAJI


@pytest.mark.parametrize("kod", [429, 500, 503])
def test_yogunluk_gecici_sayilir(monkeypatch, kod):
    monkeypatch.setenv("VERTEX_PROJE", "proje-x")
    _sahte_istemci(monkeypatch, _APIHatasi(kod))
    with pytest.raises(translate.TranslateError) as hata:
        translate._generate_with_fallback(_fabrika_kullanilmamali, (VERTEX,), "p")
    assert "meşgul" in str(hata.value)


def test_izin_yoksa_mesgul_demez(monkeypatch):
    monkeypatch.setenv("VERTEX_PROJE", "proje-x")
    _sahte_istemci(monkeypatch, _APIHatasi(403))
    with pytest.raises(translate.TranslateError) as hata:
        translate._generate_with_fallback(_fabrika_kullanilmamali, (VERTEX,), "p")
    assert "meşgul" not in str(hata.value)


def test_vertex_duserse_ucretsiz_halkaya_inilir(monkeypatch):
    """Ücretliden ücretsize iniş: okuma durmaz, para da harcanmaz."""
    monkeypatch.setenv("VERTEX_PROJE", "proje-x")
    _sahte_istemci(monkeypatch, _APIHatasi(503))

    class _Gemini:
        class models:
            @staticmethod
            def generate_content(**kw):
                return _Yanit()

    def fabrika(indeks=0):
        return _Gemini()

    fabrika.anahtar_sayisi = 1
    _, model = translate._generate_with_fallback(
        fabrika, (VERTEX, "gemini-3.6-flash"), "p"
    )
    assert model == "gemini-3.6-flash"
