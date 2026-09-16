"""Terim paneli — belgedeki kabul ölçütleri gerçek tarayıcıda.

* Türkçe metinden yapılan seçim İngilizce kaynağı OTOMATİK doldurmaz; hizalı
  paragraftan adaylar sunulur, kullanıcı seçer.
* Koşul panelde düzenlenir ve sunucuya ulaşır.
* "Etkilenen bölümler" örnekleriyle listelenir; seçilenler yeniden çeviri işine gider.
* Sözlük süzgeçleri: koşullu, okuduğum bölümde.
"""
from __future__ import annotations

import json

from playwright.sync_api import expect

import tohum

SLUG = "gumus-kule"


def _okuyucuya_gir(sayfa):
    urller = tohum.kitap(bolum_sayisi=2)
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#chapterList .chapter-row").last.click()
    expect(sayfa.locator("#readerBody article.chapter").first.locator("p[data-idx]")).to_have_count(
        len(tohum.TR)
    )
    return urller


def _sec(sayfa, secici, sozcuk):
    sayfa.evaluate(
        """([secici, sozcuk]) => {
          const n = document.querySelector(secici).firstChild;
          const i = n.textContent.indexOf(sozcuk);
          const r = document.createRange();
          r.setStart(n, i); r.setEnd(n, i + sozcuk.length);
          const s = getSelection(); s.removeAllRanges(); s.addRange(r);
        }""",
        [secici, sozcuk],
    )


def _sozluge_git(sayfa):
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#openGlossaryBtn").click()
    expect(sayfa.locator("#glossaryView")).to_be_visible()


def test_turkce_secim_kaynagi_otomatik_doldurmaz_aday_sunar(sayfa):
    _okuyucuya_gir(sayfa)
    tohum.sozluk(SLUG, {"Silver Tower": "Gümüş Kule"})
    # 3. paragraf: "Gümüş Kule'nin çanı…" ↔ "The bell of the Silver Tower…"
    _sec(sayfa, "#readerBody article.chapter p[data-idx='2']", "Gümüş Kule")
    expect(sayfa.locator("#selGlossBtn")).to_be_visible()
    sayfa.locator("#selGlossBtn").click()
    expect(sayfa.locator("#terimPaneli")).to_be_visible()
    expect(sayfa.locator("#terimEnParagraf")).to_contain_text("Silver Tower")
    expect(sayfa.locator("#terimKaynak")).to_have_value("")
    aday = sayfa.locator("#terimAdaylar .terim-aday-kayitli")
    expect(aday).to_have_text("Silver Tower → Gümüş Kule")
    aday.click()
    expect(sayfa.locator("#terimKaynak")).to_have_value("Silver Tower")
    expect(sayfa.locator("#terimKarsilik")).to_have_value("Gümüş Kule")
    expect(sayfa.locator("#terimSil")).to_be_visible()
    # Kapatınca okuyucu yerinde kalır.
    sayfa.keyboard.press("Escape")
    expect(sayfa.locator("#terimPaneli")).to_be_hidden()
    expect(sayfa.locator("#readerView")).to_be_visible()


def test_kosul_panelde_duzenlenir_ve_koşullu_suzgeci(sayfa):
    tohum.kitap()
    tohum.sozluk(SLUG, {"Great": "Ulu", "Kaan": "Kaan"})
    _sozluge_git(sayfa)
    expect(sayfa.locator("#glossList .gloss-row")).to_have_count(2)
    sayfa.locator("#glossList .gloss-row", has_text="Great").click()
    sayfa.locator("#terimKosul").fill("yalnız rütbe adı olarak")
    sayfa.locator("#terimKaydet").click()
    sayfa.wait_for_function(
        "async () => (await (await fetch('/api/book/gumus-kule/glossary')).json())"
        ".kosullar.Great === 'yalnız rütbe adı olarak'"
    )
    # Karşılığa dokunmayan ikinci kayıt koşulu SİLMEZ.
    sayfa.locator("#terimKarsilik").fill("Yüce")
    sayfa.locator("#terimKaydet").click()
    sayfa.wait_for_function(
        "async () => (await (await fetch('/api/book/gumus-kule/glossary')).json()).terms.Great === 'Yüce'"
    )
    sayfa.keyboard.press("Escape")
    sayfa.locator("[data-gloss-filter=kosullu]").click()
    expect(sayfa.locator("#glossList .gloss-row")).to_have_count(1)
    expect(sayfa.locator("#glossList .gloss-row .gloss-cip-kosul")).to_have_text("KOŞULLU")
    veri = sayfa.evaluate("async () => (await fetch('/api/book/gumus-kule/glossary')).json()")
    assert veri["kosullar"]["Great"] == "yalnız rütbe adı olarak"


def test_okudugum_bolumde_suzgeci(sayfa):
    tohum.kitap()
    # "Ore Empire" hiçbir bölüm kaynağında geçmiyor.
    tohum.sozluk(SLUG, {"Silver Tower": "Gümüş Kule", "Ore Empire": "Maden İmparatorluğu"})
    _sozluge_git(sayfa)
    expect(sayfa.locator("#glossList .gloss-row")).to_have_count(2)
    sayfa.locator("[data-gloss-filter=bolumde]").click()
    expect(sayfa.locator("#glossList .gloss-row")).to_have_count(1)
    expect(sayfa.locator("#glossList .gloss-row .gloss-source")).to_have_text("Silver Tower")
    expect(sayfa.locator("#glossCount")).to_contain_text("Okuduğun bölümde")


def test_etkilenen_bolumler_ornekli_listelenir_secilenler_ise_gider(sayfa):
    urller = tohum.kitap(bolum_sayisi=2)
    tohum.sozluk(SLUG, {"Silver Tower": "Gümüş Kule"})
    istekler = []

    def retranslate(route):
        istekler.append(json.loads(route.request.post_data))
        route.fulfill(status=200, content_type="application/json", body='{"job_id": "is-1"}')

    sonuclar = {urller[0]: {"durum": "tamam", "hizali": True, "ihlal": 0, "kalinti": 0,
                            "model": "gemini-3.6-flash"}}
    sayfa.route("**/api/book/*/retranslate", retranslate)
    sayfa.route(
        "**/api/bulk/is-1",
        lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"state": "done", "message": "Bitti — 1 bölüm yeniden çevrildi.",
                             "params": {"urls": [urller[0]], "sonuclar": sonuclar}}),
        ),
    )
    _sozluge_git(sayfa)
    sayfa.locator("#glossList .gloss-row").first.click()
    sayfa.locator("#terimEtkiBtn").click()
    satirlar = sayfa.locator("#terimEtki .terim-etki-satir")
    expect(satirlar).to_have_count(2)
    expect(satirlar.first.locator(".terim-etki-ornek[lang=en]")).to_contain_text("Silver Tower")
    expect(satirlar.first.locator(".terim-etki-ornek[lang=tr]")).to_contain_text("Gümüş Kule")
    # İkinci bölümün işaretini kaldır: yalnız seçilen gider.
    sayfa.locator(f"#terimEtki li[data-url='{urller[1]}'] input[type=checkbox]").uncheck()
    sayfa.get_by_role("button", name="Seçilenleri yeniden çevir").click()
    expect(sayfa.locator(f"#terimEtki li[data-url='{urller[0]}'] .terim-etki-sonuc")).to_contain_text(
        "YENİLENDİ"
    )
    assert istekler == [{"urls": [urller[0]]}]
