"""Bölüm özeti zinciri (AI Novel Translation yöntemi, `CEVIRI_OZET=1`).

Her bölümde çeviriden önce tek özet çağrısı: önceki bölümün kayıtlı özeti + ilgili
sözlük + bölüm -> bu bölümün kısa Türkçe özeti. Özet saklanır, sonraki bölümün özet
çağrısına gider; çeviriye YALNIZ bu bölümün özeti girer. Model çağrısı yoktur;
metinler uydurmadır.
"""
import json
from types import SimpleNamespace

import pytest

from core import pipeline, translate


def cevap(veri):
    return SimpleNamespace(text=json.dumps(veri, ensure_ascii=False),
                           candidates=[SimpleNamespace(finish_reason="STOP")])


def zincir():
    from core import ozet_zinciri
    return ozet_zinciri


class Sahte:
    """Özet ve çeviri çağrılarını ayırıp kaydeden sahte üretici."""

    def __init__(self, ozetler, ceviri="Sunny kıyıya çıktı."):
        self.ozetler = list(ozetler); self.ceviri = ceviri
        self.ozet_istemleri = []; self.ceviri_istemleri = []; self.ceviri_sistemleri = []

    def __call__(self, *args, **kwargs):
        if kwargs.get("system") == zincir().OZET_TALIMATI:
            self.ozet_istemleri.append(json.loads(args[2]))
            ozet = self.ozetler.pop(0)
            if isinstance(ozet, Exception):
                raise ozet
            return (ozet if isinstance(ozet, SimpleNamespace) else cevap({"ozet": ozet})), "m"
        self.ceviri_istemleri.append(args[2]); self.ceviri_sistemleri.append(kwargs.get("system"))
        return cevap({"translation": "[[1]] " + self.ceviri, "detected_names": [],
                      "detected_terms": {}}), "m"


@pytest.fixture
def sahte(monkeypatch):
    monkeypatch.setattr(translate, "_gemini_fabrikasi", lambda key: object())
    def kur(ozetler, **kw):
        s = Sahte(ozetler, **kw)
        monkeypatch.setattr(translate, "_generate_with_fallback", s)
        return s
    return kur


def cevir(metin="Sunny reached the shore.", **kw):
    return translate.translate_chapter(metin, "test", models=("m",), **kw)


def test_ayar_kapaliyken_ozet_cagrisi_yok_istem_ayni(sahte, monkeypatch):
    monkeypatch.delenv("CEVIRI_OZET", raising=False)
    s = sahte([])
    sonuc = cevir(book_slug="kitap", bolum_url="u://1", bolum_no=1)
    assert sonuc["translation"] == "Sunny kıyıya çıktı."
    assert s.ozet_istemleri == [] and "BAĞLAM ÖZETİ" not in s.ceviri_istemleri[0]


def test_yalniz_bu_bolumun_ozeti_ceviriye_girer_onceki_ozet_yalniz_ozet_cagrisina(sahte, monkeypatch):
    monkeypatch.setenv("CEVIRI_OZET", "1")
    q = zincir()
    q.yaz("u://1", "kitap", 1, "He looked at the sea.", "Önceki bölümde Sunny denize baktı.")
    s = sahte(["Sunny sonunda kıyıya çıkar."])
    onceki = {"url": "u://1", "book_slug": "kitap", "chapter_no": 1, "source": "He looked at the sea."}
    cevir(book_slug="kitap", bolum_url="u://2", bolum_no=2, onceki_bolum=onceki)
    giris = s.ozet_istemleri[0]
    assert giris["onceki_bolum_ozeti"] == "Önceki bölümde Sunny denize baktı."
    assert giris["bolum"] == "Sunny reached the shore."
    istem = s.ceviri_istemleri[0]
    assert "BAĞLAM ÖZETİ" in istem and "Sunny sonunda kıyıya çıkar." in istem
    assert "Önceki bölümde Sunny denize baktı." not in istem
    # Çıktı biçimi değişmez: terim tespiti bugünkü gibi çeviri çağrısında kalır.
    assert s.ceviri_sistemleri == [None]


def test_ozet_saklanir_ve_sonraki_bolumun_ozet_cagrisina_gider(sahte, monkeypatch):
    monkeypatch.setenv("CEVIRI_OZET", "1")
    s = sahte(["Birinci bölümün özeti.", "İkinci bölümün özeti."])
    cevir("He looked at the sea.", book_slug="kitap", bolum_url="u://1", bolum_no=1)
    assert s.ozet_istemleri[0]["onceki_bolum_ozeti"] == ""   # zincir boş başlar, ek çağrı yok
    onceki = {"url": "u://1", "book_slug": "kitap", "chapter_no": 1, "source": "He looked at the sea."}
    cevir(book_slug="kitap", bolum_url="u://2", bolum_no=2, onceki_bolum=onceki)
    assert s.ozet_istemleri[1]["onceki_bolum_ozeti"] == "Birinci bölümün özeti."
    assert zincir().oku("u://2", "Sunny reached the shore.") == "İkinci bölümün özeti."


def test_kaynak_degistiyse_eski_ozet_kullanilmaz_bosluk_farki_koparmaz():
    q = zincir()
    q.yaz("u://1", "kitap", 1, "First line.\n\nSecond line.", "Özet.")
    assert q.oku("u://1", "First line.\nSecond line.  ") == "Özet."
    assert q.oku("u://1", "First line.\n\nA different second line.") == ""
    assert q.oku(None, "First line.") == "" and q.oku("u://yok", "First line.") == ""


@pytest.mark.parametrize("bozuk", [
    SimpleNamespace(text="{}", candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")]),
    SimpleNamespace(text="özet değil", candidates=[SimpleNamespace(finish_reason="STOP")]),
    SimpleNamespace(text='{"ozet": ""}', candidates=[SimpleNamespace(finish_reason="STOP")]),
    RuntimeError("kota"),
])
def test_ozet_cagrisi_bozuksa_ceviri_ozetsiz_surer_kayit_yazilmaz(sahte, monkeypatch, bozuk):
    monkeypatch.setenv("CEVIRI_OZET", "1")
    s = sahte([bozuk])
    sonuc = cevir(book_slug="kitap", bolum_url="u://1", bolum_no=1)
    assert sonuc["translation"] == "Sunny kıyıya çıktı."
    assert "BAĞLAM ÖZETİ" not in s.ceviri_istemleri[0]
    assert zincir().oku("u://1", "Sunny reached the shore.") == ""


def test_cok_uzun_ozet_cumle_sonundan_kisaltilir():
    q = zincir()
    cumle = "Sunny kıyıya çıktı ve uzun uzun denize baktı. "
    uzun = cumle * (q.MAX_OZET // len(cumle) + 5)
    kisa = q._kisalt(" ".join(uzun.split()))
    assert len(kisa) <= q.MAX_OZET and kisa.endswith(".")


def test_pipeline_ozet_acikken_onceki_bolumu_verir(monkeypatch):
    monkeypatch.setenv("CEVIRI_OZET", "1")
    monkeypatch.setattr(pipeline.cache, "onceki_kaynak", lambda slug, prev, no: {"url": "u://1"})
    ek = pipeline._roman_baglami("kitap", "u://2", "u://1", 2)
    assert ek["onceki_bolum"] == {"url": "u://1"} and ek["bolum_url"] == "u://2"
    monkeypatch.setenv("CEVIRI_OZET", "0")
    assert pipeline._roman_baglami("kitap", "u://2", "u://1", 2) == {}
