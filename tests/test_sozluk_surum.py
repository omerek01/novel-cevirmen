"""Sözlük sürümü, çakışma (409) ve değişiklik geçmişi (belge: "Sürüm ve geçmiş").

Telefon ve PC aynı sözlüğü düzenliyor. Eski bir görüntü üzerinden yapılan
düzenleme öteki cihazın yeni kaydını sessizce eziyordu; artık istemci gördüğü
sürümü gönderir, uyuşmazsa sunucu yazmaz ve güncel kaydı döndürür.
"""
from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from core import db, glossary, library

KITAP = "surum-kitap"


def _client():
    from fastapi.testclient import TestClient

    import server

    return TestClient(server.app)


def _satir(source):
    return {r["source"]: r for r in glossary.get_glossary_rows(KITAP)}[source]


def test_yeni_kayit_surum1_kimlikli_ve_kitap_surumu_artar():
    assert glossary.kitap_surumu(KITAP) == 0
    glossary.set_term(KITAP, "Saint", "Aziz")
    s = _satir("Saint")
    assert s["surum"] == 1 and len(s["kimlik"]) == 16 and s["updated_at"]
    assert glossary.kitap_surumu(KITAP) == 1


def test_karsilik_degisince_surum_artar_ayni_deger_artirmaz():
    glossary.set_term(KITAP, "Saint", "Aziz")
    glossary.set_term(KITAP, "Saint", "Aziz")
    assert _satir("Saint")["surum"] == 1
    glossary.set_term(KITAP, "Saint", "Ermiş")
    assert _satir("Saint")["surum"] == 2
    glossary.set_kosul(KITAP, "Saint", "rütbe")
    assert _satir("Saint")["surum"] == 3
    assert glossary.kitap_surumu(KITAP) == 3


def test_koken_doldurmak_surumu_artirmaz():
    glossary.set_term(KITAP, "Saint", "Aziz")
    glossary.ornek_doldur(KITAP, "Saint", "The Saint rose.", 4)
    assert _satir("Saint")["surum"] == 1
    assert glossary.kitap_surumu(KITAP) == 1


def test_kosul_duzenlemesi_kokeni_degistirmez():
    glossary.merge_terms(KITAP, {"Great": "Ulu"}, "auto", 2)
    glossary.set_kosul(KITAP, "Great", "rütbe")
    assert _satir("Great")["origin"] == "auto"


def test_eski_tabanla_yazmak_cakisir_ve_yazmaz():
    glossary.set_term(KITAP, "Saint", "Aziz")
    glossary.terimi_yaz(KITAP, "Saint", "Ermiş", taban_surum=1)  # telefon
    with pytest.raises(glossary.SurumCakismasi) as hata:
        glossary.terimi_yaz(KITAP, "Saint", "Evliya", taban_surum=1)  # PC, eski görüntü
    assert hata.value.guncel["target"] == "Ermiş"
    assert _satir("Saint")["target"] == "Ermiş"


def test_taban0_kayit_varsa_taban_n_kayit_yoksa_cakisir():
    glossary.set_term(KITAP, "Saint", "Aziz")
    with pytest.raises(glossary.SurumCakismasi):
        glossary.terimi_yaz(KITAP, "Saint", "X", taban_surum=0)
    with pytest.raises(glossary.SurumCakismasi) as hata:
        glossary.terimi_yaz(KITAP, "Yok", "X", taban_surum=3)
    assert hata.value.guncel is None
    assert glossary.terimi_yaz(KITAP, "Mira", "Mira", taban_surum=0)["surum"] == 1


def test_silme_eski_tabanla_cakisir():
    glossary.set_term(KITAP, "Saint", "Aziz")
    glossary.set_term(KITAP, "Saint", "Ermiş")
    with pytest.raises(glossary.SurumCakismasi):
        glossary.delete_term(KITAP, "Saint", taban_surum=1)
    assert "Saint" in glossary.get_glossary(KITAP)
    assert glossary.delete_term(KITAP, "Saint", taban_surum=2)["target"] == "Ermiş"


def test_gecmis_butun_yollari_kaydeder_yeniden_eskiye():
    glossary.merge_terms(KITAP, {"Great": "Ulu"}, "auto", 2)
    glossary.set_term(KITAP, "Great", "Yüce")
    glossary.set_kosul(KITAP, "Great", "rütbe")
    silinen = glossary.delete_term(KITAP, "Great")
    glossary.ice_aktar(KITAP, [silinen], "dosya")
    g = glossary.gecmis(KITAP, "Great")
    assert [x["islem"] for x in g] == ["ekle", "sil", "guncelle", "guncelle", "ekle"]
    assert g[-1]["yol"] == "auto" and g[-1]["sonraki"]["target"] == "Ulu"
    assert g[3]["onceki"]["target"] == "Ulu" and g[3]["sonraki"]["target"] == "Yüce"
    assert g[2]["sonraki"]["kosul"] == "rütbe"
    assert g[0]["yol"] == "import"
    # Geri alınan kayıt aynı kimlikle döndüğü için geçmişin TAMAMI görünür.
    assert _satir("Great")["kimlik"] == silinen["kimlik"]


def test_birlestirme_gecmisi_ve_kimligi_tasir():
    glossary.set_term("kaynak-kitap", "Saint", "Aziz")
    glossary.set_term("kaynak-kitap", "Saint", "Ermiş")
    kimlik = {r["source"]: r for r in glossary.get_glossary_rows("kaynak-kitap")}["Saint"]["kimlik"]
    library.upsert_book("kaynak-kitap", "K", "https://x/1", "c1", 1)
    library.upsert_book(KITAP, "H", "https://y/1", "c1", 1)
    library.merge_books("kaynak-kitap", KITAP)
    assert _satir("Saint")["kimlik"] == kimlik
    assert [x["islem"] for x in glossary.gecmis(KITAP, "Saint")] == ["tasi", "guncelle", "ekle"]
    assert glossary.kitap_surumu("kaynak-kitap") == 0


def test_eski_satirlar_bir_kez_kimlik_ve_surum_alir():
    glossary.semayi_hazirla()
    conn = sqlite3.connect(db.db_path())
    conn.execute(
        "INSERT INTO glossary (book_slug, source, target, created_at) VALUES (?, ?, ?, ?)",
        (KITAP, "Eski", "Eski", 100.0),
    )
    conn.commit()
    conn.close()
    s = _satir("Eski")
    assert s["surum"] == 1 and s["kimlik"] and s["updated_at"] == 100.0


def test_uc_409_guncel_kaydi_doner():
    c = _client()
    r = c.post(f"/api/book/{KITAP}/glossary", json={"source": "Saint", "target": "Aziz"})
    assert r.json()["kayit"]["surum"] == 1
    r = c.post(f"/api/book/{KITAP}/glossary",
               json={"source": "Saint", "target": "Ermiş", "taban_surum": 1})
    assert r.status_code == 200 and r.json()["kayit"]["surum"] == 2
    r = c.post(f"/api/book/{KITAP}/glossary",
               json={"source": "Saint", "target": "Evliya", "taban_surum": 1})
    assert r.status_code == 409
    detay = r.json()["detail"]
    assert detay["error_class"] == "SurumCakismasi"
    assert detay["guncel"]["target"] == "Ermiş"
    r = c.delete(f"/api/book/{KITAP}/glossary", params={"source": "Saint", "taban_surum": 1})
    assert r.status_code == 409
    # Taban verilmeyen eski istemci davranışı değişmez.
    assert c.post(f"/api/book/{KITAP}/glossary", json={"source": "Saint", "target": "X"}).status_code == 200


def test_uc_karsilik_ve_kosul_tek_surum_artisi():
    c = _client()
    c.post(f"/api/book/{KITAP}/glossary", json={"source": "Great", "target": "Ulu"})
    r = c.post(f"/api/book/{KITAP}/glossary",
               json={"source": "Great", "target": "Yüce", "kosul": "rütbe", "taban_surum": 1})
    assert r.json()["kayit"]["surum"] == 2
    assert glossary.kitap_surumu(KITAP) == 2


def test_uc_gecmis():
    c = _client()
    c.post(f"/api/book/{KITAP}/glossary", json={"source": "Saint", "target": "Aziz"})
    c.post(f"/api/book/{KITAP}/glossary", json={"source": "Saint", "target": "Ermiş"})
    g = c.get(f"/api/book/{KITAP}/glossary/history", params={"source": "Saint"}).json()["gecmis"]
    assert [x["islem"] for x in g] == ["guncelle", "ekle"]


# Onaylı istisnalar: yalnız KÖKEN (cümle/bölüm) yazar, prompt'u değiştirmez; ya da
# yardımcının kendisidir / tembel göçtür.
_GECMISSIZ_YAZABILIR = {
    "_connect", "ornek_doldur", "set_kaynak_cumle", "_satir_ekle", "_satiri_guncelle",
    "_gecmise_yaz", "_kitap_surumunu_artir",
}


def test_tel_tuzagi_sozluge_yazan_her_fonksiyon_gecmise_yazar():
    """`glossary` tablosuna INSERT/UPDATE/DELETE yapan (ya da `_satir_ekle` /
    `_satiri_guncelle` çağıran) her fonksiyon geçmişe de yazmalı — yoksa bir yol
    sürümü ve geçmişi atlayarak sözlüğü değiştirir ve çakışma denetimi delinir."""
    yol = Path(__file__).resolve().parent.parent / "app" / "core" / "glossary.py"
    agac = ast.parse(yol.read_text(encoding="utf-8"))
    eksik = []
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.FunctionDef) or dugum.name in _GECMISSIZ_YAZABILIR:
            continue
        metin = ast.unparse(dugum)
        yaziyor = any(
            k in metin
            for k in ("INTO glossary", "UPDATE glossary",
                      "_satir_ekle(", "_satiri_guncelle(")
        ) or "DELETE FROM glossary" in metin
        if yaziyor and "_gecmise_yaz(" not in metin and "_satiri_guncelle(" not in metin \
                and "terimi_yaz(" not in metin:
            eksik.append(dugum.name)
    assert not eksik, f"geçmişe yazmadan sözlüğü değiştiren fonksiyonlar: {eksik}"
