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


def _bolum(no, ciftler, zaman=None, sapma=None, sizinti=None):
    conn = cache._connect()
    conn.execute(
        "INSERT INTO chapters (url, book_slug, chapter_no, translation, source_text, created_at, karsilik_sapmasi, "
        "glossary_leaks) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (f"https://y/{no}-{zaman or 0}", KITAP, no, "\n\n".join(t for _e, t in ciftler),
         "\n\n".join(e for e, _t in ciftler),
         zaman or time.time(), json.dumps(sapma) if sapma is not None else None,
         json.dumps(sizinti) if sizinti is not None else None),
    )
    conn.commit()
    conn.close()


def _havuz():
    _bolum(8, [("Mira stood at the Iron Gate.", "Mira Demir Kapı'nın önünde durdu."),
               ("The Old Tower was silent.", "Eski Kule sessizdi.")], sapma={}, sizinti={})
    _bolum(9, [("She left the Iron Gate behind.", "Demir Kapı'yı geride bıraktı."),
               ("Red Moon rose.", "Kızıl Ay yükseldi.")])
    # 10 ve 11: künyede Iron Gate iki bölümde sapmış ("Demir Geçit"), Old Tower iki bölümde İngilizce
    # kalmış; Mira (korunan ad) tek bölümde.
    _bolum(10, [("The Iron Gate opened.", "Demir Geçit açıldı."),
                ("Old Tower bells rang.", "Old Tower çanları çaldı."),
                ("Red Moon faded.", "Kızıl Ay soldu.")],
           sapma={"Iron Gate": "Demir Kapı"}, sizinti={"Old Tower": "Eski Kule", "Mira": "Mira"})
    _bolum(11, [("Guards held the Iron Gate.", "Muhafızlar Demir Geçit'i tuttu.")],
           sapma={"Iron Gate": "Demir Kapı"}, sizinti={"Old Tower": "Eski Kule"})
    # GELECEK bölüm: künyesi de örneği de sayılmaz.
    _bolum(13, [("The Iron Gate fell.", "Demir Kapı yıkıldı.")], sapma={"Mira": "Mira", "Iron Gate": "Demir Kapı"})


def _sec(metin, kosullar=None, no=12):
    return to.secim(metin, SOZLUK, kosullar or {}, cache.bellek_havuzu(KITAP, no),
                    to.sorunlu_terimler(KITAP, no, SOZLUK))


def test_sorunlu_terimler_kunyeden_okur_gelecegi_ve_eski_kaydi_saymaz():
    _havuz()
    assert to.sorunlu_terimler(KITAP, 12, SOZLUK) == {"Iron Gate": 2, "Old Tower": 2}
    # Aynı bölümün yeni kaydı eskisinin yerine geçer; bozuk künye atlanır; pencere dışı sayılmaz.
    _bolum(11, [("Guards.", "Muhafızlar.")], zaman=time.time() + 5, sapma={})
    _bolum(7, [("x", "y")], sapma="bozuk")
    conn = cache._connect()
    conn.execute("UPDATE chapters SET karsilik_sapmasi = '{oops' WHERE book_slug = ? AND chapter_no = 7", (KITAP,))
    conn.commit()
    conn.close()
    assert to.sorunlu_terimler(KITAP, 12, SOZLUK) == {}  # her terim artık tek bölümde
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(to, "MIN_BOLUM", 1)
        assert to.sorunlu_terimler(KITAP, 12, SOZLUK) == {"Iron Gate": 1, "Old Tower": 1, "Mira": 1}
        assert to.sorunlu_terimler(KITAP, 12, SOZLUK, geri=1) == {}


def test_tek_bolumluk_ve_karsiligi_degismis_bulgu_sayilmaz():
    # Canlı vaka: tek bölümün bayat künyesi 30 bölüme yayılıyordu; sözlük sonradan değişen
    # terimin eski bulgusu da bugünkü karşılık için kanıt değildir.
    _bolum(5, [("a", "b")], sapma={"Iron Gate": "Demir Kapı"})
    _bolum(6, [("a", "b")], sizinti={"Iron Gate": "Demir Kapı"}, sapma={"Iron Gate": "Demir Kapı"})
    assert to.sorunlu_terimler(KITAP, 12, SOZLUK) == {"Iron Gate": 2}  # aynı bölümde iki alan bir sayılır
    assert to.sorunlu_terimler(KITAP, 12, dict(SOZLUK, **{"Iron Gate": "Demir Geçit"})) == {}
    assert to.sorunlu_terimler(KITAP, 6, SOZLUK) == {}  # 6 dahil değil: tek bölüm kaldı


def test_secim_sapan_terimi_en_yeni_dogru_ornekle_verir_ve_sirali():
    _havuz()
    out = _sec("At dawn the Iron Gate and the Old Tower and Mira.", KOSULLAR)
    assert [(o["source"], o["sapma"], o["bolum"]) for o in out] == [("Iron Gate", 2, 9), ("Old Tower", 2, 8)]
    assert out[0]["tr"] == "Demir Kapı'yı geride bıraktı."  # yumuşamış/ekli karşılık da sayılır


def test_bolumde_gecmeyen_terim_ve_korunan_ad_alinmaz():
    _havuz()
    assert _sec("Nothing here.") == []
    from collections import Counter
    assert to.secim("Mira ran.", SOZLUK, {}, cache.bellek_havuzu(KITAP, 12), Counter({"Mira": 5})) == []


def test_kosullu_kayit_sorunlu_sayilsa_da_ornek_almaz():
    from collections import Counter
    _havuz()
    havuz = cache.bellek_havuzu(KITAP, 12)
    assert to.secim("Red Moon rose.", SOZLUK, KOSULLAR, havuz, Counter({"Red Moon": 3})) == []
    assert [o["source"] for o in to.secim("Red Moon rose.", SOZLUK, {}, havuz, Counter({"Red Moon": 3}))] == ["Red Moon"]


def test_ornek_bul_havuz_sirasindan_bagimsiz_en_yeniyi_secer():
    havuz = [{"bolum": 3, "en": "The Iron Gate.", "tr": "Demir Kapı."},
             {"bolum": 7, "en": "Iron Gate again.", "tr": "Yine Demir Kapı."},
             {"bolum": 5, "en": "Iron Gate.", "tr": "Demir Kapı."}]
    assert to.ornek_bul("Iron Gate", "Demir Kapı", havuz)["bolum"] == 7


def test_ornek_yoksa_ya_da_uzunsa_terim_atlanir(monkeypatch):
    _bolum(10, [("The Iron Gate opened.", "Demir Geçit açıldı.")], sapma={"Iron Gate": "Demir Kapı"})
    _bolum(11, [("The Iron Gate shut.", "Demir Geçit kapandı.")], sapma={"Iron Gate": "Demir Kapı"})
    assert _sec("Iron Gate.") == []  # doğru kullanım yok
    _bolum(9, [("The Iron Gate stood " + "very " * 100 + "tall.", "Demir Kapı çok uzundu.")])
    assert _sec("Iron Gate.") == []
    monkeypatch.setattr(to, "ORNEK_UST_KARAKTER", 10_000)
    assert _sec("Iron Gate.")[0]["bolum"] == 9


def test_en_cok_terim_siniri(monkeypatch):
    _havuz()
    monkeypatch.setattr(to, "EN_COK_TERIM", 1)
    assert len(_sec("Iron Gate, Old Tower.")) == 1


def test_hazirla_sorunlu_terim_yoksa_havuzu_hic_okumaz(monkeypatch):
    monkeypatch.setenv("CEVIRI_TERIM_ORNEK", "1")
    _bolum(10, [("The Iron Gate opened.", "Demir Kapı açıldı.")], sapma={}, sizinti={})
    monkeypatch.setattr(cache, "bellek_havuzu", lambda *a, **k: pytest.fail("havuz okundu"))
    assert to.hazirla(KITAP, 12, "Iron Gate", SOZLUK, {}) is None


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
