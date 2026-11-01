"""Okuyucu: otomatik kaydırma ve ayarlanabilir hız (2026-11-01, kullanıcı isteği).

Yalnız okur başlatır; kumanda alt çubuğun yerini alır; duraklatınca durur; hız
seviyesi saklanır; kapatınca alt çubuk geri gelir.
"""
from __future__ import annotations

from playwright.sync_api import expect

import tohum


def _okuyucu(sayfa):
    sayfa.set_viewport_size({"width": 390, "height": 420})  # kısa tohum metni kaydırılabilsin
    tohum.kitap(bolum_sayisi=3)
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#chapterList .chapter-row").last.click()
    expect(sayfa.locator("#readerBody article.chapter").first.locator("p[data-idx]")).to_have_count(len(tohum.TR))


def _baslat(sayfa):
    sayfa.locator("#altHap").click()
    sayfa.locator("#altKaydir").click()
    expect(sayfa.locator("#otoKaydir")).to_be_visible()


def test_kendiliginden_baslamaz_kaydir_ile_akar(sayfa):
    _okuyucu(sayfa)
    expect(sayfa.locator("#otoKaydir")).to_be_hidden()
    y0 = sayfa.evaluate("scrollY")
    sayfa.wait_for_timeout(400)
    assert sayfa.evaluate("scrollY") == y0
    _baslat(sayfa)
    expect(sayfa.locator("#okuyucuAlt")).to_be_hidden()  # kumanda çubuğun yerini alır
    sayfa.wait_for_function(f"scrollY > {y0 + 5}")


def test_duraklat_durdurur_surdur_devam_eder(sayfa):
    _okuyucu(sayfa)
    _baslat(sayfa)
    dugme = sayfa.locator("#otoKaydirDurdur")
    dugme.click()
    expect(dugme).to_have_attribute("aria-label", "Kaydırmayı sürdür")
    y = sayfa.evaluate("scrollY")
    sayfa.wait_for_timeout(500)
    assert sayfa.evaluate("scrollY") == y
    dugme.click()
    sayfa.wait_for_function(f"scrollY > {y + 3}")


def test_hiz_ayarlanir_ve_saklanir(sayfa):
    _okuyucu(sayfa)
    _baslat(sayfa)
    deger = sayfa.locator("#otoKaydirDeger")
    expect(deger).to_have_text("4")
    sayfa.locator("#otoKaydirHizli").click()
    sayfa.locator("#otoKaydirHizli").click()
    expect(deger).to_have_text("6")
    expect(sayfa.locator("#otoKaydirCentik i.dolu")).to_have_count(6)
    assert sayfa.evaluate("JSON.parse(localStorage.getItem('novellink:settings')).kaydirmaSeviyesi") == 6
    for _ in range(20):
        if sayfa.locator("#otoKaydirYavas").is_disabled():
            break
        sayfa.locator("#otoKaydirYavas").click()
    expect(deger).to_have_text("1")
    expect(sayfa.locator("#otoKaydirYavas")).to_be_disabled()


def test_kapat_alt_cubugu_geri_getirir(sayfa):
    _okuyucu(sayfa)
    _baslat(sayfa)
    sayfa.locator("#otoKaydirKapat").click()
    expect(sayfa.locator("#otoKaydir")).to_be_hidden()
    expect(sayfa.locator("#altHap")).to_be_visible()
    y = sayfa.evaluate("scrollY")
    sayfa.wait_for_timeout(400)
    assert sayfa.evaluate("scrollY") == y
