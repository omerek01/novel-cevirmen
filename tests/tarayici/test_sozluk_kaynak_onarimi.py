"""Kaynak değişimi ve ret: telefon boyutunda gerçek form ve sunucu."""
from playwright.sync_api import expect
import pytest
import tohum
from yardimci import js_bekle
from core import glossary

SLUG = "gumus-kule"
pytestmark = pytest.mark.parametrize("sayfa", [{"width": 375, "height": 812}], indirect=True)


def ac(sayfa):
    tohum.kitap()
    glossary.set_term(SLUG, "Abel", "Abel")
    glossary.set_term(SLUG, "Great", "Ulu")
    glossary.yazim_ekle(SLUG, "Abel", "Abele")
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#openGlossaryBtn").click()
    sayfa.locator("#glossList .gloss-row[data-sozluk-kaynak='Great']").click()


def test_yeni_kaynak_eski_karsiligi_ve_kosulu_tasimaz(sayfa):
    ac(sayfa)
    sayfa.locator("#terimKosul").fill("rütbe olarak")
    sayfa.locator("#terimKaynak").fill("yeni ad")
    sayfa.locator("#terimKaynak").press("Enter")
    expect(sayfa.locator("#terimKarsilik")).to_have_value("")
    expect(sayfa.locator("#terimKosul")).to_have_value("")
    expect(sayfa.locator("#terimAynen")).not_to_be_checked()
    expect(sayfa.locator("#terimPaneli")).to_be_visible()


def test_alternatif_yazim_harften_bagimsiz_kayitli_adi_getirir(sayfa):
    ac(sayfa)
    sayfa.locator("#terimKaynak").fill("aBELE")
    sayfa.locator("#terimKaynak").press("Enter")
    expect(sayfa.locator("#terimKaynak")).to_have_value("Abel")
    expect(sayfa.locator("#terimKarsilik")).to_have_value("Abel")


def test_kaynak_yazarken_perde_dokunusu_paneli_kapatmaz(sayfa):
    ac(sayfa)
    sayfa.locator("#terimKaynak").fill("bilinmeyen")
    # Gerçek perde dokunusu: kaynak change olayı aynı dokunuşta çalışır.
    sayfa.mouse.click(1, 1)
    expect(sayfa.locator("#terimPaneli")).to_be_visible()
    sayfa.locator("#terimKaynak").fill("abel")
    sayfa.locator("#terimKaynak").press("Enter")
    expect(sayfa.locator("#terimKaynak")).to_have_value("Abel")
    sayfa.locator("#terimKapat").click()
    expect(sayfa.locator("#terimPaneli")).to_be_hidden()


def test_bos_kaynak_onceki_kaydi_sildirmez(sayfa):
    ac(sayfa)
    sayfa.locator("#terimKaynak").fill("")
    sayfa.locator("#terimKaynak").press("Enter")
    expect(sayfa.locator("#terimSil")).to_be_hidden()
    expect(sayfa.locator("#terimKarsilik")).to_have_value("")


def test_rette_cakisma_guncel_kaydi_gosterir_ve_tekrar_reddedilebilir(sayfa):
    tohum.kitap()
    glossary.merge_terms(SLUG, {"Nightmare Spell": "Kabus Büyüsü"}, chapter_no=1)
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#openGlossaryBtn").click()
    sayfa.locator("#glossReviewBox > summary").click()
    kart = sayfa.locator(".inceleme-kart[data-sozluk-kaynak='Nightmare Spell']")
    expect(kart).to_be_visible()
    # Liste açıkken öteki cihaz karşılığı değiştirir; hâlâ inceleme adayı olsun.
    glossary.terimi_yaz(SLUG, "Nightmare Spell", "Kabus Sihri", origin=None)
    sayfa.route("**/glossary/review", lambda r: r.abort() if r.request.method == "GET" else r.continue_())
    kart.get_by_role("button", name="Reddet", exact=True).click()
    expect(kart).to_contain_text("Kabus Sihri")
    expect(kart.get_by_role("button", name="Reddet", exact=True)).to_be_enabled()
    assert "Nightmare Spell" in glossary.get_glossary(SLUG)
    kart.get_by_role("button", name="Reddet", exact=True).click()
    js_bekle(sayfa, "async () => !(await (await fetch('/api/book/gumus-kule/glossary')).json()).terms['Nightmare Spell']")
    expect(sayfa.locator("#glossList .gloss-row[data-sozluk-kaynak='Nightmare Spell']")).to_have_count(0)


def test_basarisiz_taze_get_yeni_kayit_surumunu_geri_sarmaz(sayfa):
    ac(sayfa)
    sayfa.evaluate("""async () => {
        const m = await import('/js/sozluk.js');
        const asil = window.fetch.bind(window);
        window.fetch = (u, o={}) => o.cache === 'no-store'
            ? new Promise((r) => window.tazeBitir = () => { window.fetch=asil; r(new Response('{}',{status:503})); })
            : asil(u,o);
        window.tazeIstek = m.fetchGlossary('gumus-kule', {taze:true});
    }""")
    sayfa.locator("#terimKarsilik").fill("Yüce")
    sayfa.locator("#terimKaydet").click()
    js_bekle(sayfa, "async () => (await (await fetch('/api/book/gumus-kule/glossary')).json()).terms.Great === 'Yüce'")
    sayfa.evaluate("async () => { tazeBitir(); await tazeIstek; }")
    sayfa.locator("#terimKarsilik").fill("Ulu")
    sayfa.locator("#terimKaydet").click()
    js_bekle(sayfa, "async () => (await (await fetch('/api/book/gumus-kule/glossary')).json()).terms.Great === 'Ulu'")


@pytest.mark.sw_acik
def test_ret_oncesi_get_sonradan_bayat_onbellegi_geri_yazamaz(sayfa):
    tohum.kitap()
    glossary.merge_terms(SLUG, {"Nightmare Spell": "Kabus Büyüsü"}, chapter_no=1)
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#openGlossaryBtn").click()
    sayfa.locator("#glossReviewBox > summary").click()
    js_bekle(sayfa, "() => !!navigator.serviceWorker.controller")
    eski = sayfa.evaluate("async () => (await fetch('/api/book/gumus-kule/glossary')).text()")
    bekleyen = []
    sayfa.context.route("**/glossary?eski=1", lambda r: bekleyen.append(r))
    sayfa.evaluate("() => { window.eskiIstek = fetch('/api/book/gumus-kule/glossary?eski=1').catch(() => null); }")
    sayfa.locator(".inceleme-kart").get_by_role("button", name="Reddet", exact=True).click()
    expect(sayfa.locator("#bildirim")).to_contain_text("reddedildi")
    assert bekleyen
    bekleyen[0].fulfill(status=200, content_type="application/json", body=eski)
    sayfa.evaluate("async () => { await eskiIstek; }")
    assert sayfa.evaluate("""async () => {
        const c=await caches.open('novellink-data');
        const r=await c.match('/api/book/gumus-kule/glossary?eski=1');
        return !r || !(await r.json()).terms['Nightmare Spell'];
    }""")


@pytest.mark.sw_acik
def test_telefon_onbellegi_hata_verse_de_sunucudaki_ret_basarili_gorunur(sayfa):
    tohum.kitap()
    glossary.merge_terms(SLUG, {"Nightmare Spell": "Kabus Büyüsü"}, chapter_no=1)
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#openGlossaryBtn").click()
    sayfa.locator("#glossReviewBox > summary").click()
    js_bekle(sayfa, "() => !!navigator.serviceWorker.controller")
    worker = sayfa.context.service_workers[0]
    worker.evaluate("() => { self.caches.open = () => Promise.reject(new Error('depolama kullanılamıyor')); }")
    sayfa.locator(".inceleme-kart").get_by_role("button", name="Reddet", exact=True).click()
    expect(sayfa.locator("#bildirim")).to_contain_text("reddedildi")
    assert "Nightmare Spell" not in glossary.get_glossary(SLUG)
    expect(sayfa.locator("#glossList .gloss-row[data-sozluk-kaynak='Nightmare Spell']")).to_have_count(0)


@pytest.mark.sw_acik
def test_basarili_ret_telefonun_bayat_sozluk_onbellegini_temizler(sayfa):
    tohum.kitap()
    glossary.merge_terms(SLUG, {"Nightmare Spell": "Kabus Büyüsü"}, chapter_no=1)
    sayfa.goto(sayfa.taban + "/")
    sayfa.locator("#shelves .spine[data-slug]").first.click()
    sayfa.locator("#openGlossaryBtn").click()
    sayfa.locator("#glossReviewBox > summary").click()
    js_bekle(sayfa, "() => !!navigator.serviceWorker.controller")
    sayfa.evaluate("""async () => {
        const c = await caches.open('novellink-data');
        const r = await fetch('/api/book/gumus-kule/glossary');
        await c.put('/api/book/gumus-kule/glossary', r.clone());
        await c.put('/api/book/gumus-kule/glossary?spoiler=1', r.clone());
        await c.put('/api/book/baska/glossary', new Response('{}'));
        await c.put('/api/chapter?url=ornek', new Response('{}'));
    }""")
    # Reddin kendisi başarılı; hemen sonraki sözlük GET'i sunucu hatasına düşer.
    # no-store isteği SW'yi atlar ve ret öncesi telefon kopyasını geri getiremez.
    sayfa.context.route("**/api/book/gumus-kule/glossary", lambda r: r.fulfill(
        status=503, content_type="application/json", body='{"detail":"geçici hata"}'))
    sayfa.locator(".inceleme-kart").get_by_role("button", name="Reddet", exact=True).click()
    expect(sayfa.locator("#bildirim")).to_contain_text("reddedildi")
    js_bekle(sayfa, """async () => {
        const c = await caches.open('novellink-data');
        return !(await c.match('/api/book/gumus-kule/glossary')) &&
            !(await c.match('/api/book/gumus-kule/glossary?spoiler=1'));
    }""")
    assert sayfa.evaluate("""async () => {
        const c = await caches.open('novellink-data');
        return !!(await c.match('/api/book/baska/glossary')) &&
            !!(await c.match('/api/chapter?url=ornek'));
    }""")
    expect(sayfa.locator("#glossList .gloss-row[data-sozluk-kaynak='Nightmare Spell']")).to_have_count(0)
