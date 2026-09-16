"""Dar ekran ve %200 büyütme: yatay kaydırma olmamalı (belge, erişilebilirlik).

%200 metin büyütmesi 390 px'lik telefonda ~195 CSS piksellik yerleşim genişliği
demektir; 320 px WCAG'nin yeniden akış (reflow) ölçütüdür.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

import tohum

TASMA = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
TASAN_OGELER = """() => [...document.querySelectorAll('body *')]
  .filter((e) => e.offsetParent !== null && e.getBoundingClientRect().right > innerWidth + 1)
  .slice(0, 8).map((e) => (e.id ? '#' + e.id : e.className || e.tagName) + ':' +
    Math.round(e.getBoundingClientRect().right))"""


def _tasma_yok(sayfa, yer):
    fazla = sayfa.evaluate(TASMA)
    assert fazla <= 1, f"{yer}: {fazla}px yatay taşma — {sayfa.evaluate(TASAN_OGELER)}"


@pytest.mark.parametrize(
    "sayfa", [{"width": 320, "height": 640}, {"width": 195, "height": 420}], indirect=True,
    ids=["320px", "zoom200"],
)
def test_kitap_sozluk_ve_terim_paneli_yatay_tasmaz(sayfa):
    tohum.kitap()
    tohum.sozluk("gumus-kule", {"Lord of the Nine Heavens": "Dokuz Göğün Efendisi"},
                 {"Lord of the Nine Heavens": "yalnız unvan olarak"})
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    expect(sayfa.locator("#bookView")).to_be_visible()
    sayfa.locator("#bookMore > summary").click()
    _tasma_yok(sayfa, "kitap sayfası")
    sayfa.locator("#openGlossaryBtn").click()
    expect(sayfa.locator("#glossList .gloss-row")).to_have_count(1)
    _tasma_yok(sayfa, "sözlük")
    sayfa.locator("#glossList .gloss-row").first.click()
    expect(sayfa.locator("#terimPaneli")).to_be_visible()
    _tasma_yok(sayfa, "terim paneli")
    # <dialog> sabit konumlu: belge genişliğine katılmaz, kartın KENDİSİ ölçülür.
    kart = sayfa.evaluate(
        "() => { const k = document.querySelector('#terimPaneli .terim-kart');"
        " return [k.scrollWidth - k.clientWidth, k.getBoundingClientRect().right - innerWidth]; }"
    )
    assert kart[0] <= 1 and kart[1] <= 1, f"terim paneli kartı taşıyor: {kart}"


# Onay kutusu/radyo, 44 px'lik ETİKETİN içindeyse hedef etikettir.
KUCUK_HEDEFLER = """(kok) => [...document.querySelectorAll(
    `${kok} button, ${kok} summary, ${kok} input, ${kok} textarea, ${kok} a`)]
  .filter((e) => (e.offsetParent !== null || e.closest('dialog[open]')) && e.type !== 'hidden')
  .filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
  .filter((e) => {
    const t = e.closest('label') && ['checkbox', 'radio'].includes(e.type) ? e.closest('label') : e;
    return t.getBoundingClientRect().height < 44;
  })
  .map((e) => (e.id || e.className || e.tagName) + ':' + Math.round(e.getBoundingClientRect().height))"""


def test_dokunma_hedefleri_44px(sayfa):
    """Belge: telefon için 44-48 CSS piksel dokunma alanı TASARIM HEDEFİ (AA zorunluluğu değil)."""
    tohum.kitap()
    tohum.sozluk("gumus-kule", {"Silver Tower": "Gümüş Kule"}, {"Silver Tower": "yalnız yapı"})
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#bookMore > summary").click()
    assert sayfa.evaluate(KUCUK_HEDEFLER, "#bookView") == []
    sayfa.locator("#openGlossaryBtn").click()
    expect(sayfa.locator("#glossList .gloss-row")).to_have_count(1)
    sayfa.locator("#glossIoBox > summary").click()
    assert sayfa.evaluate(KUCUK_HEDEFLER, "#glossaryView") == []
    sayfa.locator("#glossList .gloss-row").first.click()
    sayfa.locator("#terimEtkiBtn").click()
    expect(sayfa.locator("#terimEtki .terim-etki-satir")).to_have_count(2)
    assert sayfa.evaluate(KUCUK_HEDEFLER, "#terimPaneli") == []
