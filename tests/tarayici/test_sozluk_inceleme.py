"""4. aşama arayüzü gerçek tarayıcıda: inceleme listesi (nedenli), ret + geri al,
tür süzgeci, alternatif yazım, ek anlam, künyede "bağlam nedeniyle denetlenmedi"."""
from __future__ import annotations

from playwright.sync_api import expect

import tohum
from yardimci import js_bekle

SLUG = "gumus-kule"
SOZLUK = "async () => (await (await fetch('/api/book/gumus-kule/glossary')).json())"


def _sozlukte(ifade):
    """`v` sunucudaki sözlük yanıtıyken doğru olması beklenen JS ifadesi."""
    return (
        "async () => { const v = await (await fetch('/api/book/gumus-kule/glossary')).json();"
        f" return ({ifade}); }}"
    )


def _sozluge_git(sayfa):
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#openGlossaryBtn").click()
    expect(sayfa.locator("#glossaryView")).to_be_visible()


def test_inceleme_listesi_nedenleri_gosterir_onay_ve_ret(sayfa):
    from core import glossary

    tohum.kitap()
    glossary.merge_terms(SLUG, {"Nightmare Spell": "Kabus Büyüsü"}, "auto", 1, {"Nightmare Spell": "The Nightmare Spell woke."})
    glossary.set_term(SLUG, "Orc Empire", "Ork İmparatorluğu")
    glossary.set_term(SLUG, "Ore Empire", "Ork İmparatorluğu")
    glossary.set_term(SLUG, "Temiz", "Temiz Karşılık")
    _sozluge_git(sayfa)
    kutu = sayfa.locator("#glossReviewBox")
    expect(kutu).to_be_visible()
    expect(sayfa.locator("#glossReviewSayi")).to_have_text("İNCELENECEKLER (3)")
    kutu.locator("summary").click()
    kartlar = kutu.locator(".inceleme-kart")
    expect(kartlar).to_have_count(3)
    # Çakışanlar öne çıkar; yeni otomatik ekleme kaynak cümlesiyle gelir.
    expect(kartlar.first).to_contain_text("ÇAKIŞMA")
    yeni = kutu.locator(".inceleme-kart", has_text="Nightmare Spell")
    expect(yeni).to_contain_text("The Nightmare Spell woke.")
    # "İncelenecek" süzgeci aynı üç kaydı gösterir, temiz kayıt gizlenir.
    sayfa.locator("[data-gloss-filter=incelenecek]").click()
    expect(sayfa.locator("#glossList .gloss-row")).to_have_count(3)

    yeni.get_by_role("button", name="Reddet").click()
    js_bekle(sayfa, _sozlukte("!('Nightmare Spell' in v.terms)"))
    expect(kutu.locator(".inceleme-red")).to_contain_text("Nightmare Spell")
    # Reddedilen aday bir daha otomatik eklenmez.
    assert glossary.merge_terms(SLUG, {"Nightmare Spell": "Kabus Büyüsü"}, "auto", 5) == {}
    # GERİ AL: kayıt koşul/köken ile döner ve ret kalkar.
    sayfa.locator("#bildirim .bildirim-eylem").click()
    js_bekle(sayfa, _sozlukte("v.terms['Nightmare Spell'] === 'Kabus Büyüsü'"))
    assert glossary.red_listesi(SLUG) == []

    ore = kutu.locator(".inceleme-kart[data-sozluk-kaynak='Ore Empire']")
    ore.get_by_role("button", name="Doğru").click()
    expect(ore).to_have_count(0)


def test_tur_panelde_yazilir_ve_suzulur(sayfa):
    tohum.kitap()
    tohum.sozluk(SLUG, {"Saint": "Aziz", "Kaan": "Kaan"})
    _sozluge_git(sayfa)
    sayfa.locator("#glossList .gloss-row", has_text="Saint").click()
    sayfa.locator("#terimTur").select_option("rutbe")
    sayfa.locator("#terimKaydet").click()
    expect(sayfa.locator("#terimDurum")).to_contain_text("Sunucuya kaydedildi", timeout=10000)
    js_bekle(sayfa, _sozlukte("v.rows.find((r) => r.source === 'Saint').tur === 'rutbe'"))
    sayfa.keyboard.press("Escape")
    _sozluge_git(sayfa)  # tür sunucudan yeniden okunur
    sayfa.locator("#glossTurSuz").select_option("rutbe")
    expect(sayfa.locator("#glossList .gloss-row")).to_have_count(1)
    expect(sayfa.locator("#glossList .gloss-row .gloss-source")).to_have_text("Saint")


def test_alternatif_yazim_ve_ek_anlam_panelden_eklenir(sayfa):
    tohum.kitap()
    tohum.sozluk(SLUG, {"Great": "Ulu"}, {"Great": "rütbe"})
    _sozluge_git(sayfa)
    sayfa.locator("#glossList .gloss-row").first.click()
    sayfa.locator("#terimEkler > summary").click()
    sayfa.locator("#terimYazimYeni").fill("Grate")
    sayfa.locator("#terimYazimEkle").click()
    expect(sayfa.locator("#terimYazimlar .terim-aday")).to_have_text("Grate ×")
    # Kendi yazımını alternatif olarak eklemek reddedilir, sebep söylenir.
    sayfa.locator("#terimYazimYeni").fill("GREAT")
    sayfa.locator("#terimYazimEkle").click()
    expect(sayfa.locator("#terimEkDurum")).to_contain_text("kendi yazımı")

    sayfa.locator("#terimAnlamEkle").click()
    satir = sayfa.locator("#terimAnlamlar .terim-anlam").last
    satir.locator(".terim-anlam-hedef").fill("Harika")
    sayfa.locator("#terimAnlamKaydet").click()
    expect(sayfa.locator("#terimEkDurum")).to_contain_text("koşulu olmalı")
    satir.locator(".terim-anlam-kosul").fill("gündelik ünlem")
    sayfa.locator("#terimAnlamKaydet").click()
    expect(sayfa.locator("#terimEkDurum")).to_contain_text("Sunucuya kaydedildi")
    veri = js_bekle(sayfa, SOZLUK)
    assert veri["ekler"]["Great"] == {
        "yazimlar": ["Grate"], "anlamlar": [{"target": "Harika", "kosul": "gündelik ünlem"}],
    }
    # Ek düzenlemeler sürümü artırdı; ardından yapılan karşılık düzeltmesi kendi
    # kaydıyla çakışmamalı (panel yeni tabanı yanıtlardan aldı).
    sayfa.locator("#terimKarsilik").fill("Yüce")
    sayfa.locator("#terimKaydet").click()
    expect(sayfa.locator("#terimDurum")).to_contain_text("Sunucuya kaydedildi", timeout=10000)
    sayfa.keyboard.press("Escape")
    expect(sayfa.locator("#glossList .gloss-row .gloss-cip-yazim")).to_have_text("+1 YAZIM")


def test_kunyede_kosullu_kayit_denetlenmedi_notu(sayfa):
    tohum.kitap(bolum_sayisi=1)
    tohum.sozluk(SLUG, {"Silver Tower": "Gümüş Kule"}, {"Silver Tower": "yalnız yapı adı"})
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#chapterList .chapter-row").last.click()
    kunye = sayfa.locator("#readerBody .kunye").first
    kunye.locator("summary").click()
    expect(kunye.locator(".kunye-denetlenmedi")).to_contain_text("Silver Tower")
