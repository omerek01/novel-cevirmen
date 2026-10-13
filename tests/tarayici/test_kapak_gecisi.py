"""Kapak geçişi: gerçek tarayıcı anlık görüntüsü, azaltılmış hareket ve geri tuşu."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

import tohum


def _kutuphane(sayfa):
    tohum.kitap()
    sayfa.goto(sayfa.taban + "/")
    expect(sayfa.locator('#shelves .spine[data-slug="gumus-kule"]')).to_be_visible()


def test_raf_kapagi_kitap_kapagina_donusur_ve_geri_donulebilir(sayfa):
    sayfa.emulate_media(reduced_motion="no-preference")
    _kutuphane(sayfa)
    # Native API korunur: ready reddedilirse çift ad/eksik yeni görüntü yakalanır.
    sayfa.evaluate("""() => {
      const baslat = document.startViewTransition.bind(document);
      window.kapakKaydi = null;
      document.startViewTransition = (guncelle) => {
        const eski = getComputedStyle(document.querySelector(
          '#shelves .spine[data-slug="gumus-kule"] .spine-art')).viewTransitionName;
        const gecis = baslat(async () => {
          await guncelle();
          window.kapakKaydi = { eski,
            yeni: getComputedStyle(document.querySelector('#bookHeroArt')).viewTransitionName,
            ad: document.querySelector('#bookHeroTitle').textContent };
        });
        window.kapakGecisi = gecis;
        // ready yalnız bu testte izlenir; uygulama da olası reddi tüketmelidir.
        gecis.ready.catch(() => {});
        return gecis;
      };
    }""")
    sayfa.locator('#shelves .spine[data-slug="gumus-kule"]').click()
    expect(sayfa.locator("#bookView")).to_be_visible()
    sayfa.wait_for_function("window.kapakKaydi !== null")
    kayit = sayfa.evaluate("window.kapakKaydi")
    assert kayit["eski"] != "none"
    assert kayit["yeni"] == kayit["eski"]
    assert kayit["ad"] == "Gumus Kule"
    assert sayfa.evaluate("async () => { await window.kapakGecisi.ready; return true; }")
    sayfa.evaluate("async () => { await window.kapakGecisi.finished; }")
    assert sayfa.locator("#bookHeroArt").evaluate("e => getComputedStyle(e).viewTransitionName") == "none"
    assert sayfa.locator("#shelves .spine-art").first.evaluate("e => getComputedStyle(e).viewTransitionName") == "none"
    sayfa.locator("#bookBackBtn").click()
    expect(sayfa.locator("#libraryView")).to_be_visible()
    sayfa.locator('#shelves .spine[data-slug="gumus-kule"]').click()
    expect(sayfa.locator("#bookView")).to_be_visible()
    sayfa.evaluate("async () => { await window.kapakGecisi.finished; }")
    assert sayfa.evaluate("history.state.slug") == "gumus-kule"


@pytest.mark.parametrize("kip", ["reduce", "desteksiz", "hata"])
def test_gecis_olmadan_kitap_acilir_ve_gecmis_korunur(sayfa, kip):
    sayfa.emulate_media(reduced_motion="reduce" if kip == "reduce" else "no-preference")
    _kutuphane(sayfa)
    sayfa.evaluate("""kip => {
      document.startViewTransition = kip === 'desteksiz' ? undefined : () => {
        throw new Error('Bu bağlamda geçiş kullanılamıyor');
      };
    }""", kip)
    sayfa.locator('#shelves .spine[data-slug="gumus-kule"]').click()
    expect(sayfa.locator("#bookView")).to_be_visible()
    expect(sayfa.locator("#bookHeroTitle")).to_have_text("Gumus Kule")
    assert sayfa.locator("#bookHeroArt").evaluate("e => getComputedStyle(e).viewTransitionName") == "none"
    sayfa.locator("#bookBackBtn").click()
    expect(sayfa.locator("#libraryView")).to_be_visible()


def test_yavas_bolum_listesi_kapak_gecisini_bekletmez(sayfa):
    sayfa.emulate_media(reduced_motion="no-preference")
    _kutuphane(sayfa)
    bekleyen = []
    sayfa.route("**/api/book/gumus-kule/chapters", lambda r: bekleyen.append(r))
    sayfa.evaluate("""() => {
      const baslat = document.startViewTransition.bind(document);
      window.kapakHazir = false;
      document.startViewTransition = guncelle => {
        const gecis = baslat(guncelle);
        gecis.ready.then(() => { window.kapakHazir = true; }, () => {});
        return gecis;
      };
    }""")
    try:
        sayfa.locator('#shelves .spine[data-slug="gumus-kule"]').click()
        expect(sayfa.locator("#bookView")).to_be_visible()
        sayfa.wait_for_function("window.kapakHazir", timeout=2000)
        expect(sayfa.locator("#chapterList")).to_contain_text("Yükleniyor")
    finally:
        for r in bekleyen:
            r.continue_()
