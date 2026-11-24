"""Künye: bölümde ilk kez bulunan otomatik kayıtlar, GÜNCEL durumlarıyla.

Önce-bekleme kuralından beri otomatik kayıt çeviri anında 'eklendi' sayılmaz
(`added_terms` boş kalır). Doğrulamadan geçip kurala dönen ad hiçbir yerde
görünmüyordu (gerçek bulgu: shadow-slave 965, Carin). Durum okuma anında
sözlükten hesaplanır; doğrulama bitince künye kendiliğinden güncellenir.
"""
import pytest

from core import db, glossary, pipeline


def _inceleme_sifirla(slug, kaynak):
    conn = glossary._connect()
    try:
        conn.execute("UPDATE glossary SET inceleme = NULL, durum = NULL "
                     "WHERE book_slug = ? AND source = ?", (slug, kaynak))
        conn.commit()
    finally:
        conn.close()


def test_bolumde_bulunan_otomatik_kayit_durumuyla_doner():
    glossary.merge_names("k", ["Carin"], "auto", 965)
    glossary.merge_terms("k", {"Erebus Field": "Erebus Sahası"}, "auto", 965)
    sonuc = pipeline.bolumde_bulunan_kayitlar("k", 965)
    assert {x["kaynak"]: x["durum"] for x in sonuc} == {
        "Carin": "bekliyor", "Erebus Field": "bekliyor"}
    assert {x["kaynak"]: x["karsilik"] for x in sonuc}["Erebus Field"] == "Erebus Sahası"


def test_dogrulamadan_gecen_kayit_kural_gorunur():
    glossary.merge_names("k", ["Carin"], "auto", 965)
    _inceleme_sifirla("k", "Carin")
    assert pipeline.bolumde_bulunan_kayitlar("k", 965) == [
        {"kaynak": "Carin", "karsilik": "Carin", "tur": "kisi", "durum": "kural"}]


def test_baska_bolum_ve_elle_yazilan_kayit_girmez():
    glossary.merge_names("k", ["Sunny"], "auto", 964)
    glossary.set_term("k", "Gere", "Gere")
    assert pipeline.bolumde_bulunan_kayitlar("k", 965) == []
    assert pipeline.bolumde_bulunan_kayitlar("k", None) == []
    assert pipeline.bolumde_bulunan_kayitlar(None, 965) == []


@pytest.mark.bekleme
def test_dogrulamasi_suren_kayit_bekliyor_degil_dogrulaniyor_gorunur():
    """2026-11-24 (shadow-slave 1891, Sagramore): künye doğrulaması süren kaydı "bekliyor" diye
    gösterip "Bekleyenleri incele" diyordu; 9 sn sonra kayıt doğrulamadan geçip kural oldu ve
    listede yoktu. Doğrulama koşmadıysa durum "dogrulaniyor"; doğrulama kararı kullanıcıya
    bıraktıysa "bekliyor"."""
    glossary.merge_terms("k", {"Erebus Field": "Erebus Sahası"}, "auto", 965)
    assert [x["durum"] for x in pipeline.bolumde_bulunan_kayitlar("k", 965)] == ["dogrulaniyor"]
    conn = glossary._connect()
    try:
        conn.execute("UPDATE glossary SET dogrulama = 'inceleme' WHERE book_slug = 'k'")
        conn.commit()
    finally:
        conn.close()
    assert [x["durum"] for x in pipeline.bolumde_bulunan_kayitlar("k", 965)] == ["bekliyor"]
