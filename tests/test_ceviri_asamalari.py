"""Çeviri aşamalarını okuyucudan aç/kapa: kayıtlı ayar > ortam değişkeni > varsayılan."""
from __future__ import annotations

import pathlib
import re
import time

import pytest

from core import api_durum, ceviri_asamalari as ca, db

APP = pathlib.Path(__file__).resolve().parents[1] / "app"


def _client():
    from fastapi.testclient import TestClient

    import server

    return TestClient(server.app)


@pytest.mark.parametrize("ad, ortam, deger, beklenen", [
    ("analiz", "CEVIRI_ANALIZ", None, True),      # varsayılan açık
    ("analiz", "CEVIRI_ANALIZ", "0", False),
    ("ozet", "CEVIRI_OZET", None, False),         # varsayılan kapalı
    ("ozet", "CEVIRI_OZET", "1", True),
    ("cilalama", "CEVIRI_CILALA", "1", True),
    ("cilalama", "CEVIRI_CILALA", "evet", False),  # varsayılanı kapalı olan yalnız "1" ile açılır
    ("kalite", "CEVIRI_KALITE", "0", False),
    ("terim_alani", "CEVIRI_TERIM_ALANI_ONARIM", None, True),
])
def test_ayar_yokken_ortam_degiskeni_gecer(monkeypatch, ad, ortam, deger, beklenen):
    # Düğmeye hiç dokunulmadıysa davranış bugünküyle aynı kalmalı.
    if deger is None:
        monkeypatch.delenv(ortam, raising=False)
    else:
        monkeypatch.setenv(ortam, deger)
    assert ca.acik(ad) is beklenen


def test_kayitli_ayar_ortam_degiskenini_ezer(monkeypatch):
    monkeypatch.setenv("CEVIRI_CILALA", "1")
    ca.ayarla("cilalama", False)
    assert ca.acik("cilalama") is False
    monkeypatch.setenv("CEVIRI_KALITE", "0")
    ca.ayarla("kalite", True)
    assert ca.acik("kalite") is True


def test_bilinmeyen_asama_reddedilir():
    with pytest.raises(KeyError):
        ca.ayarla("yok_boyle", True)


def test_uc_ayari_yazar_ve_durumu_doner(monkeypatch):
    monkeypatch.setenv("CEVIRI_CILALA", "1")
    c = _client()
    r = c.get("/api/settings/asamalar")
    assert r.status_code == 200
    cilalama = next(a for a in r.json()["asamalar"] if a["ad"] == "cilalama")
    assert cilalama["acik"] is True and cilalama["kaynak"] == "ortam"
    r = c.post("/api/settings/asamalar", json={"ad": "cilalama", "acik": False})
    assert r.status_code == 200
    cilalama = next(a for a in r.json()["asamalar"] if a["ad"] == "cilalama")
    assert cilalama["acik"] is False and cilalama["kaynak"] == "ayar"
    assert ca.acik("cilalama") is False


def test_uc_bilinmeyen_asamada_400():
    r = _client().post("/api/settings/asamalar", json={"ad": "yok", "acik": True})
    assert r.status_code == 400


def _olay(conn, islem, url, asama, ms, amac="prefetch", zaman=None):
    conn.execute(
        "INSERT INTO api_olay (zaman, islem, amac, asama, url, tur, sonuc, sure_ms)"
        " VALUES (?, ?, ?, ?, ?, 'istek', 'basari', ?)",
        (zaman or time.time(), islem, amac, asama, url, ms),
    )


def test_olcum_bolum_basina_asama_suresini_hesaplar():
    api_durum._connect().close()  # tabloyu kur
    conn = db.connect()
    try:
        _olay(conn, "i1", "u1", None, 30_000)            # çeviri (aşama boş)
        _olay(conn, "i1", "u1", "cilalama", 40_000)
        _olay(conn, "i1", "u1", "kalite_denetimi", 10_000)
        _olay(conn, "i2", "u2", None, 20_000)
        _olay(conn, "i2", "u2", "kalite_denetimi", 6_000)
        _olay(conn, "i2", "u2", "kalite_onarimi", 4_000)
        # Bölüm çevirisi olmayan işler ölçüme GİRMEZ (varlık grafiğinin aşaması da boş).
        _olay(conn, "i3", None, None, 99_000, amac="varlik_cikarim")
        _olay(conn, "i4", "u4", None, 99_000, amac="paragraf_yeniden")
        conn.commit()
    finally:
        conn.close()
    o = ca.olcum()
    assert o["bolum"] == 2
    assert o["toplam_ort_sn"] == 55.0 and o["ceviri_ort_sn"] == 25.0
    assert o["asamalar"]["cilalama"] == {"bolum_orani": 0.5, "ort_sn": 20.0}
    assert o["asamalar"]["kalite"] == {"bolum_orani": 1.0, "ort_sn": 10.0}
    assert o["asamalar"]["terim_alani"] == {"bolum_orani": 0.0, "ort_sn": 0.0}


def test_olcum_kayit_yokken_bos_doner():
    assert ca.olcum()["bolum"] == 0


def test_bayraklar_yalniz_yardimcidan_okunur():
    # Tel tuzağı: aşama bayrağını doğrudan `os.getenv` ile okuyan yeni bir yer, okuyucudaki
    # düğmeyi SESSİZCE etkisiz bırakır (düğme "kapalı" der, aşama yine çalışır).
    desen = re.compile(r"os\.getenv\(\s*\"(%s)\"" % "|".join(a["ortam"] for a in ca.ASAMALAR))
    ihlal = [f"{p.relative_to(APP)}:{i}"
             for p in APP.rglob("*.py") if p.name != "ceviri_asamalari.py"
             for i, satir in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
             if desen.search(satir)]
    assert ihlal == []
