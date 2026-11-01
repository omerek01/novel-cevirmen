"""Bölüm künyesi: çeviri süresi ve modeller (2026-11-01, kullanıcı isteği).

Künye açılınca toplam süre, aşama ve model başına süre, başarısız denemeler ve
kapalı aşamalar okunur Türkçe yazılır; motor rozeti, sözlük sürümü ve "neden bu
model?" gibi anlaşılmayan satırlar YAZILMAZ.
"""
from __future__ import annotations

from playwright.sync_api import expect

import tohum
from core import cache

SURE = {
    "toplam_sn": 383.4, "indirme_sn": 2.2, "bekleme_sn": 0.0, "oteki_sn": 9.1,
    "asamalar": [
        {"ad": "ceviri", "etiket": "Çeviri", "sn": 161.0},
        {"ad": "kalite", "etiket": "Kalite denetimi", "sn": 171.0},
        {"ad": "cilalama", "etiket": "Türkçe cilalama", "sn": 40.1},
    ],
    "modeller": [
        {"model": "vertex/gemini-4-argon", "etiket": "4 Argon · ücretli", "sn": 338.0,
         "istek": 7, "basarisiz": 2, "basarisiz_sn": 174.0, "nedenler": {"zaman aşımı": 2}},
        {"model": "gemini-3.6-flash", "etiket": "3.6 Flash · ücretsiz", "sn": 34.1,
         "istek": 1, "basarisiz": 0, "basarisiz_sn": 0.0, "nedenler": {}},
    ],
    "kapali": ["Bölüm özeti"],
}


def _kunye(sayfa):
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#chapterList .chapter-row").first.click()
    expect(sayfa.locator("#readerView")).to_be_visible()
    return sayfa.locator("#readerBody article.chapter").first.locator(".kunye")


def test_kunye_sureyi_asamalari_ve_modelleri_yazar(sayfa):
    for url in tohum.kitap():  # liste sırası testi ilgilendirmesin: iki bölüm de aynı
        satir = cache.get_chapter(url)
        satir.update({"model": "gemini-3.6-flash + vertex/gemini-4-argon",
                      "sure_dokumu": SURE, "ceviri_kalitesi": {
                          "surum": 2, "durum": "denetlendi", "denetlenen": 54,
                          "onarilan": [0, 30], "supheli": []}})
        cache.save_chapter(url, satir)
    kunye = _kunye(sayfa)
    ozet = kunye.locator("summary")
    expect(ozet).to_contain_text("6 dk 23 sn")
    expect(ozet).to_contain_text("4 Argon (ücretli)")
    ozet.click()
    govde = kunye.locator(".kunye-sure")
    expect(govde).to_contain_text("Bu bölümün çevirisi 6 dk 23 sn sürdü")
    expect(govde).to_contain_text("Kalite denetimi")
    expect(govde).to_contain_text("2 dk 51 sn")
    expect(govde).to_contain_text("Türkçe cilalama")
    expect(govde).to_contain_text("2 deneme başarısız (zaman aşımı ×2), 2 dk 54 sn boşa gitti")
    expect(govde).to_contain_text("54 paragrafı kaynakla karşılaştırdı, 2 paragrafı düzeltti")
    expect(govde).to_contain_text("Kapalıydı, süre harcamadı: Bölüm özeti")
    # Kaldırılan teknik satırlar
    expect(kunye).not_to_contain_text("GEMINI")
    expect(kunye).not_to_contain_text("sözlük s.")
    expect(kunye).not_to_contain_text("Neden bu model")


def test_sure_kaydi_olmayan_eski_bolum_yalniz_modeli_soyler(sayfa):
    tohum.kitap()  # model: gemini-3.6-flash, süre dökümü yok
    kunye = _kunye(sayfa)
    kunye.locator("summary").click()
    govde = kunye.locator(".kunye-sure")
    expect(govde).to_contain_text("Çeviren model: 3.6 Flash")
    expect(govde).to_contain_text("süre bilgisi yok")
