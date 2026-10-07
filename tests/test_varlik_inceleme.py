"""Varlık grafiği inceleme kararlarının uygulanması (`scripts/varlik_inceleme.py`)."""
from __future__ import annotations

import varlik_inceleme

from core import glossary, varlik_grafigi as vg

KITAP = "shadow-slave"


def _kur():
    for k in ("Sunny", "Nephis", "Kido", "Artisans", "Jet", "Awakened", "Ascended"):
        glossary.set_term(KITAP, k, k)
    k = vg.DugumCozucu(KITAP).coz
    vg.bag_ekle(KITAP, k("Sunny"), "yoldasi", k("Nephis"), 46, "a", "model", 0.9)
    vg.bag_ekle(KITAP, k("Nephis"), "ogretmeni", k("Sunny"), 213, "b", "model", 0.9)
    vg.bag_ekle(KITAP, k("Kido"), "lideri", k("Artisans"), 313, "c", "model", 0.9)
    vg.bag_ekle(KITAP, k("Jet"), "rutbesi", k("Awakened"), 25, "d", "model", 0.9)
    vg.bag_ekle(KITAP, k("Jet"), "rutbesi", k("Ascended"), 17, "e", "model", 0.9)
    return k


def _anahtar(k, a, iliski, b, **ek):
    x, y = k(a), k(b)
    if vg.ILISKILER[iliski].get("simetrik") and x > y:
        x, y = y, x
    return {"a_k": x, "iliski": iliski, "b_k": y, **ek}


def test_kararlar_kimlikle_uygulanir():
    k = _kur()
    sayac = varlik_inceleme.uygula(KITAP, [
        _anahtar(k, "Sunny", "yoldasi", "Nephis", karar="onay"),
        _anahtar(k, "Nephis", "ogretmeni", "Sunny", karar="ters"),
        _anahtar(k, "Kido", "lideri", "Artisans", karar="ters_duzelt", yeni_iliski="lideri"),
        _anahtar(k, "Jet", "rutbesi", "Awakened", karar="ret"),
        _anahtar(k, "Jet", "rutbesi", "Ascended", karar="belirsiz"),
        {"a_k": "yok", "iliski": "yoldasi", "b_k": "yok2", "karar": "onay"},
    ])
    assert sayac == {"onay": 1, "ters": 1, "ters_duzelt": 1, "ret": 1, "belirsiz": 1, "bulunamadi": 1}
    durum = {(b["kaynak"], b["iliski"], b["hedef"]): (b["durum"], b["origin"], b["kanit"], b["ilk_bolum"])
             for b in vg.baglar(KITAP, durumlar=("aday", "onaylandi", "reddedildi"))}
    assert durum[("Sunny", "ogretmeni", "Nephis")] == ("onaylandi", "manual", "b", 213)  # yön çevrildi, kanıt korundu
    assert durum[("Nephis", "ogretmeni", "Sunny")][0] == "reddedildi"
    assert durum[("Artisans", "lideri", "Kido")][0] == "onaylandi"
    assert durum[("Jet", "rutbesi", "Awakened")][0] == "reddedildi"
    assert durum[("Jet", "rutbesi", "Ascended")][0] == "aday"
    # Reddedilen bağ otomatik yolla dirilmez.
    assert vg.bag_ekle(KITAP, k("Jet"), "rutbesi", k("Awakened"), 5, "x", "model") is False
