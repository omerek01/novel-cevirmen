"""Okuyucu alt çubuğu: kapalı hap ↔ açık çubuk, aşağı kaydırınca kapanır, Sonraki gider.

Kullanıcı isteği (2026-10-13): "alt bar açılıp kapanabilir olsun, boyutu da küçük olsun".
"""
from __future__ import annotations

from playwright.sync_api import expect

import tohum


def _okuyucu(sayfa, bolum_sayisi=2):
    tohum.kitap(bolum_sayisi=bolum_sayisi)
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#chapterList .chapter-row").last.click()  # en altta 1. bölüm
    expect(sayfa.locator("#readerBody article.chapter").first.locator("p[data-idx]")).to_have_count(len(tohum.TR))


def test_hap_acar_kapat_kapatir(sayfa):
    _okuyucu(sayfa)
    alt = sayfa.locator("#okuyucuAlt")
    expect(alt).to_have_attribute("data-hal", "kapali")
    expect(sayfa.locator("#altHap")).to_be_visible()
    expect(sayfa.locator("#altSonraki")).to_be_hidden()
    sayfa.locator("#altHap").click()
    expect(alt).to_have_attribute("data-hal", "acik")
    expect(sayfa.locator("#altSonraki")).to_be_visible()
    sayfa.locator("#altKapat").click()
    expect(alt).to_have_attribute("data-hal", "kapali")


def test_asagi_kaydirinca_kapanir(sayfa):
    _okuyucu(sayfa)
    sayfa.locator("#altHap").click()
    expect(sayfa.locator("#okuyucuAlt")).to_have_attribute("data-hal", "acik")
    sayfa.mouse.wheel(0, 600)
    expect(sayfa.locator("#okuyucuAlt")).to_have_attribute("data-hal", "kapali")


def test_sonraki_bolume_gider(sayfa):
    _okuyucu(sayfa)
    sayfa.locator("#altHap").click()
    sayfa.locator("#altSonraki").click()
    expect(sayfa.locator("#readerChapter")).to_have_text("Chapter 2")
    expect(sayfa.locator("#okuyucuAlt")).to_have_attribute("data-hal", "kapali")


def test_bolum_basligi_aramadan_sonra_da_kalir(sayfa):
    # Paragraf çizimi makaleyi temizler; başlık korunmazsa ilk aramada kaybolur.
    _okuyucu(sayfa)
    ilk = sayfa.locator("#readerBody article.chapter").first
    expect(ilk.locator(".chapter-title")).to_have_count(1)
    sayfa.locator("#findBtn").click()
    sayfa.locator("#findInput").fill("a")
    expect(ilk.locator(".chapter-title")).to_have_count(1)
