"""Okuma Salonu ayarlar paneli: dört bölüm etiketi ve tema örnekleri."""
from __future__ import annotations

from playwright.sync_api import expect

import tohum


def test_ayarlar_bolumleri_ve_tema_ornekleri(sayfa):
    tohum.kitap()
    sayfa.goto(sayfa.taban + "/")
    expect(sayfa.locator("#shelves .spine[data-slug]").first).to_be_visible()
    sayfa.locator('.navtab[data-tab="settings"]').click()
    panel = sayfa.locator("#settingsPanel")
    expect(panel).to_be_visible()
    expect(panel.locator(".ayar-bolumu")).to_have_text(["Sayfa", "Çeviri modeli", "Bu bölüm", "Bakım"])
    expect(panel.locator("[data-theme-opt] i.theme-swatch")).to_have_count(3)
