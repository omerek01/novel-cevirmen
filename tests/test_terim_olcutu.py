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


def test_istem_kurallari_bayragi(monkeypatch):
    monkeypatch.delenv("SOZLUK_TERIM_OLCUTU", raising=False)
    monkeypatch.delenv("CEVIRI_ISTEM_KURALLARI", raising=False)
    assert translate.sistem_talimati() is None and translate._ret_notu("x") == ""
    monkeypatch.setenv("CEVIRI_ISTEM_KURALLARI", "1")
    sistem = translate.sistem_talimati()
    assert "'Huh?' -> 'Ha?'" in sistem and "RÜN BLOKLARI" in sistem and "DİYALOG VE ANLATIM" in sistem
    # Kurallar JSON sözleşmesinden ÖNCE ve tek kez
    assert sistem.index("DİYALOG VE ANLATIM") < sistem.index("- Yanıtı SADECE şu JSON ile ver:")
    assert sistem.count("- Yanıtı SADECE şu JSON ile ver:") == 1
    assert "adlandıran her ifade detected_terms'e girer" in sistem  # terim bayrağı ayrı
    assert translate._ret_notu("kısa") == "kısa"
    monkeypatch.setenv("SOZLUK_TERIM_OLCUTU", "1")
    assert "South, North" in translate.sistem_talimati() and "RÜN BLOKLARI" in translate.sistem_talimati()


def test_reddedilen_denemede_sebep_isteme_girer(monkeypatch):
    istemler = []

    def sahte(_f, _m, user, **_k):
        istemler.append(user)
        raise translate.TranslateError("dur")
    monkeypatch.setattr(translate, "_izli_uret", sahte)
    for gb in ("", "çeviri kısa çıktı"):
        try:
            translate._translate_chunk(None, ("m",), PARAS, SOZLUK, "", geri_bildirim=gb)
        except translate.TranslateError:
            pass
    assert "REDDEDİLDİ" not in istemler[0]
    assert "ÖNCEKİ DENEMEN REDDEDİLDİ: çeviri kısa çıktı" in istemler[1]
