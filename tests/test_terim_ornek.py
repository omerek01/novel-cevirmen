"""Terim kullanım örneği (plan Faz 4, `CEVIRI_TERIM_ORNEK`) — çevrimdışı, sahte model.

Metinler testte yazılmış kısa sentetik paragraflardır (gerçek kitap metni değil)."""
from __future__ import annotations

import json
import time

import pytest

from core import cache, pipeline, terim_ornek as to, translate

KITAP = "deneme-kitap"
SOZLUK = {"Iron Gate": "Demir Kapı", "Mira": "Mira", "Red Moon": "Kızıl Ay", "Old Tower": "Eski Kule"}
KOSULLAR = {"Red Moon": "ay olarak gökte ise Kızıl Ay; tarikatsa Kızıl Ay Tarikatı"}


def _bolum(no, ciftler, zaman=None):
    conn = cache._connect()
    conn.execute(
        "INSERT INTO chapters (url, book_slug, chapter_no, translation, source_text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (f"https://y/{no}-{zaman or 0}", KITAP, no, "\n\n".join(t for _e, t in ciftler), "\n\n".join(e for e, _t in ciftler),
         zaman or time.time()),
    )
    conn.commit()
    conn.close()


def _havuz():
    _bolum(8, [("Mira stood at the Iron Gate.", "Mira Demir Kapı'nın önünde durdu."),
               ("The Old Tower was silent.", "Eski Kule sessizdi.")])
    _bolum(9, [("She left the Iron Gate behind.", "Demir Kapı'yı geride bıraktı."),
               ("Red Moon rose.", "Kızıl Ay yükseldi.")])
    # 10 ve 11: model Iron Gate'i iki kez "Demir Geçit" yaptı (sapma), Old Tower bir kez İngilizce kaldı.
    _bolum(10, [("The Iron Gate opened.", "Demir Geçit açıldı."),
                ("Old Tower bells rang.", "Old Tower çanları çaldı."),
                ("Red Moon faded.", "Kızıl Ay soldu.")])
    _bolum(11, [("Guards held the Iron Gate.", "Muhafızlar Demir Geçit'i tuttu.")])
    _bolum(13, [("The Iron Gate fell.", "Demir Kapı yıkıldı.")])  # GELECEK bölüm: örnek olamaz


def test_secim_sapan_terimi_en_yeni_dogru_ornekle_verir_ve_sirali():
    _havuz()
    out = to.secim("At dawn the Iron Gate and the Old Tower and Mira.", SOZLUK, KOSULLAR, cache.bellek_havuzu(KITAP, 12))
    assert [(o["source"], o["sapma"], o["bolum"]) for o in out] == [("Iron Gate", 2, 9), ("Old Tower", 1, 8)]
    assert out[0]["tr"] == "Demir Kapı'yı geride bıraktı."  # yumuşamış/ekli karşılık da sayılır


def test_kosullu_korunan_ad_ve_bolumde_gecmeyen_terim_alinmaz():
    _havuz()
    _bolum(11, [("Red Moon sect came.", "Kızıl Kamer Tarikatı geldi.")], zaman=time.time() + 5)
    havuz = cache.bellek_havuzu(KITAP, 12)
    assert to.secim("Red Moon and Mira.", SOZLUK, KOSULLAR, havuz) == []
    assert to.secim("Nothing here.", SOZLUK, KOSULLAR, havuz) == []


def test_kosullu_kayit_sorunlu_sayilsa_da_ornek_almaz(monkeypatch):
    # Sapma denetimi koşullu kaydı zaten saymıyor; seçim yine de kendisi dışlar (ihlal yolu sayabilir).
    _havuz()
    monkeypatch.setattr(to, "sorunlu_terimler", lambda *a: __import__("collections").Counter({"Red Moon": 3}))
    havuz = cache.bellek_havuzu(KITAP, 12)
    assert to.secim("Red Moon rose.", SOZLUK, KOSULLAR, havuz) == []
    assert [o["source"] for o in to.secim("Red Moon rose.", SOZLUK, {}, havuz)] == ["Red Moon"]


def test_ornek_bul_havuz_sirasindan_bagimsiz_en_yeniyi_secer():
    havuz = [{"bolum": 3, "en": "The Iron Gate.", "tr": "Demir Kapı."},
             {"bolum": 7, "en": "Iron Gate again.", "tr": "Yine Demir Kapı."},
             {"bolum": 5, "en": "Iron Gate.", "tr": "Demir Kapı."}]
    assert to.ornek_bul("Iron Gate", "Demir Kapı", havuz)["bolum"] == 7


def test_ornek_yoksa_ya_da_uzunsa_terim_atlanir(monkeypatch):
    _bolum(10, [("The Iron Gate opened.", "Demir Geçit açıldı.")])
    assert to.secim("Iron Gate.", SOZLUK, {}, cache.bellek_havuzu(KITAP, 12)) == []  # doğru kullanım yok
    _bolum(9, [("The Iron Gate stood " + "very " * 100 + "tall.", "Demir Kapı çok uzundu.")])
    assert to.secim("Iron Gate.", SOZLUK, {}, cache.bellek_havuzu(KITAP, 12)) == []
    monkeypatch.setattr(to, "ORNEK_UST_KARAKTER", 10_000)
    assert to.secim("Iron Gate.", SOZLUK, {}, cache.bellek_havuzu(KITAP, 12))[0]["bolum"] == 9


def test_en_cok_terim_siniri(monkeypatch):
    _havuz()
    monkeypatch.setattr(to, "EN_COK_TERIM", 1)
    assert len(to.secim("Iron Gate, Old Tower.", SOZLUK, {}, cache.bellek_havuzu(KITAP, 12))) == 1


def test_metin_yalniz_parcada_gecen_terimleri_yazar():
    ornekler = [{"source": "Iron Gate", "target": "Demir Kapı", "bolum": 9, "en": "E1", "tr": "T1", "sapma": 2},
                {"source": "Old Tower", "target": "Eski Kule", "bolum": 8, "en": "E2", "tr": "T2", "sapma": 1}]
    blok = to.metin(ornekler, ["The Iron Gate creaked."])
    assert "Iron Gate -> Demir Kapı (bölüm 9)" in blok and "EN: E1" in blok and "Old Tower" not in blok
    assert to.metin(ornekler, ["Nothing."]) == "" and to.metin(None, ["Iron Gate"]) == ""


def test_hazirla_bayrak_kapaliyken_none(monkeypatch):
    _havuz()
    assert to.hazirla(KITAP, 12, "Iron Gate", SOZLUK, {}) is None
    monkeypatch.setenv("CEVIRI_TERIM_ORNEK", "1")
    assert [o["source"] for o in to.hazirla(KITAP, 12, "Iron Gate", SOZLUK, {})] == ["Iron Gate"]
    assert to.hazirla(KITAP, None, "Iron Gate", SOZLUK, {}) is None
    assert to.hazirla(KITAP, 12, "Mira", SOZLUK, {}) is None  # seçilecek terim yok


def test_defter_kartini_geciren_her_ceviri_cagrisi_ornekleri_de_gecirir():
    """Statik tel tuzağı (`test_sozluk_kosul` kalıbı): kart ile örnek aynı yoldan isteme girer."""
    import pathlib
    import re

    kaynak = pathlib.Path("app/core/pipeline.py").read_text(encoding="utf-8")
    cagrilar = [kaynak[m.end():m.end() + 420] for m in re.finditer(r"= translate_chapter\(", kaynak)]
    kartli = [c for c in cagrilar if "defter=defter" in c]
    assert kartli, "kart geçiren çağrı bulunamadı"
    assert all("terim_ornekleri=terim_ornekleri" in c for c in kartli)


def test_pipeline_hatayi_yutar(monkeypatch):
    monkeypatch.setattr(to, "hazirla", lambda *a, **k: 1 / 0)
    assert pipeline._terim_ornekleri(KITAP, 12, "x", SOZLUK, {}) is None


class _Y:
    def __init__(self, metin):
        self.text = metin


def _sahte(istemler, ret_sarti=lambda u: False):
    tamam = json.dumps({"translation": "[[1]] Çeviri.", "detected_names": [], "detected_terms": []})
    ret = "Bu eserin satır satır çevirisini sağlayamıyorum."

    def sahte(client_factory, models, user, **kw):
        istemler.append(user)
        return _Y(ret if ret_sarti(user) else tamam), models[0]
    return sahte


ORNEK = [{"source": "Iron Gate", "target": "Demir Kapı", "bolum": 9, "en": "E1", "tr": "T1", "sapma": 2}]


def test_ornek_istemin_basina_girer_ret_alirsa_ornek_siz_denenir(monkeypatch):
    istemler = []
    monkeypatch.setattr(translate, "_izli_uret", _sahte(istemler, lambda u: "TERİM KULLANIM" in u))
    jeton = translate._TERIM_ORNEKLERI.set(ORNEK)
    try:
        out = translate._translate_chunk(None, ("m1", "m2"), ["The Iron Gate."], SOZLUK, "")
    finally:
        translate._TERIM_ORNEKLERI.reset(jeton)
    assert out["translation"].startswith("[[1]]") and out["model"] == "m1"
    assert istemler[0].startswith("TERİM KULLANIM ÖRNEKLERİ") and "TERİM KULLANIM" not in istemler[-1]
    assert istemler[-1] in istemler[0]


def test_ornek_yokken_istem_bayt_bayt_ayni(monkeypatch):
    istemler = []
    monkeypatch.setattr(translate, "_izli_uret", _sahte(istemler))
    translate._translate_chunk(None, ("m1",), ["The Iron Gate."], SOZLUK, "")
    jeton = translate._TERIM_ORNEKLERI.set(ORNEK)
    try:
        translate._translate_chunk(None, ("m1",), ["Nothing here."], SOZLUK, "")
    finally:
        translate._TERIM_ORNEKLERI.reset(jeton)
    assert istemler[0] == translate._build_user_prompt(["The Iron Gate."], SOZLUK, "", None, "")
    assert istemler[1] == translate._build_user_prompt(["Nothing here."], SOZLUK, "", None, "")


def test_translate_chapter_ornegi_cagri_sonunda_temizler(monkeypatch):
    gorulen = []
    monkeypatch.setattr(translate, "_translate_chapter_impl",
                        lambda *a, **k: gorulen.append(translate._TERIM_ORNEKLERI.get()) or {"translation": ""})
    translate.translate_chapter("x", "", terim_ornekleri=ORNEK)
    assert gorulen == [ORNEK] and translate._TERIM_ORNEKLERI.get() is None
