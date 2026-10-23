"""Okuma Salonu ayarlar paneli: bölüm etiketleri, tema örnekleri ve Vertex kredisi."""
from __future__ import annotations

from playwright.sync_api import expect

import tohum


def _ayarlar(sayfa):
    tohum.kitap()
    sayfa.goto(sayfa.taban + "/")
    expect(sayfa.locator("#shelves .spine[data-slug]").first).to_be_visible()
    sayfa.locator('.navtab[data-tab="settings"]').click()
    panel = sayfa.locator("#settingsPanel")
    expect(panel).to_be_visible()
    return panel


def test_ayarlar_bolumleri_ve_tema_ornekleri(sayfa):
    panel = _ayarlar(sayfa)
    expect(panel.locator(".ayar-bolumu")).to_have_text(
        ["Sayfa", "Çeviri modeli", "Vertex kredisi", "Çeviri aşamaları",
         "Karakter defteri", "Bakım"])
    expect(panel.locator("[data-theme-opt] i.theme-swatch")).to_have_count(3)


def test_kredi_bilgisi_girilir_ve_gosterge_guncellenir(sayfa):
    panel = _ayarlar(sayfa)
    kredi = panel.locator("#kredi")
    expect(kredi).to_have_attribute("aria-busy", "false")
    expect(kredi.locator("#krediToplam")).to_have_text("/ 300 $")
    expect(kredi.locator("#krediBitis")).to_have_text("Bitiş tarihi girilmedi.")
    expect(kredi.locator(".kredi-zaman")).to_be_hidden()

    kredi.locator("#krediDuzenle").click()
    expect(kredi.locator("#krediDuzenle")).to_have_attribute("aria-expanded", "true")
    expect(kredi.locator("#krediTutarGir")).to_have_value("300")
    kredi.locator("#krediBitisGir").fill("2099-12-10")
    kredi.locator("#krediOkumaGir").fill("165")
    kredi.locator("#krediForm [type=submit]").click()

    expect(kredi.locator("#krediForm")).to_be_hidden()
    expect(kredi.locator("#krediTutar")).to_have_text("≈165 $")
    expect(kredi.locator("#krediAlt")).to_have_text("%55 kullanıldı · 135 $ kaldı")
    expect(kredi.locator("#krediSerit")).to_have_attribute("aria-valuenow", "55")
    expect(kredi.locator("#krediBitis")).to_contain_text("Bitiş 10 Aralık 2099")
    expect(kredi.locator("#krediKaynak")).to_contain_text("Konsol okuması 165 $")

    kredi.locator("#krediDuzenle").click()
    expect(kredi.locator("#krediOkumaGir")).to_have_attribute("placeholder", "Son okuma 165 $")
    expect(kredi.locator("#krediOkumaSil")).to_be_visible()
    kredi.locator("#krediOkumaSil").click()
    expect(kredi.locator("#krediTutar")).to_have_text("≈0,00 $")
    expect(kredi.locator("#krediOkumaSil")).to_be_hidden()


def test_karakter_defteri_acilip_kapanir(sayfa):
    """Defter düğmesi SUNUCUYA yazar ve panel yeniden açıldığında kayıtlı durumu gösterir.

    Gerekçe para: defter çeviriden ayrı bir model çağrısı yapıyor ve ölçülen faturada
    en pahalı kalem. Önceden kapatmak sunucuya girip servisi yeniden başlatmak demekti.
    """
    panel = _ayarlar(sayfa)
    kutu = panel.locator("#defterAnahtari")
    satir = kutu.locator(".asama-satir")
    expect(satir).to_have_count(1)
    expect(satir.locator(".asama-ad")).to_have_text("Karakter defteri")
    # Masrafın büyüklüğü satırda YAZILI olmalı: düğmenin ne işe yaradığı bu.
    expect(satir.locator(".asama-aciklama")).to_contain_text("EN PAHALI")
    # Testlerde `KARAKTER_DEFTERI` kapalı ve düğmeye dokunulmadı -> kaynak ortam.
    expect(satir.locator(".asama-sure")).to_contain_text("KARAKTER_DEFTERI")
    expect(kutu.locator('[data-defter="0"]')).to_have_attribute("aria-pressed", "true")

    kutu.locator('[data-defter="1"]').click()
    expect(kutu.locator('[data-defter="1"]')).to_have_attribute("aria-pressed", "true")
    # Yazıldıktan sonra kaynak DÜĞME olur; "neden açık" sorusunun cevabı değişti.
    expect(satir.locator(".asama-sure")).to_contain_text("Bu düğmeyle ayarlandı")

    # Panel kapanıp açıldığında durum SUNUCUDAN gelir (yerel bir bayrak değil).
    # Modal açıkken alt sekme tıklanamaz (diyalog işaretçiyi yakalar); Escape kapatır.
    sayfa.keyboard.press("Escape")
    expect(panel).to_be_hidden()
    sayfa.locator('.navtab[data-tab="settings"]').click()
    expect(panel.locator('#defterAnahtari [data-defter="1"]')).to_have_attribute(
        "aria-pressed", "true")
