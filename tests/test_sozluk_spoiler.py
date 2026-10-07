"""Sözlük ucu SPOILER süzgeci (Faz 1A, 2026-10-07).

Kural: okuyucu N. bölümdeyse N'den SONRA öğrenilen bilgi uçtan HİÇ dönmez (veri
düzeyinde süzme; "spoiler verme" talimatı değil). Etkin bölüm: açık `konum`
parametresi, yoksa kitabın kayıtlı okuma konumu (grafik ucuyla aynı davranış);
`spoiler=1` süzgeci kaldırır (bilinçli istek).

Satırın `first_chapter`'ı yetmez: kayıt erken girip açıklaması (koşul/tanım) çok
sonra öğrenilen bilgiyle yeniden yazılmış olabilir. Koşul/tanımın bölüm kökeni
`kosul_bolum`/`tanim_bolum`'dur; kökeni BİLİNMEYEN alan süzülmüş görünümde gizlenir
(eski kayıtlar için bölüm UYDURULMAZ)."""
from __future__ import annotations

from fastapi.testclient import TestClient

import server
from core import glossary, library

KITAP = "spoiler-kitap"


def _kur(okur_bolumu: int | None = 100):
    library.upsert_book(KITAP, "Spoiler Kitap", f"https://x/{KITAP}/ch-1", "B1", 1)
    if okur_bolumu is not None:
        library.konum_adini_duzelt(KITAP, f"B{okur_bolumu}", okur_bolumu)
    glossary.set_term(KITAP, "Erken", "Erken")
    glossary.set_term(KITAP, "Gelecek", "Gelecek")
    glossary.set_term(KITAP, "Bilinmeyen", "Bilinmeyen")
    conn = glossary._connect()
    conn.execute("UPDATE glossary SET first_chapter = 20 WHERE book_slug = ? AND source = 'Erken'", (KITAP,))
    conn.execute("UPDATE glossary SET first_chapter = 150 WHERE book_slug = ? AND source = 'Gelecek'", (KITAP,))
    conn.commit()
    conn.close()


def _al(**params):
    with TestClient(server.app) as c:
        r = c.get(f"/api/book/{KITAP}/glossary", params=params)
    assert r.status_code == 200
    return r.json()


def test_gelecekteki_kayit_donmez():
    _kur(100)
    veri = _al(konum=100)
    assert "Erken" in veri["terms"] and "Gelecek" not in veri["terms"]
    assert {r["source"] for r in veri["rows"]} >= {"Erken"} and "Gelecek" not in {r["source"] for r in veri["rows"]}
    # Açık konum verilmezse kitabın OKUMA KONUMU kullanılır (grafik ucuyla aynı).
    assert "Gelecek" not in _al()["terms"]
    # Bilinçli istek: süzgeç yok.
    assert "Gelecek" in _al(spoiler=1)["terms"]
    # Konum ilerleyince görünür.
    assert "Gelecek" in _al(konum=200)["terms"]


def test_kokeni_bilinmeyen_kayit_gorunur_kalir():
    # Eski kayıtların çoğunda first_chapter yok; bölüm UYDURULMAZ, kayıt görünür
    # kalır (sınırlama raporlanır). `scripts/sozluk_ilk_bolum.py` kaynaktan doldurur.
    _kur(100)
    assert "Bilinmeyen" in _al(konum=100)["terms"]


def test_gec_ogrenilen_aciklama_gizlenir():
    # Kayıt 20'de girdi; açıklaması 600'de öğrenilen bilgiyle yazıldı; okur 100'de.
    _kur(100)
    glossary.terimi_yaz(KITAP, "Erken", "Erken", kosul="gizli kimliği: kral")
    glossary.tanim_yaz(KITAP, "Erken", "aslında kayıp kral")
    glossary.alan_kokeni_yaz(KITAP, "Erken", "kosul", 600)
    glossary.alan_kokeni_yaz(KITAP, "Erken", "tanim", 600)
    satir = next(r for r in _al(konum=100)["rows"] if r["source"] == "Erken")
    assert satir["kosul"] is None and satir["tanim"] is None
    assert set(satir["gizli_alanlar"]) == {"kosul", "tanim"}
    assert "Erken" not in _al(konum=100)["kosullar"]
    # 600'den sonraki okur görür.
    satir = next(r for r in _al(konum=650)["rows"] if r["source"] == "Erken")
    assert satir["kosul"] == "gizli kimliği: kral" and satir["tanim"] == "aslında kayıp kral"


def test_kokeni_bilinmeyen_aciklama_suzulmus_gorunumde_gizli():
    # Mevcut şema eski koşulun HANGİ bölümün bilgisiyle yazıldığını bilmiyor
    # (`sozluk_gecmis` yalnız ZAMAN tutar). Güvenli taraf: gizle, `spoiler=1` ile aç.
    _kur(100)
    glossary.terimi_yaz(KITAP, "Erken", "Erken", kosul="eski koşul")
    satir = next(r for r in _al(konum=100)["rows"] if r["source"] == "Erken")
    assert satir["kosul"] is None and "kosul" in satir["gizli_alanlar"]
    assert next(r for r in _al(spoiler=1)["rows"] if r["source"] == "Erken")["kosul"] == "eski koşul"


def test_ek_anlam_ve_uyarilar_gizli_kayda_sizmaz():
    _kur(100)
    glossary.set_term(KITAP, "Gelecekk", "Gelecekk")  # tek harf farkı: uyarı çifti
    conn = glossary._connect()
    conn.execute("UPDATE glossary SET first_chapter = 150 WHERE book_slug = ? AND source = 'Gelecekk'", (KITAP,))
    conn.commit()
    conn.close()
    glossary.anlamlari_yaz(KITAP, "Erken", [
        {"target": "Erk", "kosul": "gölgenin adı", "ad_mi": True, "ilk_bolum": 300},
    ])
    veri = _al(konum=100)
    assert all("Gelecek" not in a and "Gelecek" not in b for a, b in veri["warnings"])
    assert "Erken" not in veri["ekler"] or not veri["ekler"]["Erken"]["anlamlar"]


def test_yazma_yaniti_da_suzulur():
    _kur(100)
    with TestClient(server.app) as c:
        r = c.post(f"/api/book/{KITAP}/glossary", json={"source": "Yeni", "target": "Yeni"})
    assert r.status_code == 200 and "Gelecek" not in r.json()["terms"]
