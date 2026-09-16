"""Aşama 2 backend: etkilenen bölüm örnekleri, "bu bölümde geçenler", okurken
eklenen terimin kökeni, koşullu terimlerin "otomatik denetlenmedi" bilgisi.

Metinler uydurmadır; testler yapıyı (hizalı paragraf, terim eşleşmesi) sınar.
"""
from __future__ import annotations

from core import cache, glossary, library, pipeline

KITAP = "gumus-kule"
EN = [
    "Kaan lit the lantern.",
    "The bell of the Silver Tower rang twice. Nobody moved.",
    "A Great beast waited below the Silver Tower.",
]
TR = [
    "Kaan feneri yaktı.",
    "Gümüş Kulenin çanı iki kez çaldı. Kimse kıpırdamadı.",
    "Gümüş Kulenin altında Ulu bir canavar bekliyordu.",
]


def _bolum(no, en=EN, tr=TR, kaynakli=True):
    url = f"https://ornek.test/{KITAP}/chapter-{no}"
    cache.save_chapter(url, {
        "book_slug": KITAP, "book_title": "Gumus Kule", "title": f"Chapter {no}",
        "chapter_no": no, "translation": "\n\n".join(tr),
        "source": "\n\n".join(en) if kaynakli else None,
        "next_url": None, "prev_url": None, "detected_names": [], "chunk_count": 1,
    })
    library.upsert_book(KITAP, "Gumus Kule", url, f"Chapter {no}", no)
    return url


def _client():
    from fastapi.testclient import TestClient

    import server

    return TestClient(server.app)


# ---------- etki örnekleri ----------

def test_etki_bolum_basina_ingilizce_cumle_ve_hizali_turkce_paragraf_verir():
    _bolum(1)
    etki = pipeline.terim_etkisi(KITAP, "Silver Tower")
    assert etki["count"] == 1
    b = etki["chapters"][0]
    assert b["ornek_en"] == "The bell of the Silver Tower rang twice."
    assert b["ornek_tr"] == TR[1]
    assert b["ceviri_zamani"] is not None


def test_etki_hizalama_yoksa_turkce_ornek_uydurmaz():
    """Paragraf sayıları tutmuyorsa hangi Türkçe paragrafın karşılık olduğu BİLİNMEZ."""
    _bolum(1, tr=["Tek blok çeviri, hizalama tutmamış."])
    b = pipeline.terim_etkisi(KITAP, "Silver Tower")["chapters"][0]
    assert b["ornek_en"]
    assert b["ornek_tr"] is None


# ---------- bu bölümde geçenler ----------

def test_sozluk_ucu_bolum_verilince_orada_gecen_terimleri_doner():
    url = _bolum(1)
    glossary.set_term(KITAP, "Silver Tower", "Gümüş Kule")
    glossary.set_term(KITAP, "Kaan", "Kaan")
    glossary.set_term(KITAP, "Nephis", "Nephis")
    veri = _client().get(f"/api/book/{KITAP}/glossary", params={"bolum": url}).json()
    assert sorted(veri["bolumde"]) == ["Kaan", "Silver Tower"]


def test_sozluk_ucu_kaynaksiz_bolumde_bolumde_null():
    """Kaynak metni yoksa "hiçbiri geçmiyor" demek yanlış olurdu: bilinmiyor."""
    url = _bolum(1, kaynakli=False)
    glossary.set_term(KITAP, "Kaan", "Kaan")
    veri = _client().get(f"/api/book/{KITAP}/glossary", params={"bolum": url}).json()
    assert veri["bolumde"] is None


def test_sozluk_ucu_bolum_verilmezse_bolumde_alani_yok():
    glossary.set_term(KITAP, "Kaan", "Kaan")
    assert "bolumde" not in _client().get(f"/api/book/{KITAP}/glossary").json()


# ---------- okurken eklenen terimin kökeni ----------

def test_ornek_bos_kokeni_doldurur_dolu_kokene_dokunmaz():
    c = _client()
    r = c.post(f"/api/book/{KITAP}/glossary", json={
        "source": "Silver Tower", "target": "Gümüş Kule",
        "ornek": {"kaynak_cumle": "Gümüş Kulenin çanı çaldı.", "bolum": 12},
    })
    assert r.status_code == 200
    satir = {s["source"]: s for s in glossary.get_glossary_rows(KITAP)}["Silver Tower"]
    assert satir["kaynak_cumle"] == "Gümüş Kulenin çanı çaldı." and satir["first_chapter"] == 12

    c.post(f"/api/book/{KITAP}/glossary", json={
        "source": "SilverTower", "target": "Gümüş Kule",
        "ornek": {"kaynak_cumle": "Başka cümle.", "bolum": 40},
    })
    satir = {s["source"]: s for s in glossary.get_glossary_rows(KITAP)}["Silver Tower"]
    assert satir["kaynak_cumle"] == "Gümüş Kulenin çanı çaldı." and satir["first_chapter"] == 12


# ---------- koşullu terimler denetlenmedi ----------

def test_bolum_yaniti_bolumde_gecen_kosullu_terimleri_bildirir():
    url = _bolum(1)
    glossary.set_term(KITAP, "Great", "Ulu")
    glossary.set_kosul(KITAP, "Great", "yalnız rütbe")
    glossary.set_term(KITAP, "Saint", "Aziz")
    glossary.set_kosul(KITAP, "Saint", "yalnız rütbe")  # bölümde GEÇMİYOR
    veri = pipeline.get_or_translate(url, None)
    assert veri["kosullu_denetlenmeyen"] == ["Great"]


# ---------- bölüm listesi ----------

def test_bolum_listesi_ceviri_zamanini_tasir():
    _bolum(1)
    [b] = cache.list_chapters(KITAP)
    assert isinstance(b["ceviri_zamani"], float)
