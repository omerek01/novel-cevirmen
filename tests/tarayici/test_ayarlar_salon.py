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
        ["Sayfa", "Çeviri modeli", "Vertex kredisi", "Çeviri aşamaları", "Bakım"])
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
