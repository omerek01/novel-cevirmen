"""Hareket: kitaplar rafa yerleşir; "hareketi azalt" tercihinde hiç animasyon yok."""
from __future__ import annotations

from playwright.sync_api import expect

import tohum


def _kutuphane(sayfa):
    tohum.kitap()
    sayfa.goto(sayfa.taban + "/")
    expect(sayfa.locator("#shelves .spine[data-slug]").first).to_be_visible()


def test_kitaplar_rafa_yerlesir(sayfa):
    sayfa.emulate_media(reduced_motion="no-preference")
    _kutuphane(sayfa)
    ad = sayfa.locator("#shelves .spine").first.evaluate("e => getComputedStyle(e).animationName")
    assert ad == "rafa-yerles"


def test_hareketi_azalt_tercihinde_animasyon_yok(sayfa):
    sayfa.emulate_media(reduced_motion="reduce")
    _kutuphane(sayfa)
    for secici in ("#shelves .spine", "#resumeFiche"):
        ad = sayfa.locator(secici).first.evaluate("e => getComputedStyle(e).animationName")
        assert ad == "none", (secici, ad)
