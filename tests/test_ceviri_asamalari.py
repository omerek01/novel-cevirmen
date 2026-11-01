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


# --- paragraf önerisinde çalışma (2026-10-19, kullanıcı isteği) ---

def test_paragraf_anahtari_varsayilan_kapali_ve_bolumden_bagimsiz(monkeypatch):
    # Bölümde açık olan aşama paragraf önerisinde kendiliğinden ÇALIŞMAZ: öneri
    # hafif kalsın diye kısıtlandı; açmak ayrı ve bilinçli bir seçim.
    monkeypatch.setenv("CEVIRI_CILALA", "1")
    assert ca.acik("cilalama") is True
    assert ca.paragrafta_acik("cilalama") is False
    ca.ayarla_paragraf("cilalama", True)
    assert ca.paragrafta_acik("cilalama") is True
    # Bölüm anahtarı kapansa da paragraf seçimi durur (bağımsız iki seçim).
    ca.ayarla("cilalama", False)
    assert ca.paragrafta_acik("cilalama") is True
    assert ca.acik("cilalama") is False


@pytest.mark.parametrize("ad", ["analiz", "ozet", "terim_alani", "yok_boyle"])
def test_paragrafa_acilamayan_asama_reddedilir(ad):
    with pytest.raises(KeyError):
        ca.ayarla_paragraf(ad, True)
    assert ca.paragrafta_acik(ad) is False


def test_calisir_kipe_gore_dogru_anahtara_bakar(monkeypatch):
    monkeypatch.setenv("CEVIRI_KALITE", "1")
    assert ca.calisir("kalite") is True
    assert ca.calisir("kalite", paragraf=True) is False
    ca.ayarla_paragraf("kalite", True)
    ca.ayarla("kalite", False)
    assert ca.calisir("kalite") is False
    assert ca.calisir("kalite", paragraf=True) is True


def test_durum_paragraf_alanini_yalniz_uygun_asamada_verir():
    ca.ayarla_paragraf("kalite", True)
    durum = {a["ad"]: a for a in ca.durum()}
    assert durum["kalite"]["paragraf"] is True
    assert durum["cilalama"]["paragraf"] is False
    for ad in ("analiz", "ozet", "terim_alani"):
        assert durum[ad]["paragraf"] is None


def test_uc_paragraf_kapsamini_yazar():
    c = _client()
    r = c.post("/api/settings/asamalar", json={"ad": "cilalama", "acik": True, "kapsam": "paragraf"})
    assert r.status_code == 200
    cilalama = next(a for a in r.json()["asamalar"] if a["ad"] == "cilalama")
    assert cilalama["paragraf"] is True
    assert ca.paragrafta_acik("cilalama") is True
    # Bölüm seçimine dokunulmadı.
    assert ca._kayit("cilalama") == ""


@pytest.mark.parametrize("govde", [
    {"ad": "analiz", "acik": True, "kapsam": "paragraf"},   # paragrafa açılamaz
    {"ad": "kalite", "acik": True, "kapsam": "kitap"},      # bilinmeyen kapsam
])
def test_uc_gecersiz_paragraf_isteginde_400(govde):
    assert _client().post("/api/settings/asamalar", json=govde).status_code == 400


def _istek(conn, islem, url, asama, model, ms, sonuc="basari", kod=200, zaman=None):
    conn.execute(
        "INSERT INTO api_olay (zaman, islem, amac, asama, url, tur, model, sonuc, http_kodu,"
        " sure_ms) VALUES (?, ?, 'prefetch', ?, ?, 'istek', ?, ?, ?, ?)",
        (zaman or time.time(), islem, asama, url, model, sonuc, kod, ms),
    )


def test_sure_dokumu_asama_model_ve_basarisiz_denemeleri_ayirir(monkeypatch):
    """Bölüm künyesi: aşama + model başına süre, boşa giden denemeler, kapalı aşamalar."""
    monkeypatch.setenv("CEVIRI_CILALA", "0")
    api_durum._connect().close()
    basla = time.time()
    conn = db.connect()
    try:
        argon = "vertex/gemini-4-argon"
        _istek(conn, "i1", "u1", None, argon, 87_000, "gecici", 504)  # zaman aşımı
        _istek(conn, "i1", "u1", None, argon, 70_000)
        _istek(conn, "i1", "u1", "kalite_denetimi", argon, 30_000)
        _istek(conn, "i1", "u1", "kalite_onarimi", "gemini-3.6-flash", 5_000)
        _istek(conn, "i1", "u1", "kalinti_onarimi", argon, 3_000)
        _istek(conn, "i1", "baska-url", None, argon, 99_000)  # başka bölüm: sayılmaz
        _istek(conn, "i2", "u1", None, argon, 99_000)  # başka işlem: sayılmaz
        conn.commit()
    finally:
        conn.close()
    d = ca.sure_dokumu("i1", "u1", basla, basla + 200, indirme_sn=2, bekleme_sn=1)
    asama = {a["etiket"]: a["sn"] for a in d["asamalar"]}
    assert asama == {"Çeviri": 157.0, "Kalite denetimi": 35.0,
                     "Düzeltme: İngilizce kalan paragraflar": 3.0}
    assert d["toplam_sn"] == 200 and d["oteki_sn"] == 2.0  # 200 - 195 - 2 - 1
    m = {x["model"]: x for x in d["modeller"]}
    assert m[argon]["etiket"] == "4 Argon · ücretli"
    assert m[argon]["istek"] == 4 and m[argon]["basarisiz"] == 1
    assert m[argon]["basarisiz_sn"] == 87.0 and m[argon]["nedenler"] == {"zaman aşımı": 1}
    assert d["modeller"][0]["model"] == argon  # en çok süre alan önce
    assert "Türkçe cilalama" in d["kapali"]


def test_sure_dokumu_islem_yoksa_bos_doner():
    d = ca.sure_dokumu(None, "u1", 100.0, 130.0)
    assert d["asamalar"] == [] and d["modeller"] == [] and d["toplam_sn"] == 30.0
