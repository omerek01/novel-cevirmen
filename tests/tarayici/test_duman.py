"""Duman testleri: uygulamanın ana akışları uçtan uca çalışıyor mu.

Modül bölmesi (app.js -> js/*.js) bu testler yeşilken yapıldı ve sonrasında da
yeşil kalmak ZORUNDA: build adımı olmayan bir kod tabanında tanımsız bir
tanımlayıcı ancak o kod yolu koşunca patlar.
"""
from __future__ import annotations

import json
import urllib.request

import pytest
from playwright.sync_api import expect

import tohum

SLUG = "gumus-kule"


def _api(sayfa, yol: str):
    with urllib.request.urlopen(sayfa.taban + yol, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def _ac(sayfa):
    sayfa.goto(sayfa.taban + "/")
    expect(sayfa.locator("#shelves .spine[data-slug]").first).to_be_visible()


def test_kutuphane_raf_ve_devam_fisi(sayfa):
    tohum.kitap(bolum_sayisi=2, konum=1)
    _ac(sayfa)
    expect(sayfa.locator(".spine-title").first).to_have_text("Gumus Kule")
    expect(sayfa.locator("#resumeFiche")).to_be_visible()


def test_kitap_sayfasi_bolum_listesi_ters_sirada(sayfa):
    tohum.kitap(bolum_sayisi=3)
    _ac(sayfa)
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    expect(sayfa.locator("#bookView")).to_be_visible()
    satirlar = sayfa.locator("#chapterList .chapter-row .chapter-no")
    expect(satirlar).to_have_count(3)
    expect(satirlar.first).to_have_text("BÖLÜM 3")


def _okuyucuya_gir(sayfa, bolum_sayisi=2):
    urller = tohum.kitap(bolum_sayisi=bolum_sayisi)
    _ac(sayfa)
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#chapterList .chapter-row").last.click()  # en altta 1. bölüm
    expect(sayfa.locator("#readerView")).to_be_visible()
    expect(sayfa.locator("#readerBody article.chapter").first.locator("p[data-idx]")).to_have_count(
        len(tohum.TR)
    )
    return urller


def test_okuyucu_paragraflar_ve_kunye(sayfa):
    _okuyucuya_gir(sayfa)
    ilk = sayfa.locator("#readerBody article.chapter").first
    expect(ilk.locator(".kunye")).to_have_count(1)
    expect(sayfa.locator("#readerChapter")).to_have_text("Chapter 1")


def test_cift_dokunma_ingilizce_satiri_acar(sayfa):
    _okuyucuya_gir(sayfa)
    p = sayfa.locator("#readerBody article.chapter").first.locator("p[data-idx]").nth(1)
    p.click()
    p.click()
    satir = sayfa.locator("#readerBody .source-line").first
    expect(satir).to_have_text(tohum.EN[1])


def test_sonsuz_okuma_sonraki_bolumu_ekler(sayfa):
    _okuyucuya_gir(sayfa, bolum_sayisi=2)
    sayfa.mouse.wheel(0, 20000)
    expect(sayfa.locator("#readerBody article.chapter")).to_have_count(2, timeout=15000)


def test_sozluk_ekle_ara_sil(sayfa):
    tohum.kitap()
    tohum.sozluk(SLUG, {"Silver Tower": "Gümüş Kule", "Kaan": "Kaan"})
    _ac(sayfa)
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#openGlossaryBtn").click()
    expect(sayfa.locator("#glossaryView")).to_be_visible()
    expect(sayfa.locator("#glossList .gloss-row")).to_have_count(2)

    sayfa.locator("#glossSource").fill("Mira")
    sayfa.locator("#glossTarget").fill("Mira")
    sayfa.locator("#glossAddBtn").click()
    expect(sayfa.locator("#glossList .gloss-row")).to_have_count(3)
    sayfa.wait_for_function(
        "async () => (await (await fetch('/api/book/gumus-kule/glossary')).json()).terms.Mira === 'Mira'"
    )

    sayfa.locator("#glossSearch").fill("gümüş")
    expect(sayfa.locator("#glossList .gloss-row")).to_have_count(1)


@pytest.mark.xfail(
    strict=True,
    reason="BİLİNEN HATA: süzgeç eski sunucu listesinden çizer; gönderilen terim "
    "kuyruktan düşünce listeden kaybolur (kuyruk v2 ile düzelecek)",
)
def test_eklenen_terim_gonderimden_sonra_suzgecte_kaybolmaz(sayfa):
    tohum.kitap()
    tohum.sozluk(SLUG, {"Silver Tower": "Gümüş Kule"})
    _ac(sayfa)
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#openGlossaryBtn").click()
    expect(sayfa.locator("#glossList .gloss-row")).to_have_count(1)
    sayfa.locator("#glossSource").fill("Mira")
    sayfa.locator("#glossAddBtn").click()
    sayfa.wait_for_function(
        "async () => (await (await fetch('/api/book/gumus-kule/glossary')).json()).terms.Mira === 'Mira'"
    )
    sayfa.wait_for_function("() => !document.querySelector('#glossList .gloss-row-pending')")
    sayfa.locator("#glossSearch").fill("x")
    sayfa.locator("#glossSearch").fill("")
    expect(sayfa.locator("#glossList .gloss-row")).to_have_count(2)


def test_sozluk_silme_sunucuya_ulasir(sayfa):
    tohum.kitap()
    tohum.sozluk(SLUG, {"Silver Tower": "Gümüş Kule"})
    _ac(sayfa)
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#openGlossaryBtn").click()
    expect(sayfa.locator("#glossList .gloss-row")).to_have_count(1)
    sayfa.locator("#glossList .gloss-del").first.click()
    sayfa.wait_for_function(
        "async () => !('Silver Tower' in (await (await fetch('/api/book/gumus-kule/glossary')).json()).terms)"
    )


def test_ayarlar_temasi_degisir(sayfa):
    tohum.kitap()
    _ac(sayfa)
    sayfa.locator(".navtab[data-tab=settings]").click()
    expect(sayfa.locator("#settingsPanel")).to_be_visible()
    sayfa.locator("[data-theme-opt=dark]").click()
    expect(sayfa.locator("html")).to_have_attribute("data-theme", "dark")


def test_kitap_ekle_modali_acilir_kapanir(sayfa):
    tohum.kitap()
    _ac(sayfa)
    sayfa.locator(".spine-add").click()
    expect(sayfa.locator("#addModal")).to_be_visible()
    sayfa.locator("#addCancel").click()
    expect(sayfa.locator("#addModal")).to_be_hidden()


def test_kitap_sayfasi_modallari(sayfa):
    tohum.kitap()
    _ac(sayfa)
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    for dugme, modal, kapat in (
        ("#bulkBtn", "#bulkModal", "#bulkCancel"),
        ("#epubBtn", "#epubModal", "#epubCancel"),
        ("#addChapterBtn", "#chapterAddModal", "#chAddCancel"),
        ("#mergeBtn", "#mergeModal", "#mergeCancel"),
    ):
        sayfa.locator(dugme).click()
        expect(sayfa.locator(modal)).to_be_visible()
        sayfa.locator(kapat).click()
        expect(sayfa.locator(modal)).to_be_hidden()


def test_secimden_sozluge_ekle(sayfa):
    _okuyucuya_gir(sayfa)
    sayfa.route(
        "**/glossary/suggest",
        lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"source": "Mira", "target": "Mira", "is_character": True}),
        ),
    )
    # İngilizce satırı aç ve oradan bir özel ad seç.
    p = sayfa.locator("#readerBody article.chapter").first.locator("p[data-idx]").nth(1)
    p.click()
    p.click()
    expect(sayfa.locator("#readerBody .source-line").first).to_be_visible()
    sayfa.evaluate(
        """() => {
          const n = document.querySelector('#readerBody .source-line').firstChild;
          const i = n.textContent.indexOf('Mira');
          const r = document.createRange();
          r.setStart(n, i); r.setEnd(n, i + 4);
          const s = getSelection(); s.removeAllRanges(); s.addRange(r);
        }"""
    )
    expect(sayfa.locator("#selGlossBtn")).to_be_visible()
    sayfa.locator("#selGlossBtn").click()
    expect(sayfa.locator("#glossQuickModal")).to_be_visible()
    expect(sayfa.locator("#glossQuickSource")).to_have_value("Mira")
    expect(sayfa.locator("#glossQuickTarget")).to_have_value("Mira")
    sayfa.locator("#glossQuickSave").click()
    sayfa.wait_for_function(
        "async () => (await (await fetch('/api/book/gumus-kule/glossary')).json()).terms.Mira === 'Mira'"
    )
