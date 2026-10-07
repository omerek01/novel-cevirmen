"""Çift anlamlı ad (Saint) çeviri sonrası denetim + hedefli onarım (Faz 1H) — çevrimdışı.

Sınıflayıcı yalnız ADAY seçer; kararı onarım isteğindeki model verir. Kabul ölçütü:
aynı denetimden geçmek + paragrafın geri kalanını korumak. Metinler yapay."""
from __future__ import annotations

import json

from core import translate, varlik_grafigi as vg

KURAL = vg.KITAP_PROFILLERI["shadow-slave"]["anlam_dugumleri"]["Saint"]["ayirici"]
TANIM = [{"kayit": "Saint", "taban_karsilik": "Aziz", "anlam_karsilik": "Saint",
          "anlam_aciklama": "Sunny'nin gölgesinin adı", "ayirici": KURAL}]
EN = ["Sunny walked into the hall.", "He summoned Saint and waited.", "Nothing moved."]


class _Yanit:
    def __init__(self, veri):
        self.text = json.dumps(veri, ensure_ascii=False)


def _calistir(monkeypatch, tr, yanit):
    istemler = []

    def sahte(_f, models, user, system=None, max_tokens=None):
        istemler.append((user, system))
        return _Yanit(yanit), models[0]

    monkeypatch.setattr(translate, "_generate_with_fallback", sahte)
    tr = list(tr)
    metrik = translate._anlam_denetle_ve_onar(lambda: None, ("m",), tr, EN, TANIM, 400, {}, {})
    return tr, metrik, istemler


def test_gercek_hata_hedefli_onarilir(monkeypatch):
    tr = ["Sunny salona girdi.", "Aziz'i çağırdı ve bekledi.", "Hiçbir şey kıpırdamadı."]
    yeni, m, istemler = _calistir(monkeypatch, tr, {"degisiklik": True, "ceviri": "Saint'i çağırdı ve bekledi."})
    assert yeni[1] == "Saint'i çağırdı ve bekledi." and yeni[0] == tr[0] and yeni[2] == tr[2]
    assert (m["saint_flags"], m["saint_repairs_attempted"], m["saint_repairs_accepted"], m["kalan"]) == (1, 1, 1, 0)
    # Onarım isteği YALNIZ etkilenen paragrafı + yerel bağlamı taşır, bölümün tamamını değil.
    user, system = istemler[0]
    assert "He summoned Saint" in user and "Sunny walked" in user and "Nothing moved" in user
    assert "ANLAM 1" in user and "ANLAM 2" in user and system == translate.ANLAM_ONARIM_INSTRUCTION


def test_yanlis_alarmda_ceviri_korunur(monkeypatch):
    tr = ["Sunny salona girdi.", "Aziz'i çağırdı ve bekledi.", "Hiçbir şey kıpırdamadı."]
    yeni, m, _ = _calistir(monkeypatch, tr, {"degisiklik": False})
    assert yeni == tr
    assert (m["saint_repairs_accepted"], m["saint_false_positive_or_rejected"], m["kalan"]) == (0, 1, 1)


def test_paragrafi_yeniden_yazan_onarim_reddedilir(monkeypatch):
    tr = ["Sunny salona girdi.", "Aziz'i çağırdı ve bekledi.", "Hiçbir şey kıpırdamadı."]
    yeni, m, _ = _calistir(monkeypatch, tr, {"degisiklik": True, "ceviri": "Saint geldi."})
    assert yeni == tr and m["saint_false_positive_or_rejected"] == 1


def test_hala_yanlis_onarim_reddedilir(monkeypatch):
    tr = ["Sunny salona girdi.", "Aziz'i çağırdı ve bekledi.", "Hiçbir şey kıpırdamadı."]
    yeni, m, _ = _calistir(monkeypatch, tr, {"degisiklik": True, "ceviri": "Aziz'i çağırdı ve bekledi!"})
    assert yeni == tr and m["saint_false_positive_or_rejected"] == 1


def test_temiz_bolumde_istek_atilmaz(monkeypatch):
    tr = ["Sunny salona girdi.", "Saint'i çağırdı ve bekledi.", "Hiçbir şey kıpırdamadı."]
    yeni, m, istemler = _calistir(monkeypatch, tr, {"degisiklik": False})
    assert yeni == tr and istemler == [] and m["saint_flags"] == 0 and m["saint_checks"] == 1
