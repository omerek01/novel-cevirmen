"""Ortak <dialog> bileşeni — belgedeki kabul ölçütleri.

"Tab arka plana kaçmaz; ekran okuyucu pencere başlığını duyurur." Ek olarak:
Escape kapatır, kapanınca odak açan düğmeye döner, perdeye dokunmak kapatır.
"""
from __future__ import annotations

from playwright.sync_api import expect

import tohum


def _ac(sayfa):
    tohum.kitap()
    sayfa.goto(sayfa.taban + "/")
    expect(sayfa.locator("#shelves .spine[data-slug]").first).to_be_visible()


# Arka plan `inert` olduğu için odak arka plandaki bir öğeye İNEMEZ. Son öğeden
# sonraki Tab tarayıcı arayüzüne gider (başsız tarayıcıda `body` görünür) — bu
# arka plana kaçmak değildir; ölçüt "arka plandaki bir sayfa öğesi odak aldı mı".
ODAK_ICERIDE = (
    "(id) => { const a = document.activeElement;"
    " return a === document.body || document.getElementById(id).contains(a); }"
)


def test_tab_arka_plana_kacmaz_escape_kapatir_odak_geri_doner(sayfa):
    _ac(sayfa)
    sayfa.locator(".spine-add").click()
    diyalog = sayfa.locator("#addModal")
    expect(diyalog).to_be_visible()
    assert sayfa.evaluate("() => document.getElementById('addModal').open")
    icerde = 0
    for _ in range(25):
        sayfa.keyboard.press("Tab")
        assert sayfa.evaluate(ODAK_ICERIDE, "addModal"), "odak arka plandaki bir öğeye kaçtı"
        icerde += sayfa.evaluate("(id) => document.getElementById(id).contains(document.activeElement)", "addModal")
    assert icerde > 15, "Tab diyaloğun içinde dolaşmalı"
    sayfa.keyboard.press("Escape")
    expect(diyalog).to_be_hidden()
    assert sayfa.evaluate("() => document.activeElement.classList.contains('spine-add')")


def test_pencere_basligi_aria_labelledby_ile_bagli(sayfa):
    _ac(sayfa)
    for dugme, kimlik in ((".spine-add", "addModal"),):
        sayfa.locator(dugme).click()
        baslik = sayfa.evaluate(
            "(id) => { const d = document.getElementById(id);"
            " const b = document.getElementById(d.getAttribute('aria-labelledby'));"
            " return b ? b.textContent.trim() : null; }",
            kimlik,
        )
        assert baslik == "KİTAP EKLE"
    # Bütün modallar başlığa bağlı: hiçbiri adsız duyurulmamalı.
    adsizlar = sayfa.evaluate(
        "() => [...document.querySelectorAll('dialog')].filter((d) => {"
        " const id = d.getAttribute('aria-labelledby');"
        " return !(id && document.getElementById(id)) && !d.getAttribute('aria-label'); })"
        ".map((d) => d.id)"
    )
    assert adsizlar == []


def test_perdeye_dokunmak_kapatir(sayfa):
    _ac(sayfa)
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#epubBtn").click()
    expect(sayfa.locator("#epubModal")).to_be_visible()
    sayfa.mouse.click(5, 5)  # kartın dışı
    expect(sayfa.locator("#epubModal")).to_be_hidden()


def test_ayar_paneli_diyalog_escape_ile_kapanir(sayfa):
    _ac(sayfa)
    sayfa.locator(".navtab[data-tab=settings]").click()
    expect(sayfa.locator("#settingsPanel")).to_be_visible()
    sayfa.keyboard.press("Escape")
    expect(sayfa.locator("#settingsPanel")).to_be_hidden()
