"""Sözlük yedeği: tam kayıt (koşul + köken) dışa/içe aktarma, eski biçim uyumu.

Belge bulgusu (2026-09-16): dışa aktarma yalnız `kaynak -> karşılık` taşıyordu.
Boş bir veritabanına geri yüklenen yedek KOŞULLARI (prompt'ta kural olan bağlam
bilgisi) ve kökeni (kaydın hangi bölümden, hangi cümleden, kimin eliyle girdiği)
sessizce kaybediyordu — yani "yedek" adını taşıyan dosya sözlüğü geri
getirmiyordu. Kabul ölçütü: boş veritabanına geri yüklemede koşullar ve köken
bilgisi korunur.
"""
from __future__ import annotations

import json

import pytest

from core import glossary

KITAP = "gumus-kule"


def _tohumla():
    glossary.set_term(KITAP, "Great", "Ulu")
    glossary.set_kosul(KITAP, "Great", "yalnız canavar rütbesi olarak")
    glossary.merge_terms(
        KITAP, {"Silver Tower": "Gümüş Kule"}, "auto", 7,
        {"Silver Tower": "Gümüş Kulenin çanı çaldı."},
    )
    glossary.merge_names(KITAP, ["Kaan"], "auto", 3, {"Kaan": "Kaan kapıyı açtı."})


def _satirlar(slug=KITAP):
    return {r["source"]: r for r in glossary.get_glossary_rows(slug)}


# ---------- dışa aktarma ----------

def test_disa_aktarim_tam_kayit_ve_bicim_surumu_tasir():
    _tohumla()
    yedek = glossary.disa_aktar(KITAP)
    assert yedek["bicim"] == "novellink-sozluk"
    assert yedek["surum"] == 2
    assert yedek["book_slug"] == KITAP
    assert yedek["kayit_sayisi"] == 3
    kayit = {k["source"]: k for k in yedek["kayitlar"]}
    assert kayit["Great"]["kosul"] == "yalnız canavar rütbesi olarak"
    assert kayit["Silver Tower"]["first_chapter"] == 7
    assert kayit["Silver Tower"]["origin"] == "auto"
    assert kayit["Silver Tower"]["kaynak_cumle"] == "Gümüş Kulenin çanı çaldı."


def test_disa_aktarim_eski_okuyucu_icin_terms_eslemesini_de_tasir():
    """Önbellekteki eski app.js yalnız `terms` okur; yeni yedeği tümden reddetmesin."""
    _tohumla()
    assert glossary.disa_aktar(KITAP)["terms"]["Great"] == "Ulu"


# ---------- geri yükleme ----------

def test_bos_veritabanina_geri_yukleme_kosul_ve_kokeni_korur(tmp_path, monkeypatch):
    _tohumla()
    once = _satirlar()
    yedek = json.loads(json.dumps(glossary.disa_aktar(KITAP), ensure_ascii=False))

    monkeypatch.setenv("NOVEL_DB_PATH", str(tmp_path / "bos.db"))
    assert glossary.get_glossary(KITAP) == {}
    sonuc = glossary.ice_aktar(KITAP, yedek["kayitlar"], "mevcut")

    assert sonuc["eklenen"] == 3 and sonuc["gecersiz"] == 0
    sonra = _satirlar()
    for kaynak, satir in once.items():
        for alan in ("target", "kosul", "origin", "first_chapter", "kaynak_cumle", "created_at"):
            assert sonra[kaynak][alan] == satir[alan], (kaynak, alan)


def test_mevcut_stratejisi_kayitli_terimi_ezmez():
    glossary.set_term(KITAP, "Great", "Büyük")
    sonuc = glossary.ice_aktar(
        KITAP, [{"source": "Great", "target": "Ulu", "kosul": "rütbe"}], "mevcut"
    )
    assert sonuc["atlanan"] == 1 and sonuc["eklenen"] == 0
    assert glossary.get_glossary(KITAP)["Great"] == "Büyük"
    assert glossary.get_kosullar(KITAP) == {}


def test_dosya_stratejisi_verilen_alanlari_yazar_verilmeyenleri_korur():
    glossary.set_term(KITAP, "Great", "Büyük")
    glossary.set_kosul(KITAP, "Great", "eski koşul")
    glossary.merge_terms(KITAP, {"Saint": "Aziz"}, "auto", 9, {"Saint": "Aziz geldi."})

    sonuc = glossary.ice_aktar(KITAP, [
        {"source": "Great", "target": "Ulu"},  # kosul anahtarı YOK -> korunur
        {"source": "Saint", "target": "Aziz", "kaynak_cumle": None},  # açık null -> temizlenir
    ], "dosya")

    assert sonuc["guncellenen"] == 2
    satir = _satirlar()
    assert satir["Great"]["target"] == "Ulu"
    assert satir["Great"]["kosul"] == "eski koşul"
    assert satir["Saint"]["kaynak_cumle"] is None
    assert satir["Saint"]["first_chapter"] == 9


def test_yazim_varyanti_ikinci_satir_acmaz_kayitli_yazim_korunur():
    glossary.set_term(KITAP, "Ore Empire", "Ork İmparatorluğu")
    glossary.ice_aktar(KITAP, [{"source": "OreEmpire", "target": "Maden İmparatorluğu"}], "dosya")
    assert glossary.get_glossary(KITAP) == {"Ore Empire": "Maden İmparatorluğu"}


def test_dosyada_ayni_terim_iki_kez_varsa_ilki_yazilir():
    sonuc = glossary.ice_aktar(KITAP, [
        {"source": "Ore Empire", "target": "Ork İmparatorluğu"},
        {"source": "OreEmpire", "target": "Maden İmparatorluğu"},
    ], "dosya")
    assert sonuc["eklenen"] == 1 and sonuc["atlanan"] == 1
    assert glossary.get_glossary(KITAP) == {"Ore Empire": "Ork İmparatorluğu"}


def test_gecersiz_kayit_atlanir_sayilir_digerleri_yazilir():
    sonuc = glossary.ice_aktar(KITAP, [
        {"target": "kaynaksız"},
        {"source": 42, "target": "sayı"},
        "düz metin",
        {"source": "Kaan", "first_chapter": "yedi"},
        {"source": "Mira", "target": "Mira"},
    ], "mevcut")
    assert sonuc["gecersiz"] == 4
    assert sonuc["eklenen"] == 1
    assert glossary.get_glossary(KITAP) == {"Mira": "Mira"}


def test_bos_karsilik_aynen_koru_demektir_ve_koken_yoksa_import_yazilir():
    glossary.ice_aktar(KITAP, [{"source": "Kaan", "target": None}], "mevcut")
    satir = _satirlar()["Kaan"]
    assert satir["target"] == "Kaan"
    assert satir["origin"] == "import"
    assert satir["created_at"] is not None


def test_bilinmeyen_strateji_reddedilir():
    with pytest.raises(ValueError):
        glossary.ice_aktar(KITAP, [{"source": "Kaan"}], "hepsini-sil")


# ---------- uç ----------

def _client():
    from fastapi.testclient import TestClient

    import server

    return TestClient(server.app)


def test_uc_disa_aktarim_v2_json_indirir():
    _tohumla()
    r = _client().get(f"/api/book/{KITAP}/glossary/export")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    veri = r.json()
    assert veri["surum"] == 2 and len(veri["kayitlar"]) == 3


def test_uc_iceri_aktarim_kayitlar_ile_calisir():
    r = _client().post(f"/api/book/{KITAP}/glossary/import", json={
        "kayitlar": [{"source": "Great", "target": "Ulu", "kosul": "rütbe", "origin": "manual"}],
    })
    assert r.status_code == 200
    veri = r.json()
    assert veri["eklenen"] == 1 and veri["gelen"] == 1
    assert glossary.get_kosullar(KITAP) == {"Great": "rütbe"}


def test_uc_eski_bicim_terms_hala_calisir():
    r = _client().post(f"/api/book/{KITAP}/glossary/import", json={"terms": {"Kaan": "Kaan"}})
    assert r.status_code == 200 and r.json()["eklenen"] == 1


def test_uc_ne_terms_ne_kayitlar_varsa_400():
    r = _client().post(f"/api/book/{KITAP}/glossary/import", json={"strateji": "mevcut"})
    assert r.status_code == 400


def test_uc_bilinmeyen_strateji_400():
    r = _client().post(f"/api/book/{KITAP}/glossary/import",
                       json={"kayitlar": [{"source": "Kaan"}], "strateji": "yok"})
    assert r.status_code == 400
