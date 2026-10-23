"""Vertex kredi göstergesi: Google token ölçümü → saatlik tablo → kullanılan/kalan."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from core import settings, vertex_kredi as vk

SIMDI = datetime(2026, 10, 23, 12, 30, tzinfo=timezone.utc)


def _seri(model, tur, noktalar):
    return {"resource": {"labels": {"model_user_id": model}}, "metric": {"labels": {"type": tur}},
            "points": [{"interval": {"endTime": t}, "value": {"int64Value": str(n)}} for t, n in noktalar]}


@pytest.fixture
def google(monkeypatch):
    monkeypatch.setenv("VERTEX_KREDI", "1")
    monkeypatch.setenv("VERTEX_PROJE", "proje-x")
    cagri = {"seriler": [], "araliklar": []}

    def sahte(proje, bas, son):
        cagri["araliklar"].append((bas, son))
        if isinstance(cagri["seriler"], Exception):
            raise cagri["seriler"]
        return cagri["seriler"]

    monkeypatch.setattr(vk, "_zaman_serisi", sahte)
    return cagri


def test_saatlik_toplam_ve_maliyet(google):
    google["seriler"] = [
        # 10:00 noktası 09:00-10:00 saatidir
        _seri("gemini-3.8-flash", "input", [("2026-10-23T10:00:00Z", 1_000_000)]),
        _seri("gemini-3.8-flash", "output", [("2026-10-23T10:00:00Z", 200_000)]),
        _seri("gemini-2.5-pro", "output", [("2026-10-22T08:00:00Z", 100_000)]),
    ]
    assert vk.esitle(simdi=SIMDI) is None
    d = vk.durum(esitle_once=False, simdi=SIMDI)
    # 3.8: 1M×0,75 + 0,2M×3,75 = 1,50 ; 2.5-pro: 0,1M×10 = 1,00
    assert d["kullanilan"] == 2.5 and d["tahmin"] == 2.5
    assert d["kalan"] == 297.5 and d["oran"] == pytest.approx(2.5 / 300, abs=1e-4)
    assert d["son_7_gun"] == 2.5
    assert d["ilk_olcum"] == "2026-10-22T07:00Z"
    assert [m["model"] for m in d["modeller"]] == ["gemini-3.8-flash", "gemini-2.5-pro"]


def test_ayni_saat_yeniden_gelince_ustune_yazilir(google):
    google["seriler"] = [_seri("gemini-4-argon", "output", [("2026-10-23T10:00:00Z", 100_000)])]
    vk.esitle(simdi=SIMDI)
    google["seriler"] = [_seri("gemini-4-argon", "output", [("2026-10-23T10:00:00Z", 300_000)])]
    vk.esitle(zorla=True, simdi=SIMDI)
    assert vk.durum(esitle_once=False, simdi=SIMDI)["kullanilan"] == 3.0  # 0,3M × 10, iki kez değil


def test_esitleme_saatte_bir_ve_kaldigi_yerden(google):
    google["seriler"] = [_seri("gemini-4-argon", "input", [("2026-10-23T10:00:00Z", 1)])]
    vk.esitle(simdi=SIMDI)
    vk.esitle(simdi=SIMDI)  # saat dolmadı: Google'a gidilmez
    assert len(google["araliklar"]) == 1
    vk.esitle(zorla=True, simdi=SIMDI)
    bas, _ = google["araliklar"][1]
    assert bas == datetime(2026, 10, 23, 7, tzinfo=timezone.utc)  # son kayıtlı saat 09 − 2


def test_konsol_okumasi_ustune_yalniz_sonrasini_ekler(google):
    google["seriler"] = [
        _seri("gemini-4-argon", "output", [("2026-10-23T09:00:00Z", 1_000_000),  # okumadan önce
                                           ("2026-10-23T12:00:00Z", 100_000)]),  # sonra (11:00 saati)
    ]
    vk.esitle(simdi=SIMDI)
    vk.ayarla(okuma_tutar=165.0, bitis="2026-12-10", simdi=datetime(2026, 10, 23, 10, 15, tzinfo=timezone.utc))
    d = vk.durum(esitle_once=False, simdi=SIMDI)
    assert d["okuma"]["tutar"] == 165.0
    assert d["tahmin"] == 1.0 and d["kullanilan"] == 166.0 and d["kalan"] == 134.0
    assert d["kalan_gun"] == 48
    vk.ayarla(okuma_sil=True)
    assert vk.durum(esitle_once=False, simdi=SIMDI)["kullanilan"] == 11.0


def test_fiyati_bilinmeyen_model_isaretlenir(google):
    google["seriler"] = [_seri("gemini-9-ultra", "input", [("2026-10-23T10:00:00Z", 5000)])]
    vk.esitle(simdi=SIMDI)
    m = vk.durum(esitle_once=False, simdi=SIMDI)["modeller"][0]
    assert m["fiyat_bilinmiyor"] is True and m["maliyet"] == 0.0 and m["giris_token"] == 5000


def test_izin_yoksa_anlasilir_hata_ve_bir_dakika_sonra_yeniden(google):
    google["seriler"] = PermissionError("izin yok")
    hata = vk.esitle(simdi=SIMDI)
    assert "monitoring.viewer" in hata
    assert vk.durum(esitle_once=False, simdi=SIMDI)["hata"] == hata
    assert vk.esitle(simdi=SIMDI) == hata  # hemen yeniden denenmez
    google["seriler"] = []
    import time as _t
    settings.set(vk.ANAHTAR_ESITLEME, str(_t.time() - vk.ESITLEME_ARALIK_SN - 1))
    assert vk.esitle(simdi=SIMDI) is None
    assert vk.durum(esitle_once=False, simdi=SIMDI)["hata"] is None


def test_kapaliyken_google_a_gidilmez(google, monkeypatch):
    monkeypatch.setenv("VERTEX_KREDI", "0")
    vk.esitle(zorla=True, simdi=SIMDI)
    assert google["araliklar"] == []
    assert vk.durum(simdi=SIMDI)["kaynak"] == "kapali"


def test_gecersiz_girdi_reddedilir():
    with pytest.raises(ValueError):
        vk.ayarla(tutar=0)
    with pytest.raises(ValueError):
        vk.ayarla(bitis="10.12.2026")


def test_uclar(google):
    import server

    istemci = TestClient(server.app)
    google["seriler"] = [_seri("gemini-3.8-flash", "output", [("2026-10-23T10:00:00Z", 400_000)])]
    r = istemci.get("/api/settings/kredi")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert r.json()["kullanilan"] == 1.5 and r.json()["tutar"] == 300.0
    r = istemci.post("/api/settings/kredi", json={"tutar": 250, "bitis": "2026-12-10", "okuma_tutar": 100})
    assert r.status_code == 200
    d = r.json()
    assert d["tutar"] == 250 and d["bitis"] == "2026-12-10" and d["okuma"]["tutar"] == 100
    assert istemci.post("/api/settings/kredi", json={"bitis": "yarın"}).status_code == 400
