"""Kaynak adını değiştirme (yeniden adlandırma): kayıt AYNI kalır, yalnız adı değişir.

Kullanıcı vakası (2026-11-07): inceleme "Chaos Beings" için tekil öneriyordu; panelde
kaynağı "Chaos Being" yapıp kaydedince yeni, kökensiz bir kayıt açılıyordu ve kaydın
yakalandığı paragraf (köken cümlesi, ilk bölüm) kayboluyordu."""
import pytest

from core import glossary, translate

KITAP = "kitap"


def _kayit(source):
    return next((r for r in glossary.get_glossary_rows(KITAP) if r["source"] == source), None)


def test_ad_degisir_koken_kimlik_ve_ekler_korunur():
    glossary.merge_terms(KITAP, {"Chaos Beings": "Kaos Varlıkları"}, "auto", 12,
                         {"Chaos Beings": "The Chaos Beings swarmed the gate."})
    glossary.yazim_ekle(KITAP, "Chaos Beings", "Beings of Chaos")
    once = _kayit("Chaos Beings")

    sonra = glossary.kaynagi_degistir(KITAP, "Chaos Beings", "Chaos Being")

    assert _kayit("Chaos Beings") is None
    yeni = _kayit("Chaos Being")
    assert yeni["kimlik"] == once["kimlik"] and sonra["kimlik"] == once["kimlik"]
    assert yeni["kaynak_cumle"] == "The Chaos Beings swarmed the gate."
    assert yeni["first_chapter"] == 12
    assert yeni["target"] == "Kaos Varlıkları"
    assert glossary.ekler(KITAP)["Chaos Being"]["yazimlar"] == ["Beings of Chaos"]
    # Tekil ad metindeki çoğulu da yakalar: kayıt kaynak cümlesinden yine bulunur.
    assert translate._term_regex("Chaos Being").search("The Chaos Beings swarmed")
    # Geçmiş kimlikle okunur: eski adla yazılanlar kopmaz.
    assert len(glossary.gecmis(KITAP, "Chaos Being")) >= 2


def test_baska_kaydin_adi_ya_da_yazimi_olamaz():
    glossary.set_term(KITAP, "Chaos Beings", "Kaos Varlıkları")
    glossary.set_term(KITAP, "Chaos Spawn", "Kaos Yavrusu")
    glossary.yazim_ekle(KITAP, "Chaos Spawn", "Chaos Brood")
    for hedef in ("Chaos Spawn", "chaos spawn", "Chaos Brood"):
        with pytest.raises(glossary.YazimCakismasi):
            glossary.kaynagi_degistir(KITAP, "Chaos Beings", hedef)
    assert _kayit("Chaos Beings")["target"] == "Kaos Varlıkları"


def test_kendi_yazimina_gecince_yazim_ana_ad_olur():
    glossary.set_term(KITAP, "Chaos Beings", "Kaos Varlıkları")
    glossary.yazim_ekle(KITAP, "Chaos Beings", "Chaos Being")
    glossary.kaynagi_degistir(KITAP, "Chaos Beings", "Chaos Being")
    assert _kayit("Chaos Being") and not glossary.ekler(KITAP).get("Chaos Being", {}).get("yazimlar")


def test_kayit_yoksa_none():
    assert glossary.kaynagi_degistir(KITAP, "Yok", "Var") is None


def test_uc_ad_degistirir_ve_hatalari_soyler():
    from fastapi.testclient import TestClient

    import server

    glossary.set_term(KITAP, "Chaos Beings", "Kaos Varlıkları")
    glossary.set_term(KITAP, "Chaos Spawn", "Kaos Yavrusu")
    c = TestClient(server.app)
    yol = f"/api/book/{KITAP}/glossary/kaynak"
    r = c.post(yol, json={"source": "Chaos Beings", "yeni": "Chaos Being"})
    assert r.status_code == 200 and r.json()["kayit"]["source"] == "Chaos Being"
    assert c.post(yol, json={"source": "Chaos Being", "yeni": "Chaos Spawn"}).status_code == 400
    assert c.post(yol, json={"source": "Yok", "yeni": "Var"}).status_code == 404
