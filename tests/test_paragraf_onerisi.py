"""Okuyucudan tek paragraf önerisi (Ö2 yeniden çeviri, Ö4 hedefli onarım) ve kabul."""
from __future__ import annotations

import json

import pytest

from core import cache, translate

URL = "https://ornek.test/paragraf-kitap/3"


def _client():
    from fastapi.testclient import TestClient

    import server

    return TestClient(server.app)


def _bolum(kalite=None, kaynak="One.\n\nTwo.\n\nThree."):
    cache.save_chapter(URL, {
        "book_slug": "paragraf-kitap", "book_title": "P", "title": "3", "chapter_no": 3,
        "translation": "Bir.\n\nİki.\n\nÜç.", "source": kaynak,
        "ceviri_kalitesi": kalite,
    })


def test_yeniden_oneri_kaydetmez_ve_baglam_verir(monkeypatch):
    _bolum()
    gorulen = {}

    def sahte(text, api_key, **kw):
        gorulen.update(text=text, prev=kw.get("prev_context"))
        return {"translation": "İKİ (yeni)", "model": "m"}
    monkeypatch.setattr(translate, "translate_chapter", sahte)
    r = _client().post("/api/chapter/paragraf/oneri", json={"url": URL, "sira": 1})
    assert r.status_code == 200
    assert r.json()["aday"] == "İKİ (yeni)" and r.json()["mevcut"] == "İki."
    assert gorulen == {"text": "Two.", "prev": "Bir."}
    assert cache.get_chapter(URL)["translation"] == "Bir.\n\nİki.\n\nÜç."


def test_yeniden_oneri_hafif_kipte_cevirir(monkeypatch):
    # Tek cümlelik öneri bölüm hattının bütün turlarıyla 3-5 çağrı / 40-75 sn sürüyordu.
    _bolum()
    gorulen = {}

    def sahte(text, api_key, **kw):
        gorulen["hafif"] = kw.get("hafif")
        return {"translation": "İKİ", "model": "m"}
    monkeypatch.setattr(translate, "translate_chapter", sahte)
    _client().post("/api/chapter/paragraf/oneri", json={"url": URL, "sira": 1})
    assert gorulen["hafif"] is True


class _Tur:
    """Ek turları sayar; hafif kipte hiçbiri çağrılmamalı."""

    def __init__(self, monkeypatch):
        from core import ceviri_baglam, ceviri_cilala, ceviri_kalite

        self.turlar = []
        self.ceviri = 0
        def cilala(tr, *a, **k):
            self.turlar.append("cilalama")
            return {}
        def kalite(*a, **k):
            self.turlar.append("kalite")
            return {"durum": "temiz", "supheli": [], "onarim_modelleri": []}
        def analiz(*a, **k):
            self.turlar.append("analiz")
            raise ceviri_baglam.AnalizHatasi("testte analiz yok")
        def parca(*a, **k):
            # Terim alanları eksik yanıt: hafif olmayan kipte bir tekrar daha tetikler.
            self.ceviri += 1
            return {"translation": "[[1]] Merhaba dostum, nasılsın.", "detected_names": [],
                    "detected_terms": {}, "model": "m", "alan_eksik": True}
        monkeypatch.setattr(ceviri_cilala, "cilala", cilala)
        monkeypatch.setattr(ceviri_kalite, "denetle_ve_onar", kalite)
        monkeypatch.setattr(ceviri_baglam, "analiz", analiz)
        monkeypatch.setattr(translate, "_translate_chunk", parca)
        for ad in ("CEVIRI_CILALA", "CEVIRI_KALITE"):
            monkeypatch.setenv(ad, "1")


def test_hafif_kip_tek_ceviri_cagrisi_yapar(monkeypatch):
    tur = _Tur(monkeypatch)
    monkeypatch.setenv("CEVIRI_ANALIZ", "1")
    sonuc = translate.translate_chapter("Hello my friend, how are you.", "anahtar",
                                        models=("m",), hafif=True)
    assert sonuc["translation"] == "Merhaba dostum, nasılsın."
    assert tur.ceviri == 1 and tur.turlar == []


def test_hafif_olmayan_kip_ek_turlari_calistirir(monkeypatch):
    # Karşı test: ek turlar bu kurulumda gerçekten tetikleniyor, yani yukarıdaki
    # "hiçbiri çağrılmadı" sonucu kurulum hatasından gelmiyor.
    tur = _Tur(monkeypatch)
    monkeypatch.setenv("CEVIRI_ANALIZ", "0")
    translate.translate_chapter("Hello my friend, how are you.", "anahtar", models=("m",))
    assert tur.ceviri == 2 and tur.turlar == ["cilalama", "kalite"]


@pytest.mark.parametrize("acilan, beklenen", [
    (("cilalama",), ["cilalama"]),
    (("kalite",), ["kalite"]),
    (("cilalama", "kalite"), ["cilalama", "kalite"]),
])
def test_hafif_kipte_paragraf_anahtari_acik_asamayi_calistirir(monkeypatch, acilan, beklenen):
    # Ayarlardaki "Paragraf önerisinde" anahtarı: yalnız açılan tur koşar; analiz ve
    # terim tekrarı hafif kipte yine atlanır (tek çeviri çağrısı).
    from core import ceviri_asamalari

    tur = _Tur(monkeypatch)
    monkeypatch.setenv("CEVIRI_ANALIZ", "1")
    for ad in acilan:
        ceviri_asamalari.ayarla_paragraf(ad, True)
    translate.translate_chapter("Hello my friend, how are you.", "anahtar",
                                models=("m",), hafif=True)
    assert tur.ceviri == 1 and tur.turlar == beklenen


def test_paragraf_anahtari_bolum_cevirisini_etkilemez(monkeypatch):
    # Bölüm anahtarı kapalıyken paragraf anahtarı açık: bölüm çevirisinde tur KOŞMAZ.
    from core import ceviri_asamalari

    tur = _Tur(monkeypatch)
    monkeypatch.setenv("CEVIRI_ANALIZ", "0")
    ceviri_asamalari.ayarla("cilalama", False)
    ceviri_asamalari.ayarla("kalite", False)
    ceviri_asamalari.ayarla_paragraf("cilalama", True)
    ceviri_asamalari.ayarla_paragraf("kalite", True)
    translate.translate_chapter("Hello my friend, how are you.", "anahtar", models=("m",))
    assert tur.turlar == []


def test_bolunen_paragraf_tek_paragrafa_indirilir(monkeypatch):
    _bolum()
    monkeypatch.setattr(translate, "translate_chapter",
                        lambda *a, **k: {"translation": "A.\n\nB."})
    r = _client().post("/api/chapter/paragraf/oneri", json={"url": URL, "sira": 0})
    assert r.json()["aday"] == "A. B."


def test_onar_modu_kalite_onarimini_kullanir(monkeypatch):
    _bolum()
    monkeypatch.setattr(translate, "paragraf_onar", lambda en, tr, sira, *a, **k: {
        "aday": tr[sira] + " (onarıldı)", "model": "m", "kalan": []})
    r = _client().post("/api/chapter/paragraf/oneri", json={"url": URL, "sira": 2, "mod": "onar"})
    assert r.json()["aday"] == "Üç. (onarıldı)" and r.json()["mod"] == "onar"


def test_hizasiz_bolumde_409():
    _bolum(kaynak="Only one paragraph.")
    r = _client().post("/api/chapter/paragraf/oneri", json={"url": URL, "sira": 0})
    assert r.status_code == 409


def test_kaydet_paragrafi_degistirir_arsivler_ve_supheyi_dusurur():
    _bolum(kalite={"durum": "supheli", "supheli": [
        {"paragraf": 1, "tur": "anlam", "aciklama": "x"},
        {"paragraf": 2, "tur": "uslup", "aciklama": "y"}]})
    r = _client().post("/api/chapter/paragraf/kaydet",
                       json={"url": URL, "sira": 1, "mevcut": "İki.", "metin": "İki yeni."})
    assert r.status_code == 200 and r.json()["ceviri_zamani"]
    b = cache.get_chapter(URL)
    assert b["translation"] == "Bir.\n\nİki yeni.\n\nÜç."
    assert [x["paragraf"] for x in b["ceviri_kalitesi"]["supheli"]] == [2]
    assert b["ceviri_kalitesi"]["elle_degisen"] == [1]
    assert len(cache.arsiv_listesi(URL)) == 1


def test_kaydet_arada_degismisse_409():
    _bolum()
    r = _client().post("/api/chapter/paragraf/kaydet",
                       json={"url": URL, "sira": 1, "mevcut": "Eski görünüm.", "metin": "X"})
    assert r.status_code == 409
    assert cache.get_chapter(URL)["translation"] == "Bir.\n\nİki.\n\nÜç."


@pytest.mark.parametrize("metin", ["", "A.\n\nB."])
def test_kaydet_bos_ya_da_bolunmus_metni_reddeder(metin):
    _bolum()
    r = _client().post("/api/chapter/paragraf/kaydet",
                       json={"url": URL, "sira": 0, "mevcut": "Bir.", "metin": metin})
    assert r.status_code == 400


def test_paragraf_onar_degismeyen_metinde_oneri_vermez(monkeypatch):
    from core import ceviri_kalite

    def sahte(tr, en, *a, **k):
        return {"supheli": [{"paragraf": 0}], "onarim_modeli": None, "durum": "supheli"}
    monkeypatch.setattr(ceviri_kalite, "denetle_ve_onar", sahte)
    monkeypatch.setattr(translate, "_gemini_fabrikasi", lambda k: None)
    sonuc = translate.paragraf_onar(["a"], ["b"], 0, {}, {}, None, models=("m",))
    assert sonuc["aday"] is None and sonuc["kalan"] == [{"paragraf": 0}]
    assert json.dumps(sonuc)
