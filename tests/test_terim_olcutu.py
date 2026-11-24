"""Terim ölçütü bayrağı (`SOZLUK_TERIM_OLCUTU`, 2026-11-24): kapalıyken istem bayt bayt eski."""
from core import glossary, translate

PARAS = ["Sunny walked south past the Tier marker. Well, the Saint was there."]
SOZLUK = {"Tier": "Kademe", "Saint": "Aziz", "Sunny": "Sunny"}


def test_bayrak_kapaliyken_sistem_ve_istem_aynen_kalir(monkeypatch):
    monkeypatch.delenv("SOZLUK_TERIM_OLCUTU", raising=False)
    assert translate.sistem_talimati() is None
    once = translate._build_user_prompt(PARAS, SOZLUK, "")
    tok = translate._SOZLUK_TURLERI.set(None)
    try:
        assert translate._build_user_prompt(PARAS, SOZLUK, "") == once
    finally:
        translate._SOZLUK_TURLERI.reset(tok)
    assert "[rütbe]" not in once


def test_bayrak_acikken_yeni_olcut_ve_tur_etiketi(monkeypatch):
    monkeypatch.setenv("SOZLUK_TERIM_OLCUTU", "1")
    sistem = translate.sistem_talimati()
    assert "South, North" in sistem and "Third Tier" in sistem
    assert "adlandıran her ifade detected_terms'e girer" not in sistem
    assert sistem.count("- Yanıtı SADECE şu JSON ile ver:") == 1  # JSON sözleşmesi korunur
    tok = translate._SOZLUK_TURLERI.set({"Tier": "rutbe", "Saint": "diger", "Sunny": "kisi"})
    try:
        user = translate._build_user_prompt(PARAS, SOZLUK, "")
    finally:
        translate._SOZLUK_TURLERI.reset(tok)
    assert "Tier -> Kademe  [rütbe]" in user
    assert "Saint -> Aziz  [" not in user  # `diger` etiket taşımaz
    assert "çeviriye YAZILMAZ" in user


def test_ceviri_turleri_tutulani_ve_tursuzu_almaz():
    glossary.terimi_yaz("tur-kitap", "Tier", "Kademe", tur="rutbe")
    glossary.terimi_yaz("tur-kitap", "Abyss", "Uçurum")
    glossary.merge_terms("tur-kitap", {"Weaver": "Weaver’s"}, "auto", 1, tur="kisi")  # biçimden tutulur
    assert glossary.ceviri_turleri("tur-kitap") == {"Tier": "rutbe"}
