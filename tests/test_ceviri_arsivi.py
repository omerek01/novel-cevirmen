"""Çeviri arşivi + bölüm künyesinde sözlük sürümü (belge: "eski çeviri geri alınabilmeli").

Yeniden çeviri eski çeviriyi sessizce eziyordu; yeni çeviri daha kötü çıkarsa
(hizalama kaybı, kalıntı) dönüş yoktu.
"""
from __future__ import annotations

import re
from pathlib import Path

from core import cache, glossary, library

URL = "https://ornek.test/kitap/chapter-1"


def _kaydet(ceviri, model="gemini-3.6-flash", **ek):
    cache.save_chapter(URL, {
        "book_slug": "kitap", "book_title": "Kitap", "title": "C1", "chapter_no": 1,
        "translation": ceviri, "source": "EN", "next_url": None, "detected_names": [],
        "chunk_count": 1, "model": model, "engine": "gemini", "glossary_leaks": {},
        "ingilizce_kalinti": {}, **ek,
    })


def _client():
    from fastapi.testclient import TestClient

    import server

    return TestClient(server.app)


def test_metin_degisince_eski_ceviri_arsivlenir_ayni_metin_arsivlenmez():
    _kaydet("bir", sozluk_surumu=4)
    _kaydet("bir")
    assert cache.arsiv_listesi(URL) == []
    _kaydet("iki", model="gemini-2.5-flash", sozluk_surumu=5)
    arsiv = cache.arsiv_listesi(URL)
    assert len(arsiv) == 1
    assert arsiv[0]["model"] == "gemini-3.6-flash" and arsiv[0]["sozluk_surumu"] == 4
    assert cache.get_chapter(URL)["sozluk_surumu"] == 5


def test_arsiv_url_basina_son_uc():
    for i in range(6):
        _kaydet(f"sürüm {i}")
    assert len(cache.arsiv_listesi(URL)) == cache.ARSIV_MAX


def test_geri_yukleme_eskiyi_getirir_simdikini_arsive_koyar_zamani_tazeler():
    _kaydet("eski", sozluk_surumu=1)
    _kaydet("yeni", model="gemini-2.5-flash", sozluk_surumu=2)
    once = cache.get_chapter(URL)["ceviri_zamani"]
    arsiv_id = cache.arsiv_listesi(URL)[0]["id"]
    assert cache.arsivden_geri_yukle(URL, arsiv_id)
    bolum = cache.get_chapter(URL)
    assert bolum["translation"] == "eski" and bolum["model"] == "gemini-3.6-flash"
    assert bolum["sozluk_surumu"] == 1
    assert bolum["ceviri_zamani"] >= once
    arsiv = cache.arsiv_listesi(URL)
    assert len(arsiv) == 1 and arsiv[0]["model"] == "gemini-2.5-flash"
    assert cache.arsivden_geri_yukle(URL, 99999) is False


def test_onarim_yolu_da_arsivler():
    _kaydet("kalıntılı")
    cache.set_translation(URL, "onarılmış", model="gemini-3.6-flash")
    assert len(cache.arsiv_listesi(URL)) == 1


def test_bolum_ve_kitap_silinince_arsiv_temizlenir():
    _kaydet("a")
    _kaydet("b")
    library.upsert_book("kitap", "Kitap", URL, "C1", 1)
    library.delete_book("kitap")
    assert cache.arsiv_listesi(URL) == []


def test_uclar_liste_ve_geri_yukleme():
    _kaydet("eski")
    _kaydet("yeni")
    c = _client()
    arsiv = c.get("/api/chapter/arsiv", params={"url": URL}).json()["arsiv"]
    assert len(arsiv) == 1 and arsiv[0]["uzunluk"] == len("eski")
    r = c.post("/api/chapter/arsiv/geri", json={"url": URL, "id": arsiv[0]["id"]})
    assert r.status_code == 200 and r.json()["ceviri_zamani"]
    assert cache.get_chapter(URL)["translation"] == "eski"
    assert c.post("/api/chapter/arsiv/geri", json={"url": URL, "id": 424242}).status_code == 404


def test_sozluk_ucu_kitap_surumunu_verir():
    glossary.set_term("kitap", "Saint", "Aziz")
    assert _client().get("/api/book/kitap/glossary").json()["surum"] == 1


def test_tel_tuzagi_ceviri_uretan_her_metin_yolu_sozluk_surumunu_yazar():
    """Künyeyi üreten metin yolları `glossary_leaks` ile AYNI noktalardır; birine
    `sozluk_surumu` eklenip ötekine eklenmezse o yoldan gelen bölüm "hangi sözlükle
    çevrildi" bilgisini sessizce kaybeder (`model` alanında tam bu yaşandı)."""
    metin = (Path(__file__).resolve().parent.parent / "app" / "core" / "pipeline.py").read_text(
        encoding="utf-8"
    )
    assert len(re.findall(r'"glossary_leaks":', metin)) == len(re.findall(r'"sozluk_surumu":', metin))
    assert metin.count("glossary.kitap_surumu(") == metin.count('"sozluk_surumu":')


def test_pipeline_ceviri_oncesi_sozluk_surumunu_kunyeye_yazar(monkeypatch):
    """Çeviriden SONRA eklenen otomatik terimler o prompt'ta yoktu: künye ÖNCEKİ
    sürümü taşımalı."""
    from core import pipeline

    glossary.set_term("kitap", "Saint", "Aziz")  # sürüm 1
    monkeypatch.setattr(pipeline, "translate_chapter", lambda text, **kw: {
        "translation": "ç", "source": None, "chunk_count": 1, "engine": "gemini",
        "detected_names": [], "detected_terms": {"Cold Wind City": "Soğuk Rüzgar Şehri"},
    })
    monkeypatch.setattr(pipeline, "fetch_chapter", lambda url, **kw: {
        "book_slug": "kitap", "book_title": "K", "title": "B1", "chapter_no": 1,
        "text": "t", "next_url": None, "prev_url": None,
    })
    payload = pipeline.get_or_translate("p-surum", "anahtar")
    assert payload["sozluk_surumu"] == 1
    assert glossary.kitap_surumu("kitap") == 2  # otomatik terim sonradan eklendi
    assert cache.get_chapter("p-surum")["sozluk_surumu"] == 1
