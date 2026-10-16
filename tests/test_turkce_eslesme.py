"""Türkçe karşılık eşleştirici: çekim, yumuşama, Türkçe büyük-küçük harf, tamlama çoğulu."""
import pytest

from core.turkce_eslesme import ayni_karsilik, karsilik_gecer, tr_kucuk


def test_tr_kucuk_turkce_harfler():
    assert tr_kucuk("IŞIK İZ") == "ışık iz"


@pytest.mark.parametrize("karsilik, metin", [
    ("Aziz", "Azizin gölgesi"),
    ("Aziz", "Aziz'e baktı"),
    ("Aziz", "AZİZLER geldi"),           # bağırma yazımı
    ("Işık", "IŞIĞIN içinde"),           # I -> ı + k -> ğ
    ("Kitap", "Kitabı açtı"),            # p -> b
    ("Ağaç", "Ağacın dalı"),             # ç -> c
    ("Kanat", "Kanadını açtı"),          # t -> d
    ("Oyuk Dağı", "Oyuk Dağı'nda kaldılar"),
    ("Oyuk Dağı", "Oyuk Dağına çıktı"),
    ("Oyuk Dağı", "Oyuk Dağları"),       # tamlama çoğulu
    ("Oyuk Dağı", "oyuk  dağının"),      # esnek boşluk + küçük harf
    ("Gölge Rütbesi", "Gölge Rütbeleri"),
])
def test_cekimli_hal_bulunur(karsilik, metin):
    assert karsilik_gecer(karsilik, metin)


@pytest.mark.parametrize("karsilik, metin", [
    ("Oyuk Dağı", "Kovan Dağları"),      # gerçek sapma vakası
    ("Aziz", "Mazizi"),                  # sözcük ortası
    ("Kitap", "Kitbı"),
    ("Kanat", "Kanadsız"),               # yumuşama yalnız ünlüden önce
    ("Işık", "isik"),                    # işaretsiz yazım katı kipte sayılmaz
])
def test_farkli_karsilik_bulunmaz(karsilik, metin):
    assert not karsilik_gecer(karsilik, metin)


def test_gevsek_kip_isaretsiz_yazimi_kabul_eder():
    assert karsilik_gecer("Işık", "isigin", gevsek=True)


def test_kisa_sozcukte_yumusama_yok():
    # "ak" -> "ağ" yumuşaması iki harfte yanlış eşleşme üretirdi
    assert not karsilik_gecer("Ak", "Ağı")


def test_ayni_karsilik():
    assert ayni_karsilik("Oyuk Dagina", "Oyuk Dağı")
    assert ayni_karsilik("Oyuk", "Oyuk Dağı")          # kısa anma sapma değil
    assert ayni_karsilik("Kitabı", "Kitap")
    assert not ayni_karsilik("Kovan Dağları", "Oyuk Dağı")
    assert ayni_karsilik("", "Aziz")
