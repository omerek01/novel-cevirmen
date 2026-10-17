"""Bölüm başına sözlük damgası (Ö3): bu bölümü etkileyen sözlük değişikliği hangisi."""
from __future__ import annotations

from core import cache, glossary, pipeline

KITAP = "damga-kitap"
URL = "https://ornek.test/damga-kitap/1"


def test_damga_yalniz_bolumde_gecen_kayitlari_tasir():
    sozluk = {"Hollow Mountain": "Kovan Dağı", "Sunny": "Sunny", "Nephis": "Nephis"}
    damga = glossary.sozluk_damgasi(sozluk, "Sunny climbed Hollow Mountain.")
    assert damga == {"Hollow Mountain": "Kovan Dağı", "Sunny": "Sunny"}


def test_damga_farki_yalniz_degisen_kaydi_soyler():
    glossary.set_term(KITAP, "Hollow Mountain", "Kovan Dağı")
    glossary.set_term(KITAP, "Sunny", "Sunny")
    damga = {"Hollow Mountain": "Kovan Dağı", "Sunny": "Sunny"}
    assert glossary.damga_farki(KITAP, damga) == []
    glossary.set_term(KITAP, "Hollow Mountain", "Oyuk Dağı")
    # Bölümde geçmeyen kayıt değişse de bu bölüm etkilenmez.
    glossary.set_term(KITAP, "Nephis", "Neph")
    assert glossary.damga_farki(KITAP, damga) == [
        {"source": "Hollow Mountain", "eski": "Kovan Dağı", "yeni": "Oyuk Dağı"}]


def test_damgasiz_bolum_bilinmiyor_doner():
    assert glossary.damga_farki(KITAP, None) is None


def test_damga_kaydedilir_ve_okurken_fark_turetilir():
    glossary.set_term(KITAP, "Hollow Mountain", "Kovan Dağı")
    cache.save_chapter(URL, {
        "book_slug": KITAP, "book_title": "Damga", "title": "1", "chapter_no": 1,
        "translation": "Kovan Dağı'na tırmandı.", "source": "He climbed Hollow Mountain.",
        "sozluk_damgasi": {"Hollow Mountain": "Kovan Dağı"},
    })
    satir = cache.get_chapter(URL)
    assert satir["sozluk_damgasi"] == {"Hollow Mountain": "Kovan Dağı"}
    glossary.set_term(KITAP, "Hollow Mountain", "Oyuk Dağı")
    sonuc = pipeline._finalize_cached(cache.get_chapter(URL), URL, advance_position=False)
    assert sonuc["sozluk_degisen"] == [
        {"source": "Hollow Mountain", "eski": "Kovan Dağı", "yeni": "Oyuk Dağı"}]


def test_damga_tasimayan_guncelleme_eski_damgayi_korur():
    cache.save_chapter(URL, {
        "book_slug": KITAP, "book_title": "Damga", "title": "1", "chapter_no": 1,
        "translation": "a", "sozluk_damgasi": {"Sunny": "Sunny"},
    })
    cache.save_chapter(URL, {"book_slug": KITAP, "book_title": "Damga", "title": "1",
                             "chapter_no": 1, "translation": "a"})
    assert cache.get_chapter(URL)["sozluk_damgasi"] == {"Sunny": "Sunny"}
