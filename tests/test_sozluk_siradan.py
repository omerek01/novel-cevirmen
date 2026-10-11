"""Sıradan kelime işareti (`SOZLUK_SIRADAN`): büyük harfli sözlük kaydı metinde yalnız
küçük harfle ya da cümle başında geçiyorsa modele "sıradan kelime olabilir" denir.

Ölçülen sorun (2026-10-11 anlam/bağlam deneyi): "armor" -> "Zırhları", "hope" ->
"Umut'u", "Seven chains" -> "Yediler zincir". Kayıt prompt'tan atılmaz (hiyerarşi
adı küçük harfle de terimdir); yalnız işaretlenir. Bayrak kapalıyken prompt bayt
bayt eskisidir. Hepsi çevrimdışı.
"""
from __future__ import annotations

import pytest

from core import translate

ISARET = translate.SIRADAN_ISARETI


@pytest.fixture
def acik(monkeypatch):
    monkeypatch.setenv("SOZLUK_SIRADAN", "1")


def _istem(paras, sozluk, kosullar=None):
    return translate._build_user_prompt(paras, sozluk, "", kosullar)


def _satir(user: str, kaynak: str) -> str:
    return next(s for s in user.splitlines() if s.startswith(f"{kaynak} -> "))


def test_bayrak_kapaliyken_istem_degismez(monkeypatch):
    paras = ["They dismissed most of their armor."]
    monkeypatch.delenv("SOZLUK_SIRADAN", raising=False)
    kapali = _istem(paras, {"Armor": "Zırh"})
    assert ISARET not in kapali
    monkeypatch.setenv("SOZLUK_SIRADAN", "0")
    assert _istem(paras, {"Armor": "Zırh"}) == kapali


def test_yalniz_kucuk_harfli_gecis_isaretlenir(acik):
    user = _istem(["They dismissed most of their armor."], {"Armor": "Zırh"})
    assert ISARET in _satir(user, "Armor")
    # Açıklama ve son hatırlatma notu yalnız işaretli kayıt varken eklenir.
    assert user.count(ISARET) == 3


def test_cumle_basi_buyuk_harf_terim_kaniti_degildir(acik):
    user = _istem(["They entered. Seven chains lay on the floor."], {"Seven": "Yediler"})
    assert ISARET in _satir(user, "Seven")


def test_cumle_ortasinda_buyuk_harf_terimdir(acik):
    user = _istem(["He summoned the Armor and dismissed the armor of others."], {"Armor": "Zırh"})
    assert ISARET not in user


def test_koseli_parantez_icindeki_ad_terimdir(acik):
    """`_cumle_basinda` "[" sonrasını cümle başı sayar; nitelik adı ise terimdir."""
    user = _istem(["Attributes: [Swift], [Sharp]."], {"Swift": "Hızlı"})
    assert ISARET not in user


def test_ingilizce_korunan_kosullu_ve_kucuk_harfli_kayit_isaretlenmez(acik):
    paras = ["The sun rose. Sun smiled at a great beast."]
    sozluk = {"Sun": "Sun", "Great": "Ulu", "beast": "Mahluk"}
    user = _istem(paras, sozluk, {"Great": "YALNIZ rütbe anlamında"})
    assert ISARET not in user


def test_isaretsiz_istem_bayrak_acikken_de_ayni(acik, monkeypatch):
    """İşaretlenecek kayıt yoksa bayrak açık da olsa prompt bayt bayt aynıdır."""
    paras = ["He summoned the Armor."]
    acik_istem = _istem(paras, {"Armor": "Zırh"})
    monkeypatch.setenv("SOZLUK_SIRADAN", "0")
    assert _istem(paras, {"Armor": "Zırh"}) == acik_istem
