"""Kitaba özel terim türleri (2026-10-09, kullanıcı kararı): yalnız o kitapta geçerli;
hazır türler de yeniden adlandırılır ve silinir. Kod sabittir, ad değişir."""
from __future__ import annotations

from fastapi.testclient import TestClient

import server
from core import glossary

KITAP = "tur-kitap"
BASKA = "baska-kitap"


def _kodlar(slug):
    return [t["kod"] for t in glossary.turler(slug)]


def test_hazir_turler_varsayilan_adla_gelir():
    turler = glossary.turler(KITAP)
    assert [t["kod"] for t in turler] == list(glossary.TURLER)
    assert turler[0] == {"kod": "kisi", "ad": "Kişi", "ozel": False}


def test_ozel_tur_eklenir_atanir_ve_yalniz_o_kitapta_gecerli():
    kod = glossary.tur_ekle(KITAP, "  Klan  ")
    assert kod == "Klan" and "Klan" in _kodlar(KITAP) and "Klan" not in _kodlar(BASKA)
    assert glossary.tur_ekle(KITAP, "klan") == "Klan"  # aynı ad ikinci tür açmaz
    glossary.set_term(KITAP, "Fire Keepers", "Ateş Bekçileri")
    glossary.terimi_yaz(KITAP, "Fire Keepers", "Ateş Bekçileri", tur="Klan")
    assert glossary.get_glossary_rows(KITAP)[0]["tur"] == "Klan"
    # Başka kitapta tanınmaz: tür boş kalır.
    glossary.set_term(BASKA, "Fire Keepers", "Ateş Bekçileri")
    glossary.terimi_yaz(BASKA, "Fire Keepers", "Ateş Bekçileri", tur="Klan")
    assert glossary.get_glossary_rows(BASKA)[0]["tur"] is None


def test_hazir_tur_yeniden_adlandirilir_kod_ayni_kalir():
    glossary.set_term(KITAP, "Sunny", "Sunny")
    glossary.terimi_yaz(KITAP, "Sunny", "Sunny", tur="kisi")
    assert glossary.tur_adlandir(KITAP, "kisi", "Karakter")
    assert glossary.turler(KITAP)[0] == {"kod": "kisi", "ad": "Karakter", "ozel": False}
    assert glossary.get_glossary_rows(KITAP)[0]["tur"] == "kisi"
    assert glossary.turler(BASKA)[0]["ad"] == "Kişi"  # başka kitap etkilenmez


def test_hazir_tur_silinir_kayit_kalir_turu_bosalir_ve_geri_getirilebilir():
    glossary.set_term(KITAP, "Sunny", "Sunny")
    glossary.terimi_yaz(KITAP, "Sunny", "Sunny", tur="kisi")
    assert glossary.tur_sil(KITAP, "kisi") == 1
    assert "kisi" not in _kodlar(KITAP)
    satir = glossary.get_glossary_rows(KITAP)[0]
    assert satir["source"] == "Sunny" and satir["tur"] is None
    # Silinen hazır türü model doğrulaması geri getiremez.
    glossary.tanim_yaz(KITAP, "Sunny", "Ana karakter", "kisi", yalniz_bossa=True)
    assert glossary.get_glossary_rows(KITAP)[0]["tur"] is None
    assert glossary.tur_ekle(KITAP, "Kişi") == "kisi" and "kisi" in _kodlar(KITAP)


def test_ad_kurallari():
    for kotu in ("", "   ", "x" * 31):
        try:
            glossary.tur_ekle(KITAP, kotu)
        except ValueError:
            continue
        raise AssertionError(kotu)
    glossary.tur_ekle(KITAP, "Klan")
    try:
        glossary.tur_adlandir(KITAP, "kisi", "klan")
    except ValueError:
        pass
    else:
        raise AssertionError("iki tür aynı adı taşıyamaz")


def test_api_uclari():
    c = TestClient(server.app)
    r = c.post(f"/api/book/{KITAP}/glossary/turler", json={"ad": "Klan"})
    assert r.status_code == 200 and r.json()["kod"] == "Klan"
    r = c.put(f"/api/book/{KITAP}/glossary/turler", json={"kod": "kisi", "ad": "Karakter"})
    assert r.status_code == 200 and r.json()["turler"][0]["ad"] == "Karakter"
    r = c.delete(f"/api/book/{KITAP}/glossary/turler", params={"kod": "yer"})
    assert r.status_code == 200 and "yer" not in [t["kod"] for t in r.json()["turler"]]
    assert c.delete(f"/api/book/{KITAP}/glossary/turler", params={"kod": "yok"}).status_code == 404
    assert c.post(f"/api/book/{KITAP}/glossary/turler", json={"ad": " "}).status_code == 400
    glossary.set_term(KITAP, "Sunny", "Sunny")
    g = c.get(f"/api/book/{KITAP}/glossary").json()
    assert [t["kod"] for t in g["turler"]][-1] == "Klan"
