"""Okuma Salonu sözlüğü: büyük başlık, "?" ile açılan açıklama, örnek koşul düğmeleri."""
from __future__ import annotations

from playwright.sync_api import expect

import tohum

SLUG = "gumus-kule"


def _sozluk(sayfa):
    tohum.kitap()
    tohum.sozluk(SLUG, {"Great": "Ulu"})
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#openGlossaryBtn").click()
    expect(sayfa.locator("#glossList .gloss-row")).to_have_count(1)


def test_baslik_ve_soru_isaretiyle_acilan_aciklama(sayfa):
    _sozluk(sayfa)
    expect(sayfa.locator("#glossaryView .gloss-title")).to_have_text("Sözlük")
    aciklama = sayfa.locator("#glossaryView .gloss-help .gloss-hint")
    expect(aciklama).to_be_hidden()
    sayfa.locator("#glossaryView .gloss-help > summary").click()
    expect(aciklama).to_be_visible()


def test_ornek_kosul_dugmesi_kosula_ekler(sayfa):
    _sozluk(sayfa)
    sayfa.locator("#glossList .gloss-row", has_text="Great").click()
    expect(sayfa.locator("#terimPaneli")).to_be_visible()
    kosul = sayfa.locator("#terimKosul")
    kosul.fill("")
    sayfa.locator('#terimKosulOrnekleri button[data-ek="gündelik anlamda çevrilmez"]').click()
    expect(kosul).to_have_value("gündelik anlamda çevrilmez")
    sayfa.locator('#terimKosulOrnekleri button[data-ek^="yalnız unvan"]').click()
    expect(kosul).to_have_value("gündelik anlamda çevrilmez; yalnız unvan ya da rütbe olarak geçtiğinde")
