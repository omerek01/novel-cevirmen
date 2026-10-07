"""Varlık grafiği (`core.varlik_grafigi`) — çevrimdışı.

Rün metinleri Shadow Slave'in mesaj BİÇİMİNİ taklit eden kısa yapay örneklerdir
(roman metni değil). Gerçek veride ölçülen davranış: sunucu kopyasında 189 tekil
sistem bağı, kalite kurallarında 19 bulgu.
"""
from __future__ import annotations

from core import glossary, library, varlik_grafigi as vg

KITAP = "shadow-slave"  # profil bu slug'a bağlı

RUNLER = """He looked at the runes.

Name: Sunless.

True Name: Lost from Light.

Rank: Dreamer.

Memories: [Silver Bell], [Azure Blade].

Attributes: [Fated].

He smiled.

Memory: [Azure Blade].

Memory Rank: Awakened.

Then the voice of the Spell came.

[You have slain an awakened monster, Rolling Stone.]

Shadow: [Stone Saint].

Shadow Rank: Awakened.

Shadow Class: Monster."""


def _sozluk():
    for k, v in {
        "Sunny": "Sunny", "Sunless": "Sunless", "Lost from Light": "Işıktan Mahrum",
        "Dreamer": "Rüyacı", "Silver Bell": "Gümüş Çan", "Azure Blade": "Gök Mavisi Bıçak",
        "Fated": "Yazgılı", "Awakened": "Uyanmış", "Monster": "Canavar", "Rolling Stone": "Yuvarlanan Taş",
        "Stone Saint": "Taş Aziz", "beast": "Mahluk", "Dormant": "Uykuda",
    }.items():
        glossary.set_term(KITAP, k, v)


def _bag_kumesi(**kw):
    return {(b["kaynak"], b["iliski"], b["hedef"]) for b in vg.baglar(KITAP, **kw)}


def test_run_bloklari_dogru_ozneye_baglanir():
    bulunan = {(o, i, n) for o, i, n, _k in vg.sistem_baglarini_bul(RUNLER, "Sunny", ("Sunless",))}
    assert {
        ("Sunny", "gercek_adi", "Lost from Light"), ("Sunny", "rutbesi", "Dreamer"),
        ("Sunny", "anisi", "Silver Bell"), ("Sunny", "anisi", "Azure Blade"),
        ("Sunny", "niteligi", "Fated"), ("Azure Blade", "rutbesi", "Awakened"),
        ("Sunny", "oldurdu", "Rolling Stone"), ("Rolling Stone", "rutbesi", "awakened"),
        ("Rolling Stone", "sinifi", "monster"), ("Sunny", "golgesi", "Stone Saint"),
        ("Stone Saint", "rutbesi", "Awakened"), ("Stone Saint", "sinifi", "Monster"),
    } <= bulunan
    assert ("Sunny", "rutbesi", "Awakened") not in bulunan


def test_duz_paragraf_run_blogunu_kapatir():
    # Düz paragraftan sonra gelen rün biçimli satır önceki bloğun öznesine
    # bağlanmamalı (başka bir şeyin rünü ya da diyalog olabilir).
    metin = "Name: Sunless.\n\nRank: Dreamer.\n\nHe thought for a while.\n\nRank: Awakened."
    bulunan = {(o, i, n) for o, i, n, _k in vg.sistem_baglarini_bul(metin, "Sunny", ("Sunless",))}
    assert bulunan == {("Sunny", "rutbesi", "Dreamer")}


def test_bolum_akisi_bag_yazar_ve_cozulemeyen_adi_atlar():
    _sozluk()
    assert vg.bolumden_sistem_baglari(KITAP, 16, RUNLER + "\n\nMemory: [Unknown Thing].") > 0
    baglar = _bag_kumesi()
    assert ("Sunny", "anisi", "Azure Blade") in baglar
    assert not any(b[2] == "Unknown Thing" for b in baglar)
    assert vg.bolumden_sistem_baglari("baska-kitap", 1, RUNLER) == 0  # profilsiz kitap


def test_ilk_bolum_yalniz_kuculur_ve_red_dirilmez():
    _sozluk()
    cozucu = vg.DugumCozucu(KITAP)
    a, b = cozucu.coz("Sunny"), cozucu.coz("Silver Bell")
    vg.bag_ekle(KITAP, a, "anisi", b, 50, "geç", "model", 0.6)
    vg.bag_ekle(KITAP, a, "anisi", b, 20, "erken", "model", 0.7)
    vg.bag_ekle(KITAP, a, "anisi", b, 90, "daha geç", "sistem", 1.0)
    bag = vg.baglar(KITAP)[0]
    assert bag["ilk_bolum"] == 20 and bag["kanit"] == "erken"
    assert bag["origin"] == "sistem" and bag["durum"] == "onaylandi"  # güçlü köken kazanır
    vg.bag_durumu(KITAP, a, "anisi", b, "reddedildi")
    assert vg.bag_ekle(KITAP, a, "anisi", b, 5, "x", "model") is False
    assert vg.baglar(KITAP) == []  # reddedilen varsayılan listede yok


def test_spoiler_suzgeci():
    _sozluk()
    vg.bolumden_sistem_baglari(KITAP, 16, RUNLER)
    assert _bag_kumesi(en_cok_bolum=10) == set()
    assert ("Sunny", "golgesi", "Stone Saint") in _bag_kumesi(en_cok_bolum=16)


def test_uc_spoiler_varsayilan_gizli():
    from fastapi.testclient import TestClient

    import server

    _sozluk()
    vg.bolumden_sistem_baglari(KITAP, 16, RUNLER)
    library.upsert_book(KITAP, "Shadow Slave", "https://x/ch-3", "B3", 3)
    c = TestClient(server.app)
    assert c.get(f"/api/book/{KITAP}/graph").json()["edges"] == []  # konum 3 < 16
    assert c.get(f"/api/book/{KITAP}/graph", params={"bolum": 16}).json()["edges"]
    tum = c.get(f"/api/book/{KITAP}/graph", params={"spoiler": "true"}).json()
    assert {e["relation"] for e in tum["edges"]} >= {"anisi", "golgesi", "gercek_adi"}


def test_sozluk_kaydi_silinince_baglari_gider():
    _sozluk()
    vg.bolumden_sistem_baglari(KITAP, 16, RUNLER)
    glossary.delete_term(KITAP, "Stone Saint")
    assert not any("Stone Saint" in (b[0], b[2]) for b in _bag_kumesi())


def test_kitap_birlestirmede_baglar_tasinir():
    _sozluk()
    vg.bolumden_sistem_baglari(KITAP, 16, RUNLER)
    glossary.set_term("hedef-kitap", "Sunny", "Sunny")  # hedefte zaten var, kimliği farklı
    conn = vg._connect()
    try:
        glossary.kitaba_tasi(conn, KITAP, "hedef-kitap")
        conn.commit()
    finally:
        conn.close()
    hedef = {(b["kaynak"], b["iliski"], b["hedef"]) for b in vg.baglar("hedef-kitap")}
    assert ("Sunny", "anisi", "Silver Bell") in hedef
    assert vg.baglar(KITAP) == []


def test_sozcuk_karismasi_baska_sinifin_sozcugunu_yakalar():
    _sozluk()
    for k, v in {"Winter Beast": "Kış Canavarı", "Soul Beast": "Ruh Mahluku",
                 "Monster": "Canavar", "Awakened monsters": "Uyanmış canavarlar"}.items():
        glossary.set_term(KITAP, k, v)
    duzen = {"Monster": ["Canavar"], "beast": ["Mahluk"], "Awakened": ["Uyanmış"]}
    sonuc = vg.sozcuk_karismalari(KITAP, duzen)
    assert set(sonuc) == {"Winter Beast"}


def test_sozcuk_karismasi_kok_dusmani_yakalamaz():
    glossary.set_term(KITAP, "Vanquished Foes", "Alt Edilen Düşmanlar")
    assert vg.sozcuk_karismalari(KITAP, {"Fallen": ["Düşmüş"]}) == {}


def test_ayni_kisinin_adlari_karisik_politika():
    _sozluk()
    vg.bolumden_sistem_baglari(KITAP, 16, RUNLER)
    cozucu = vg.DugumCozucu(KITAP)
    vg.bag_ekle(KITAP, cozucu.coz("Sunny"), "takma_adi", cozucu.coz("Sunless"), 1, None, "manual")
    sonuc = vg.ad_tutarsizliklari(KITAP)
    assert set(sonuc) == {"Lost from Light"}
    assert "Sunless (İngilizce)" in sonuc["Lost from Light"]["aciklama"]


def test_inceleme_listesi_grafik_nedenlerini_gosterir():
    _sozluk()
    vg.bolumden_sistem_baglari(KITAP, 16, RUNLER)
    tur = {x["source"]: [n["tur"] for n in x["nedenler"]] for x in glossary.inceleme_listesi(KITAP)}
    assert vg.AD_TUTARLILIGI in tur["Lost from Light"]


def test_simetrik_iliski_tek_bagdir():
    _sozluk()
    glossary.set_term(KITAP, "Kai", "Kai")
    cozucu = vg.DugumCozucu(KITAP)
    s, k = cozucu.coz("Sunny"), cozucu.coz("Kai")
    assert vg.bag_ekle(KITAP, s, "yoldasi", k, 120, "a", "model", 0.9) is True
    assert vg.bag_ekle(KITAP, k, "yoldasi", s, 110, "b", "model", 0.9) is False
    baglar = [b for b in vg.baglar(KITAP) if b["iliski"] == "yoldasi"]
    assert len(baglar) == 1 and baglar[0]["ilk_bolum"] == 110


def test_takma_ad_dugumundeki_baglar_asil_kisiye_tasinir():
    _sozluk()
    for k in ("Nephis", "Neph", "Dawn Shard", "Changing Star", "Tessai"):
        glossary.set_term(KITAP, k, k)
    k = vg.DugumCozucu(KITAP).coz
    vg.bag_ekle(KITAP, k("Nephis"), "takma_adi", k("Neph"), 209, None, "model", durum="onaylandi")
    vg.bag_ekle(KITAP, k("Nephis"), "gercek_adi", k("Changing Star"), 28, None, "manual")
    vg.bag_ekle(KITAP, k("Neph"), "anisi", k("Dawn Shard"), 296, "x", "model", 0.9)
    vg.bag_ekle(KITAP, k("Changing Star"), "oldurdu", k("Tessai"), 313, "y", "model", 0.9)
    vg.bag_ekle(KITAP, k("Nephis"), "anisi", k("Dawn Shard"), 400, "z", "model", 0.9)
    assert vg.takma_adlari_birlestir(KITAP) == 2
    baglar = {(b["kaynak"], b["iliski"], b["hedef"]): b for b in vg.baglar(KITAP)}
    assert baglar[("Nephis", "anisi", "Dawn Shard")]["ilk_bolum"] == 296  # erken olan kalır
    assert ("Nephis", "oldurdu", "Tessai") in baglar
    assert ("Neph", "anisi", "Dawn Shard") not in baglar
    assert ("Nephis", "takma_adi", "Neph") in baglar  # kimlik bağı yerinde


def test_bilinmeyen_iliski_reddedilir():
    import pytest

    with pytest.raises(ValueError):
        vg.bag_ekle(KITAP, "a", "sevgilisi", "b", 1, None, "model")
