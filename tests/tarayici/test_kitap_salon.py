"""Okuma Salonu kitap ekranı: künye (kapak/ad/tür), iki satırlı devam, içindekiler."""
from __future__ import annotations

from playwright.sync_api import expect

import tohum


def _kitap_ac(sayfa):
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    expect(sayfa.locator("#chapterList .chapter-row").first).to_be_visible()


def test_kitap_kunyesi_ve_devam(sayfa):
    tohum.kitap(bolum_sayisi=3, konum=2)
    _kitap_ac(sayfa)
    expect(sayfa.locator("#bookHeroTitle")).to_have_text("Gumus Kule")
    expect(sayfa.locator("#bookHeroKind")).to_contain_text("Okunuyor")
    expect(sayfa.locator("#bookHeroInfo")).to_have_text("3 bölüm çevrildi")
    expect(sayfa.locator("#bookHeroArt.cloth .spine-mono")).to_be_visible()
    expect(sayfa.locator("#resumeSub")).to_contain_text("Bölüm 2")


def test_kaldigin_bolum_isaretli(sayfa):
    tohum.kitap(bolum_sayisi=3, konum=2)
    _kitap_ac(sayfa)
    guncel = sayfa.locator('#chapterList .chapter-row[aria-current="true"]')
    expect(guncel).to_have_count(1)
    expect(guncel.locator(".chapter-here")).to_have_text("burada")
    expect(guncel.locator(".chapter-no")).to_have_text("2")
