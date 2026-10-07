"""Varlık grafiği boşluk bulucu (`core.varlik_bosluk`) ve hedefli soru — çevrimdışı.

Metinler yapay örneklerdir (roman metni değil)."""
from __future__ import annotations

import json

from core import cache, glossary, translate, varlik_bosluk as vb, varlik_cikarim, varlik_grafigi as vg

KITAP = "shadow-slave"


def _hazirla():
    for k, v in {"Sunny": "Sunny", "Effie": "Effie", "Jet": "Jet", "Master Jet": "Master Jet",
                 "Kai": "Kai", "Dark City": "Karanlık Şehir"}.items():
        glossary.set_term(KITAP, k, v)
    metin = (
        "Effie laughed and punched Sunny on the shoulder. "
        "Sunny and Effie walked to the Dark City together. "
        "Later, Effie told Sunny a joke.\n\n"
        "Master Jet watched the Sleepers. Master Jet smiled. Master Jet left.\n\n"
        "Kai sang. Sunny listened to Kai."
    )
    cache.save_chapter("https://x/ch-130", {
        "book_slug": KITAP, "book_title": "Shadow Slave", "title": "B130", "chapter_no": 130,
        "translation": "Çeviri.", "source": metin,
    })


def _ciftler(**kw):
    return {frozenset((c["a"], c["b"])): c for c in vb.ortak_gecisler(KITAP, **kw)}


def test_ortak_gecis_ayrik_anmalari_sayar_ic_ice_adi_saymaz():
    _hazirla()
    ciftler = _ciftler(en_az=3)
    assert frozenset(("Sunny", "Effie")) in ciftler
    assert ciftler[frozenset(("Sunny", "Effie"))]["sayi"] == 3
    # "Master Jet" içindeki `Jet` ayrı bir anma değildir.
    assert frozenset(("Jet", "Master Jet")) not in _ciftler(en_az=1)


def test_bagi_olan_cift_atlanir():
    _hazirla()
    k = vg.DugumCozucu(KITAP).coz
    vg.bag_ekle(KITAP, k("Sunny"), "yoldasi", k("Effie"), 130, None, "manual")
    assert frozenset(("Sunny", "Effie")) not in _ciftler(en_az=1)


class _Yanit:
    def __init__(self, veri):
        self.text = json.dumps(veri)


def test_hedefli_soru_kaniti_verilen_cumlelerle_dogrular(monkeypatch):
    _hazirla()
    cift = _ciftler(en_az=3)[frozenset(("Sunny", "Effie"))]

    def sahte(_f, models, user, system=None, max_tokens=None):
        assert "Sunny" in user and "Effie" in user
        return _Yanit({"baglar": [
            {"ozne": "Sunny", "iliski": "yoldasi", "nesne": "Effie",
             "kanit": "Sunny and Effie walked to the Dark City together.", "guven": 0.9},
            {"ozne": "Effie", "iliski": "dusmani", "nesne": "Sunny",
             "kanit": "Effie betrayed Sunny in the end.", "guven": 0.9},  # uydurma
        ]}), models[0]

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    sonuc = varlik_cikarim.ciftleri_sor(KITAP, [cift], api_key="x")
    assert [(g["iliski"], g["bolum"]) for g in sonuc["gecerli"]] == [("yoldasi", 130)]
    assert sonuc["red"][0]["sebep"] == "kanıt verilen cümlelerden değil"
