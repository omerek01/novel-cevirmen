"""Okuma Salonu kütüphanesi: büyük başlık, ödünç kartı, sayılı sekmeler, bez cilt.

Onaylı tasarım: docs/superpowers/specs/2026-10-13-okuma-salonu-design.md.
"""
from __future__ import annotations

import re

from playwright.sync_api import expect

import tohum


def _ac(sayfa):
    sayfa.goto(sayfa.taban + "/")
    expect(sayfa.locator("#shelves .spine[data-slug]").first).to_be_visible()


def test_buyuk_baslik_ve_alt_satir(sayfa):
    tohum.kitap(bolum_sayisi=2, konum=1)
    _ac(sayfa)
    expect(sayfa.locator(".lib-title")).to_have_text("Kütüphane")
    expect(sayfa.locator("#libSubtitle")).to_contain_text("1 kitap")


def test_odunc_karti_damga_ve_bolum(sayfa):
    tohum.kitap(bolum_sayisi=2, konum=1)
    _ac(sayfa)
    fis = sayfa.locator("#resumeFiche")
    expect(fis.locator(".fiche-label")).to_have_text("Ödünç kartı")
    expect(fis.locator(".fiche-chapter")).to_contain_text("Bölüm")
    damga = fis.locator(".fiche-stamp")
    expect(damga).to_have_count(1)
    assert re.match(r"^\d{1,2} (OCA|ŞUB|MAR|NİS|MAY|HAZ|TEM|AĞU|EYL|EKİ|KAS|ARA)", damga.inner_text())


def test_sekme_sayilari_ve_kapaksiz_bez_cilt(sayfa):
    tohum.kitap(bolum_sayisi=2, konum=1)
    _ac(sayfa)
    expect(sayfa.locator('#shelfFilters .chip[data-filter="all"] sup')).to_have_text("1")
    expect(sayfa.locator('#shelfFilters .chip[data-filter="bitti"] sup')).to_have_text("0")
    # Tohum kitabının kapağı yok: bez cilt + yaldız baş harf.
    expect(sayfa.locator(".spine .spine-art.cloth .spine-mono").first).to_be_visible()
    expect(sayfa.locator(".spine-add .spine-addlabel")).to_have_text("Rafa kitap ekle")
