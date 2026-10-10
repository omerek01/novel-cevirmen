"""Ürün akışında analiz ayrımı ve başarısız denemenin kanıtı."""
import json

import pytest
from core import translate, cache, pipeline, ceviri_baglam, ceviri_izleri
from test_roman_baglam import yanit, veri, KAYNAK


def kur(monkeypatch):
    monkeypatch.setenv("CEVIRI_ANALIZ", "1")
    monkeypatch.setenv("CEVIRI_KALITE", "0")
    monkeypatch.setattr(translate, "_gemini_fabrikasi", lambda key: object())


def test_analiz_uretimden_ayri_ve_ham_ceviri_kayitli(monkeypatch):
    kur(monkeypatch); cagrilar = []
    def uret(factory, models, user, **kw):
        system = kw.get("system", translate.SYSTEM_INSTRUCTION); cagrilar.append((system, user))
        if system == ceviri_baglam.ANALIZ_TALIMATI:
            return yanit(veri()), "vertex/gemini-3.6-flash"
        assert "detected_terms" not in system
        assert "Sunny köprüyü geçti." in user
        return yanit({"translation": "[[1]] Sunny Kül Köprüsü'nden geçti. Ordu seferine katıldı."}), "vertex/gemini-3.6-flash"
    monkeypatch.setattr(translate, "_generate_with_fallback", uret)
    r = translate.translate_chapter(KAYNAK, "test", models=("vertex/gemini-3.6-flash",),
                                    book_slug="kitap", bolum_url="test://k/3", bolum_no=3)
    assert len(cagrilar) == 2
    assert r["detected_terms"] == {"Ash Bridge": "Kül Köprüsü"}
    iz = ceviri_izleri.iz_oku("test://k/3")[0]["veri"]
    assert iz["durum"] == "tamamlandi"
    assert iz["ham_ceviri"] == r["translation"]
    assert iz["analiz"]["terimler"][0]["kaynak"] == "Ash Bridge"
    assert len(iz["cagrilar"]) == 2
    assert iz["cagrilar"][1]["finish_reason"] == ["STOP"]


def test_onceki_ozet_tembel_uretilir_ve_tekrar_kullanilir(monkeypatch):
    kur(monkeypatch); kaynak = "Sunny crossed the Ash Bridge."
    calls = []
    def uret(factory, models, user, **kw):
        s = kw.get("system"); calls.append(s)
        if s in (ceviri_baglam.OZET_TALIMATI, ceviri_baglam.ANALIZ_TALIMATI):
            v = veri()
            if s == ceviri_baglam.OZET_TALIMATI: v["terimler"] = []
            return yanit(v), "model"
        return yanit({"translation": "[[1]] Sunny Kül Köprüsü'nden geçti."}), "model"
    monkeypatch.setattr(translate, "_generate_with_fallback", uret)
    onceki = {"url": "test://k/2", "book_slug": "kitap", "chapter_no": 2, "source": kaynak}
    for _ in range(2):
        translate.translate_chapter(kaynak, "test", models=("model",), book_slug="kitap",
                                    bolum_url="test://k/3", bolum_no=3, onceki_bolum=onceki)
    assert calls.count(ceviri_baglam.OZET_TALIMATI) == 1
    assert ceviri_izleri.iz_oku("test://k/3")[0]["veri"]["onceki_bolum"]["chapter_no"] == 2


def test_basarisiz_analiz_iz_birakir_chapter_degismez(monkeypatch):
    kur(monkeypatch)
    cache.save_chapter("test://k/3", {"book_slug": "kitap", "translation": "Eski çeviri.", "source": KAYNAK})
    monkeypatch.setattr(translate, "_generate_with_fallback", lambda *a, **k: (yanit(veri(), "MAX_TOKENS"), "model"))
    with pytest.raises(translate.TranslateError):
        translate.translate_chapter(KAYNAK, "test", book_slug="kitap", bolum_url="test://k/3")
    assert cache.get_chapter("test://k/3")["translation"] == "Eski çeviri."
    assert ceviri_izleri.iz_oku("test://k/3")[0]["veri"]["durum"] == "basarisiz"


def test_analiz_kapali_eski_istem_birebir_korunur(monkeypatch):
    kur(monkeypatch); monkeypatch.setenv("CEVIRI_ANALIZ", "0")
    def uret(*a, **k):
        assert not k.get("system")
        return yanit({"translation": "[[1]] Sunny Kül Köprüsü'nden geçti.", "detected_names": [], "detected_terms": {}}), "model"
    monkeypatch.setattr(translate, "_generate_with_fallback", uret)
    translate.translate_chapter("Sunny crossed the Ash Bridge.", "test", models=("model",))


def test_pipeline_yeni_baglami_ve_iz_urlunu_tasir(monkeypatch):
    kur(monkeypatch)
    url = "https://ornek.test/kitap/chapter-3"
    cache.save_chapter(url, {"book_slug": "kitap", "chapter_no": 3, "source": KAYNAK,
                             "translation": "Eski çeviri."})
    cache.save_chapter("prev", {"book_slug": "kitap", "chapter_no": 2, "source": KAYNAK,
                                "translation": "Önceki çeviri."})
    monkeypatch.setattr(translate, "ceviri_anahtari_var_mi", lambda k: True)
    monkeypatch.setattr(pipeline, "_anlam_tanimlari", lambda slug: None)
    def cevir(text, **kwargs):
        assert kwargs["bolum_url"] == url
        assert kwargs["book_slug"] == "kitap"
        assert kwargs["onceki_bolum"]["chapter_no"] == 2
        return {"translation": "Yeni çeviri.", "source": text, "detected_names": [], "detected_terms": {}, "chunk_count": 1}
    monkeypatch.setattr(pipeline, "translate_chapter", cevir)
    r = pipeline.get_or_translate(url, "test", refresh=True, advance_position=False)
    assert r["translation"] == "Yeni çeviri."


def test_pipeline_onceki_turkce_baglami_da_baska_kitaptan_almaz(monkeypatch):
    kur(monkeypatch)
    url = "https://ornek.test/kitap/chapter-3"
    cache.save_chapter("wrong", {"book_slug": "baska", "chapter_no": 2,
                                "source": KAYNAK, "translation": "YANLIŞ KİTAP"})
    cache.save_chapter(url, {"book_slug": "kitap", "chapter_no": 3, "prev_url": "wrong",
                             "source": KAYNAK, "translation": "Eski çeviri."})
    monkeypatch.setattr(translate, "ceviri_anahtari_var_mi", lambda k: True)
    monkeypatch.setattr(pipeline, "_anlam_tanimlari", lambda slug: None)
    def cevir(text, **kwargs):
        assert kwargs["prev_context"] == ""
        assert kwargs["onceki_bolum"] is None
        return {"translation": "Yeni çeviri.", "source": text, "detected_names": [], "detected_terms": {}, "chunk_count": 1}
    monkeypatch.setattr(pipeline, "translate_chapter", cevir)
    pipeline.get_or_translate(url, "test", refresh=True, advance_position=False)
