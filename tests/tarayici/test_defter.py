"""Defter ekranı: kişi listesi, arama, sekmeler, karakter kartı, elle kayıt, sen/siz kararı, spoiler."""
from __future__ import annotations

import time

from playwright.sync_api import expect

import tohum
from core import defter_kayit, glossary, karakter_defteri, varlik_grafigi

SLUG = "shadow-slave"  # rün profili bu slug'a bağlı


def _iddia(conn, bolum, tur, ozne, kimlik, nesne=None, nesne_kimlik=None, deger="{}"):
    conn.execute(
        "INSERT INTO defter_iddia (book_slug, bolum, tur, ozne_ad, ozne_kimlik, nesne_ad, nesne_kimlik, deger, "
        "gecerli, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
        (SLUG, bolum, tur, ozne, kimlik, nesne, nesne_kimlik, deger, time.time()),
    )


def _kur(konum=1):
    tohum.kitap(SLUG, "Shadow Slave", bolum_sayisi=3, konum=konum)
    for kaynak, hedef in (("Sunny", "Sunny"), ("Nephis", "Nephis"), ("Changing Star", "Değişen Yıldız")):
        glossary.set_term(SLUG, kaynak, hedef)
        glossary.tanim_yaz(SLUG, kaynak, None, "kisi")
    kim = {r["source"]: r["kimlik"] for r in glossary.get_glossary_rows(SLUG)}
    conn = karakter_defteri._connect()
    for b in (1, 2, 3):
        _iddia(conn, b, "varlik", "Sunny", kim["Sunny"], deger='{"t": "kisi"}')
        _iddia(conn, b, "varlik", "Nephis", kim["Nephis"], deger='{"t": "kisi"}')
        _iddia(conn, b, "hitap", "Nephis", kim["Nephis"], "Sunny", kim["Sunny"], '{"f": "sen"}')
    _iddia(conn, 1, "hitap", "Nephis", kim["Nephis"], "Sunny", kim["Sunny"], '{"f": "sen"}')
    conn.commit()
    conn.close()
    varlik_grafigi.bag_ekle(SLUG, kim["Nephis"], "takma_adi", kim["Changing Star"], 1, None, "model", 1.0,
                            durum="onaylandi")
    varlik_grafigi.bag_ekle(SLUG, kim["Sunny"], "yoldasi", kim["Nephis"], 1, None, "model", 1.0, durum="onaylandi")
    defter_kayit.elle_yaz(SLUG, {"tur": "ani", "sahip": "Sunny", "ad": "Azure Blade", "ilk_bolum": 1,
                                 "alanlar": {"tur": "Weapon", "rutbe": "Awakened"}})
    defter_kayit.elle_yaz(SLUG, {"tur": "ani", "sahip": "Sunny", "ad": "Dark Wing", "ilk_bolum": 3})
    defter_kayit.elle_yaz(SLUG, {"tur": "alan", "sahip": "Sunny", "ad": "rutbesi", "deger": "Dreamer",
                                 "ilk_bolum": 1})
    return kim


def _defter(sayfa):
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#openDefterBtn").click()
    expect(sayfa.locator("#defterView")).to_be_visible()


def test_liste_takma_adla_arar_ve_sekme_degistirir(sayfa):
    _kur()
    _defter(sayfa)
    expect(sayfa.locator("#defterSinirMetin")).to_have_text("Bölüm 1’e kadar")
    satirlar = sayfa.locator("#defterListe .defter-satir")
    expect(satirlar).to_have_count(2)
    sayfa.locator("#defterAra").fill("değişen")
    expect(satirlar).to_have_count(1)
    expect(satirlar.first).to_contain_text("Nephis")
    sayfa.locator("#defterAra").fill("")
    sayfa.locator('[data-defter-sekme="anilar"]').click()
    expect(satirlar).to_have_count(1)  # Dark Wing 3. bölümde: konumdan sonra gizli
    expect(satirlar.first).to_contain_text("Azure Blade")
    expect(satirlar.first).to_contain_text("Silah")


def test_tum_kitap_secilince_ilerisi_gorunur(sayfa):
    _kur()
    _defter(sayfa)
    sayfa.locator('[data-defter-sekme="anilar"]').click()
    sayfa.locator("#defterSinirBtn").click()
    expect(sayfa.locator("#defterSinirMetin")).to_have_text("Tüm kitap")
    expect(sayfa.locator("#defterListe .defter-satir")).to_have_count(2)


def test_kart_run_listesi_anilar_ve_hitap_karari(sayfa):
    _kur()
    _defter(sayfa)
    sayfa.locator("#defterListe .defter-satir", has_text="Sunny").click()
    kart = sayfa.locator("#defterKart")
    expect(kart).to_be_visible()
    expect(kart.locator(".defter-run")).to_contain_text("Dreamer")
    expect(kart.locator(".defter-ani")).to_have_count(1)
    expect(kart.locator(".defter-baglar")).to_contain_text("Nephis")
    hitap = kart.locator(".defter-hitaplar li", has_text="Nephis → Sunny")
    hitap.locator(".seg", has_text="siz").click()
    expect(kart.locator(".defter-hitaplar li", has_text="Nephis → Sunny")).to_contain_text("Senin kararın: “siz”")


def test_karttan_elle_ani_eklenir_ve_kaldirilir(sayfa):
    _kur()
    _defter(sayfa)
    sayfa.locator("#defterListe .defter-satir", has_text="Sunny").click()
    kart = sayfa.locator("#defterKart")
    kart.locator(".defter-bolum-ust", has_text="Anılar").locator(".pill").click()
    form = sayfa.locator("#defterForm")
    expect(form).to_be_visible()
    form.locator('[name="ad"]').fill("Endless Spring")
    form.locator('[name="tur"]').fill("Tool")
    form.locator("#defterFormKaydet").click()
    expect(form).to_be_hidden()
    expect(kart.locator(".defter-ani", has_text="Endless Spring")).to_contain_text("Araç")
    kart.locator(".defter-ani", has_text="Endless Spring").click()
    expect(form).to_be_visible()
    form.locator("#defterFormKaldir").click()
    expect(form).to_be_hidden()
    expect(kart.locator(".defter-ani", has_text="Endless Spring")).to_have_count(0)
    assert sayfa.js_hatalari == []
