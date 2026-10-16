"""Hitap onarımı (Faz A6): kararlı çiftin sapmalı paragrafı hedefli onarılır.

Cümleler uydurmadır. Model sahte: kabul kapısının her kolu ayrı sınanır."""
import json

from core import cache, karakter_defteri

SLUG = "k"
EN = ["Lena walked in.", "\"Sit down,\" Lena told Arto. \"You look tired.\"", "Arto sat."]
TR = ["Lena içeri girdi.", "\"Oturun,\" dedi Lena Arto'ya. \"Yorgun görünüyorsunuz.\"", "Arto oturdu."]
SAPMA = [{"konusan": "Lena", "muhatap": "Arto", "paragraf": 2, "bicim": "siz", "beklenen": "sen",
          "alinti": "", "elle": False}]


def _bolum():
    cache.save_chapter("https://ornek.test/k/1", {
        "book_slug": SLUG, "book_title": "K", "title": "B1", "chapter_no": 1,
        "translation": "\n\n".join(TR), "source": "\n\n".join(EN), "next_url": None,
        "prev_url": None, "detected_names": [], "chunk_count": 1, "model": "m1"})


def _uret(yanit):
    cagrilar = []

    def f(istem):
        cagrilar.append(istem)
        return json.dumps(yanit, ensure_ascii=False), "onaran"
    return f, cagrilar


def test_dogru_onarim_kabul_edilir_ve_kunyeye_girer():
    _bolum()
    uret, cagrilar = _uret({"degisiklik": True,
                            "ceviri": "\"Otur,\" dedi Lena Arto'ya. \"Yorgun görünüyorsun.\""})
    sayac = karakter_defteri.hitap_onar(SLUG, 1, SAPMA, uret=uret)
    assert sayac == {"denenen": 1, "kabul": 1}
    assert "KİTAPTAKİ HİTAP: sen" in cagrilar[0] and "KONUŞAN: Lena" in cagrilar[0]
    bolum = cache.get_chapter("https://ornek.test/k/1")
    assert "Yorgun görünüyorsun." in bolum["translation"]
    assert bolum["model"] == "m1 + onaran"
    assert cache.arsiv_listesi("https://ornek.test/k/1")  # eski hâl geri alınabilir


def test_model_degisiklik_yok_derse_dokunulmaz():
    _bolum()
    uret, _ = _uret({"degisiklik": False})
    assert karakter_defteri.hitap_onar(SLUG, 1, SAPMA, uret=uret)["kabul"] == 0
    assert cache.get_chapter("https://ornek.test/k/1")["translation"] == "\n\n".join(TR)


def test_paragrafi_yeniden_yazan_onarim_reddedilir():
    _bolum()
    # Aynı uzunlukta ama başka bir cümle: yalnız benzerlik kapısı durdurabilir.
    uret, _ = _uret({"degisiklik": True,
                     "ceviri": "Kapı çarpınca herkes sustu; masadaki mum söndü, rüzgâr içeri doldu."})
    assert karakter_defteri.hitap_onar(SLUG, 1, SAPMA, uret=uret)["kabul"] == 0


def test_model_hatasi_bolumu_bozmaz():
    _bolum()

    def patlar(istem):
        raise RuntimeError("503")
    assert karakter_defteri.hitap_onar(SLUG, 1, SAPMA, uret=patlar) == {"denenen": 1, "kabul": 0}


def test_hizasiz_bolum_denenmez():
    cache.save_chapter("https://ornek.test/k/1", {
        "book_slug": SLUG, "book_title": "K", "title": "B1", "chapter_no": 1,
        "translation": "tek blok", "source": "\n\n".join(EN), "next_url": None,
        "prev_url": None, "detected_names": [], "chunk_count": 1})
    uret, cagrilar = _uret({"degisiklik": False})
    assert karakter_defteri.hitap_onar(SLUG, 1, SAPMA, uret=uret)["denenen"] == 0
    assert cagrilar == []
