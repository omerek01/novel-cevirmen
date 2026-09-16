"""Sözlük silme: silinen kayıt yanıtta döner, geri alma kaydı TAM geri getirir.

Belge (2026-09-16): "Silme sonrasında geri alma sunulmalı." Geri almanın doğru
olması için yalnız karşılık değil KOŞUL ve KÖKEN de dönmeli — aksi hâlde geri
alınan kayıt "elle, şimdi eklendi" görünür ve prompt'taki bağlam kuralı kaybolur.
Silinen satır sunucudan döner; istemci onu içe aktarma ucuyla (dosya stratejisi)
geri yazar.
"""
from __future__ import annotations

from core import glossary

KITAP = "gumus-kule"


def _client():
    from fastapi.testclient import TestClient

    import server

    return TestClient(server.app)


def test_silme_silinen_satiri_dondurur():
    glossary.merge_terms(KITAP, {"Great": "Ulu"}, "auto", 4, {"Great": "Ulu bir yaratık."})
    glossary.set_kosul(KITAP, "Great", "rütbe")
    silinen = glossary.delete_term(KITAP, "Great")
    assert silinen["source"] == "Great"
    assert silinen["kosul"] == "rütbe"
    assert silinen["first_chapter"] == 4
    assert glossary.get_glossary(KITAP) == {}


def test_silme_yazim_varyantiyla_da_bulur():
    glossary.set_term(KITAP, "Ore Empire", "Ork İmparatorluğu")
    silinen = glossary.delete_term(KITAP, "OreEmpire")
    assert silinen["source"] == "Ore Empire"
    assert glossary.get_glossary(KITAP) == {}


def test_olmayan_terimi_silmek_none_doner():
    assert glossary.delete_term(KITAP, "Yok") is None


def test_uc_silinen_kaydi_dondurur_ve_geri_alma_tam_geri_getirir():
    glossary.merge_terms(KITAP, {"Great": "Ulu"}, "auto", 4, {"Great": "Ulu bir yaratık."})
    glossary.set_kosul(KITAP, "Great", "rütbe")
    once = {r["source"]: r for r in glossary.get_glossary_rows(KITAP)}["Great"]
    c = _client()

    r = c.delete(f"/api/book/{KITAP}/glossary", params={"source": "Great"})
    assert r.status_code == 200
    silinen = r.json()["silinen"]
    assert silinen["kosul"] == "rütbe"

    r = c.post(f"/api/book/{KITAP}/glossary/import",
               json={"kayitlar": [silinen], "strateji": "dosya"})
    assert r.status_code == 200
    sonra = {r["source"]: r for r in glossary.get_glossary_rows(KITAP)}["Great"]
    assert sonra == once


def test_uc_olmayan_terim_silinen_null():
    r = _client().delete(f"/api/book/{KITAP}/glossary", params={"source": "Yok"})
    assert r.status_code == 200 and r.json()["silinen"] is None
