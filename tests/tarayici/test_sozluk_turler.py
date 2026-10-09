"""Kitaba özel türler gerçek tarayıcıda: panelden tür ekle + ata, hazır türü yeniden
adlandır ve sil; "Aynen koru" kaydı listede kelimenin kendisiyle görünür."""
from __future__ import annotations

from playwright.sync_api import expect

import tohum
from yardimci import js_bekle

SLUG = "gumus-kule"


def _sozlukte(ifade):
    return (
        "async () => { const v = await (await fetch('/api/book/gumus-kule/glossary')).json();"
        f" return ({ifade}); }}"
    )


def _sozluge_git(sayfa):
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#openGlossaryBtn").click()
    expect(sayfa.locator("#glossaryView")).to_be_visible()


def test_panelden_yeni_tur_eklenir_ve_kayda_atanir(sayfa):
    tohum.kitap()
    tohum.sozluk(SLUG, {"Fire Keepers": "Ateş Bekçileri"})
    _sozluge_git(sayfa)
    sayfa.locator("#glossList .gloss-row", has_text="Fire Keepers").click()
    sayfa.locator("#terimTurYonet > summary").click()
    sayfa.locator("#terimTurYeni").fill("Klan")
    sayfa.locator("#terimTurEkle").click()
    expect(sayfa.locator("#terimTurDurum")).to_contain_text("eklendi")
    expect(sayfa.locator("#terimTur")).to_have_value("Klan")
    sayfa.locator("#terimKaydet").click()
    js_bekle(sayfa, _sozlukte("v.rows.find((r) => r.source === 'Fire Keepers').tur === 'Klan'"))
    # Süzgeç de yeni türü bilir.
    sayfa.keyboard.press("Escape")
    sayfa.locator("#glossTurSuz").select_option("Klan")
    expect(sayfa.locator("#glossList .gloss-row")).to_have_count(1)


def test_hazir_tur_yeniden_adlandirilir_ve_silinir(sayfa):
    tohum.kitap()
    tohum.sozluk(SLUG, {"Saint": "Aziz"})
    from core import glossary

    glossary.terimi_yaz(SLUG, "Saint", "Aziz", tur="rutbe")
    _sozluge_git(sayfa)
    sayfa.locator("#glossList .gloss-row", has_text="Saint").click()
    sayfa.locator("#terimTurYonet > summary").click()
    satir = sayfa.locator("#terimTurListe .terim-tur-satir").nth(3)  # rütbe
    satir.locator("input").fill("Unvan")
    satir.get_by_role("button", name="Adı kaydet").click()
    expect(sayfa.locator("#terimTur option[value='rutbe']")).to_have_text("Unvan")
    expect(sayfa.locator("#terimTur")).to_have_value("rutbe")
    sayfa.once("dialog", lambda d: d.accept())
    sayfa.locator("#terimTurListe .terim-tur-satir").nth(3).get_by_role("button", name="Sil").click()
    expect(sayfa.locator("#terimTur option[value='rutbe']")).to_have_count(0)
    js_bekle(sayfa, _sozlukte("v.rows.find((r) => r.source === 'Saint').tur === null"))
    js_bekle(sayfa, _sozlukte("!v.turler.some((t) => t.kod === 'rutbe')"))


def test_aynen_koru_kaydi_kelimenin_kendisiyle_gorunur(sayfa):
    tohum.kitap()
    tohum.sozluk(SLUG, {"Kaan": "Kaan"})
    _sozluge_git(sayfa)
    expect(sayfa.locator("#glossList .gloss-row", has_text="Kaan").locator(".gloss-target-metin")).to_have_text("Kaan")
