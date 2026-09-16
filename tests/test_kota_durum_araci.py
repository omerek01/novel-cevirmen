"""`scripts/kota_durum.py` proje ayrılığı ipucu: yalnız KESİN cevaplar sayılır."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_YOL = Path(__file__).resolve().parent.parent / "scripts" / "kota_durum.py"
_spec = importlib.util.spec_from_file_location("kota_durum", _YOL)
kota_durum = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kota_durum)


def _e(acik=(), yok=()):
    return {"acik": set(acik), "yok": set(yok)}


def test_gecici_hata_projeleri_ayri_gostermez():
    # 2026-09-16 gerçek çıktı: #1'de 3.5-flash AÇIK, #2'de aynı anda 503.
    bir = _e(acik={"gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.5-flash"})
    iki = _e(acik={"gemini-3.6-flash", "gemini-2.5-flash"})
    assert kota_durum.erisim_kesin_farkli(bir, iki) is False


def test_biri_acik_oteki_404_ise_kesin_ayri():
    bir = _e(acik={"gemini-2.5-flash"})
    uc = _e(yok={"gemini-2.5-flash"})
    assert kota_durum.erisim_kesin_farkli(bir, uc) is True
    assert kota_durum.erisim_kesin_farkli(uc, bir) is True


def test_ikisi_de_404_ayrilik_kaniti_degil():
    assert kota_durum.erisim_kesin_farkli(_e(yok={"m"}), _e(yok={"m"})) is False
