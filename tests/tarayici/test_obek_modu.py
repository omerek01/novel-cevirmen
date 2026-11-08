"""Öbek modu (hızlı okuma planı Adım C, 2026-11-08): alt çubuktan aç / kapa, öbekli çizim,
arama vurgusu ve uç hatası. Uç taklit edilir: testler gerçek (ücretli) model çağırmaz."""
import json

from playwright.sync_api import expect

import tohum
from core import obekler


def _uc(sayfa, durum=200):
    govde = {"sinirlar": [obekler.kural_obekleri(p) for p in tohum.TR], "kaynak": "model"}
    sayfa.route("**/api/chapter/obekler**", lambda r: r.fulfill(
        status=durum, content_type="application/json",
        body=json.dumps(govde if durum == 200 else {"detail": "x"})))


def _okuyucu(sayfa):
    tohum.kitap(bolum_sayisi=1)
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#chapterList .chapter-row").first.click()
    expect(sayfa.locator("#readerBody article.chapter p[data-idx]")).to_have_count(len(tohum.TR))


def _ac_kapa(sayfa):
    sayfa.locator("#altHap").click()
    sayfa.locator("#altObek").click()


def test_alt_cubuktan_ac_kapa_oblekli_cizim_ve_kalicilik(sayfa):
    _uc(sayfa)
    _okuyucu(sayfa)
    metin = sayfa.locator("#readerBody article.chapter p[data-idx]").first.inner_text()
    expect(sayfa.locator("span.obek")).to_have_count(0)
    _ac_kapa(sayfa)
    expect(sayfa.locator("#altObek")).to_have_attribute("aria-pressed", "true")
    expect(sayfa.locator("#status")).to_contain_text("Öbek modu açık")
    ilk = sayfa.locator("#readerBody article.chapter p[data-idx]").first
    expect(ilk.locator("span.obek")).to_have_count(len(obekler.kural_obekleri(tohum.TR[0])))
    assert ilk.inner_text() == metin  # metin aynen korunur
    assert sayfa.evaluate("JSON.parse(localStorage.getItem('novellink:settings')).obekModu") is True

    sayfa.reload()  # yeniden açılışta mod açık kalır
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#chapterList .chapter-row").first.click()
    expect(sayfa.locator("#altObek")).to_have_attribute("aria-pressed", "true")
    expect(sayfa.locator("span.obek").first).to_be_visible()

    _ac_kapa(sayfa)
    expect(sayfa.locator("#altObek")).to_have_attribute("aria-pressed", "false")
    expect(sayfa.locator("span.obek")).to_have_count(0)


def test_obek_sinirini_asan_arama_eslesmesi_tek_sayilir(sayfa):
    _uc(sayfa)
    _okuyucu(sayfa)
    _ac_kapa(sayfa)
    expect(sayfa.locator("span.obek").first).to_be_visible()
    sayfa.locator("#findBtn, [aria-label='Bölümde ara']").first.click()
    sayfa.locator("#findInput").fill("yaktı ve")  # "Kaan fenerini yaktı" | "ve dar geçidin"
    expect(sayfa.locator("#findCount")).to_have_text("1/1")
    assert sayfa.locator("mark").count() >= 2  # öbek sınırında iki parça


def test_uc_hata_verirse_bolum_duz_kalir(sayfa):
    _uc(sayfa, durum=500)
    _okuyucu(sayfa)
    _ac_kapa(sayfa)
    expect(sayfa.locator("#altObek")).to_have_attribute("aria-pressed", "true")
    sayfa.wait_for_timeout(500)
    expect(sayfa.locator("span.obek")).to_have_count(0)
    expect(sayfa.locator("#readerBody article.chapter p[data-idx]")).to_have_count(len(tohum.TR))
