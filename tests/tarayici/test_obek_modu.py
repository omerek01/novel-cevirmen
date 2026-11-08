"""Öbek modu (hızlı okuma planı Adım C, 2026-11-08): sabit boylu öbekler (2-6 sözcük),
alt çubuktan açılan kumanda ile büyütme / küçültme, kalıcılık ve arama vurgusu."""
from playwright.sync_api import expect

import tohum


def _okuyucu(sayfa):
    tohum.kitap(bolum_sayisi=1)
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#chapterList .chapter-row").first.click()
    expect(sayfa.locator("#readerBody article.chapter p[data-idx]")).to_have_count(len(tohum.TR))


def _kumanda(sayfa):
    sayfa.locator("#altHap").click()
    sayfa.locator("#altObek").click()
    expect(sayfa.locator("#obekKumanda")).to_be_visible()


def _ilk_obekler(sayfa):
    return sayfa.locator("#readerBody article.chapter p[data-idx]").first.locator("span.obek").all_inner_texts()


def test_kumanda_ile_ac_buyut_kucult_kapat_ve_kalicilik(sayfa):
    _okuyucu(sayfa)
    metin = sayfa.locator("#readerBody article.chapter p[data-idx]").first.inner_text()
    _kumanda(sayfa)
    expect(sayfa.locator("#okuyucuAlt")).to_be_hidden()  # kumanda alt çubuğun yerini alır
    expect(sayfa.locator("#obekBoyu")).to_have_text("3")
    assert _ilk_obekler(sayfa)[:2] == ["Kaan fenerini yaktı", "ve dar geçidin"]
    assert sayfa.locator("#readerBody article.chapter p[data-idx]").first.inner_text() == metin
    sayfa.locator("#obekBuyut").click()
    expect(sayfa.locator("#obekBoyu")).to_have_text("4")
    assert _ilk_obekler(sayfa)[0] == "Kaan fenerini yaktı ve"
    for _ in range(5):
        if sayfa.locator("#obekKucult").is_disabled():
            break
        sayfa.locator("#obekKucult").click()
    expect(sayfa.locator("#obekBoyu")).to_have_text("2")
    assert sayfa.evaluate("JSON.parse(localStorage.getItem('novellink:settings')).obekBoyu") == 2

    sayfa.locator("#obekTamam").click()  # kumanda gizlenir, mod açık kalır
    expect(sayfa.locator("#obekKumanda")).to_be_hidden()
    expect(sayfa.locator("#okuyucuAlt")).to_be_visible()
    expect(sayfa.locator("#altObek")).to_have_attribute("aria-pressed", "true")

    sayfa.reload()
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#chapterList .chapter-row").first.click()
    expect(sayfa.locator("span.obek").first).to_have_text("Kaan fenerini")

    _kumanda(sayfa)
    sayfa.locator("#obekKapat").click()
    expect(sayfa.locator("span.obek")).to_have_count(0)
    expect(sayfa.locator("#altObek")).to_have_attribute("aria-pressed", "false")


def test_obek_sinirini_asan_arama_eslesmesi_tek_sayilir(sayfa):
    _okuyucu(sayfa)
    _kumanda(sayfa)
    sayfa.locator("#obekTamam").click()
    sayfa.locator("#findBtn").click()
    sayfa.locator("#findInput").fill("yaktı ve")  # "Kaan fenerini yaktı" | "ve dar geçidin"
    expect(sayfa.locator("#findCount")).to_have_text("1/1")
    assert sayfa.locator("mark").count() >= 2
